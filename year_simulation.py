"""
Year simulation of one household with solar panels and a battery, at 15-min resolution, plus the scenario sweep
(number of panels x battery capacity).

Assumptions:
- energy exported to the grid has the same price as energy imported (net metering at the day-ahead price)
- battery charging/discharging and the solar panels are lossless, the capacity is fully usable (0-100 %)
- no overhead for the battery cooling fans or for extra battery modules
- SoC is known exactly (F1.3 coulomb counting is frozen), grid impedance (F1.5) and faults (F5) are not modelled;
  the only F5 effect is the inverter current/power limit (c_rate)
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from forecasting import ForecastConfig, Forecasts, make_forecasts
from peak_shaving_controller import ControllerConfig, DayPlan, control_step, plan_day
from year_data import DT, N_DAYS, N_STEPS, PANEL_WP, STEPS_PER_DAY, YearData


@dataclass
class SimConfig:
    initial_soc: float = 0.5
    forecast: ForecastConfig = field(default_factory=ForecastConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)


@dataclass
class SimResult:
    n_panels: int
    capacity: float  # kWh
    p_solar: np.ndarray  # kW
    p_bat: np.ndarray  # kW, > 0 discharging
    p_grid: np.ndarray  # kW, > 0 import
    e_bat: np.ndarray  # kWh at the start of each step, length N_STEPS + 1
    peak_mask: np.ndarray  # planned peak quarters
    actual_peak_mask: np.ndarray  # hindsight peak quarters
    plans: list[DayPlan]
    metrics: dict


def window_mask(starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    q = np.arange(STEPS_PER_DAY)
    return ((q >= starts[:, None]) & (q < ends[:, None])).ravel()


def simulate_year(data: YearData, fc: Forecasts, n_panels: int, capacity: float, cfg: SimConfig) -> SimResult:
    ccfg = cfg.controller
    p_solar = data.p_solar_per_panel * n_panels
    solar_fc = fc.solar_per_panel * n_panels
    p_max = ccfg.c_rate * capacity
    price_daily = data.price.reshape(N_DAYS, STEPS_PER_DAY)

    p_bat = np.zeros(N_STEPS)
    e_bat = np.zeros(N_STEPS + 1)
    e_bat[0] = cfg.initial_soc * capacity
    plans = []

    for d in range(N_DAYS):
        plan = plan_day(e_bat[d * STEPS_PER_DAY], capacity, p_max, int(fc.peak_start[d]), int(fc.peak_end[d]),
                        fc.demand[d], solar_fc[d], price_daily[d], ccfg)
        plans.append(plan)
        if capacity <= 0:
            continue
        for q in range(STEPS_PER_DAY):
            i = d * STEPS_PER_DAY + q
            p_bat[i] = control_step(q, plan, data.p_consumption[i], p_solar[i], e_bat[i], capacity, p_max, ccfg)
            e_bat[i + 1] = e_bat[i] - p_bat[i] * DT

    p_grid = data.p_consumption - p_bat - p_solar
    result = SimResult(
        n_panels=n_panels, capacity=capacity, p_solar=p_solar, p_bat=p_bat, p_grid=p_grid, e_bat=e_bat,
        peak_mask=window_mask(fc.peak_start, fc.peak_end),
        actual_peak_mask=window_mask(fc.actual_peak_start, fc.actual_peak_end),
        plans=plans, metrics={},
    )
    result.metrics = compute_metrics(data, result, p_max)
    return result


def compute_metrics(data: YearData, r: SimResult, p_max: float) -> dict:
    imp = np.clip(r.p_grid, 0, None) * DT  # kWh per quarter
    exp = np.clip(-r.p_grid, 0, None) * DT
    cons = data.p_consumption * DT
    solar = r.p_solar * DT
    peak = r.peak_mask
    e_at_peak = r.e_bat[[p.peak_start + d * STEPS_PER_DAY for d, p in enumerate(r.plans)]]
    peak_import_per_day = (imp * peak).reshape(N_DAYS, STEPS_PER_DAY).sum(axis=1)

    import_kw = np.clip(r.p_grid, 0, None)
    monthly_max_kw = pd.Series(import_kw).groupby(data.timestamps.month).max()
    cost = r.p_grid * DT * data.price
    baseline_cost = cons * data.price  # same household without panels or battery

    total_solar = solar.sum()
    return {
        "household_id": data.household_id,
        "n_panels": r.n_panels,
        "pv_kwp": r.n_panels * PANEL_WP / 1000,
        "battery_kwh": r.capacity,
        "battery_max_kw": p_max,
        "consumption_kwh": cons.sum(),
        "solar_kwh": total_solar,
        "grid_import_kwh": imp.sum(),
        "grid_export_kwh": exp.sum(),
        "net_grid_kwh": imp.sum() - exp.sum(),
        # main KPI: grid use during the planned peak window, vs the household without panels or battery
        "peak_demand_kwh": cons[peak].sum(),
        "peak_grid_import_kwh": imp[peak].sum(),
        "peak_grid_export_kwh": exp[peak].sum(),
        "peak_draw_reduction_kwh": cons[peak].sum() - imp[peak].sum(),
        "peak_draw_reduction_pct": 100 * (1 - imp[peak].sum() / cons[peak].sum()),
        "peak_import_share_pct": 100 * imp[peak].sum() / cons[peak].sum(),
        "peak_max_import_kw": r.p_grid[peak].max(initial=0),
        "days_peak_fully_covered": int((peak_import_per_day < 1e-6).sum()),
        "worst_day_peak_import_kwh": peak_import_per_day.max(),
        "actual_peak_grid_import_kwh": imp[r.actual_peak_mask].sum(),
        "actual_peak_demand_kwh": cons[r.actual_peak_mask].sum(),
        # off-peak draw: > demand when the battery is charged from the grid
        "offpeak_demand_kwh": cons[~peak].sum(),
        "offpeak_grid_import_kwh": imp[~peak].sum(),
        "offpeak_draw_change_kwh": imp[~peak].sum() - cons[~peak].sum(),
        "battery_grid_charge_kwh": np.clip(-r.p_bat - np.clip(r.p_solar - data.p_consumption, 0, None),
                                           0, None).sum() * DT,
        # connection load (Flemish capacity tariff is based on the monthly 15-min import peak)
        "max_import_kw": import_kw.max(),
        "mean_monthly_max_import_kw": monthly_max_kw.mean(),
        "offpeak_max_import_kw": import_kw[~peak].max(initial=0),
        # too much electricity output to the grid
        "max_export_kw": max(0.0, -r.p_grid.min()),
        "export_hours": (exp > 0).sum() * DT,
        "self_consumption_pct": 100 * (1 - exp.sum() / total_solar) if total_solar > 0 else np.nan,
        "self_sufficiency_pct": 100 * (1 - imp.sum() / cons.sum()),
        # money at the day-ahead price, export paid at the same price as import
        "energy_cost_eur": float(cost.sum()),
        "peak_cost_eur": float(cost[peak].sum()),
        "offpeak_cost_eur": float(cost[~peak].sum()),
        "baseline_cost_eur": float(baseline_cost.sum()),
        "savings_eur": float(baseline_cost.sum() - cost.sum()),
        # battery
        "battery_full_at_peak_days": int((e_at_peak >= 0.99 * r.capacity).sum()) if r.capacity > 0 else 0,
        "battery_mean_soc_at_peak_pct": 100 * e_at_peak.mean() / r.capacity if r.capacity > 0 else np.nan,
        "battery_equivalent_cycles": np.clip(r.p_bat, 0, None).sum() * DT / r.capacity if r.capacity > 0 else 0.0,
    }


def daily_table(data: YearData, r: SimResult) -> pd.DataFrame:
    """One row per day: energy flows, peak coverage and battery state, for seasonal / distribution statistics."""
    def per_day(x: np.ndarray, how: str = "sum") -> np.ndarray:
        x = x.reshape(N_DAYS, STEPS_PER_DAY)
        return x.max(axis=1) if how == "max" else x.sum(axis=1)

    imp = np.clip(r.p_grid, 0, None) * DT
    exp = np.clip(-r.p_grid, 0, None) * DT
    cons = data.p_consumption * DT
    peak = r.peak_mask
    battery_grid_charge = np.clip(-r.p_bat - np.clip(r.p_solar - data.p_consumption, 0, None), 0, None) * DT
    peak_start = np.array([p.peak_start for p in r.plans])
    peak_end = np.array([p.peak_end for p in r.plans])
    actual = r.actual_peak_mask.reshape(N_DAYS, STEPS_PER_DAY)
    day_start = data.timestamps[::STEPS_PER_DAY]
    return pd.DataFrame({
        "household_id": data.household_id,
        "n_panels": r.n_panels,
        "battery_kwh": r.capacity,
        "date": day_start.strftime("%Y-%m-%d"),
        "month": day_start.month,
        "weekday": day_start.weekday,
        "peak_start_h": peak_start * DT,
        "peak_end_h": peak_end * DT,
        "actual_peak_start_h": actual.argmax(axis=1) * DT,
        "actual_peak_end_h": (actual.argmax(axis=1) + actual.sum(axis=1)) * DT,
        "consumption_kwh": per_day(cons),
        "solar_kwh": per_day(r.p_solar * DT),
        "grid_import_kwh": per_day(imp),
        "grid_export_kwh": per_day(exp),
        "peak_demand_kwh": per_day(cons * peak),
        "peak_grid_import_kwh": per_day(imp * peak),
        "peak_grid_export_kwh": per_day(exp * peak),
        "offpeak_grid_import_kwh": per_day(imp * ~peak),
        "actual_peak_grid_import_kwh": per_day(imp * r.actual_peak_mask),
        "battery_grid_charge_kwh": per_day(battery_grid_charge),
        "planned_grid_charge_kwh": [p.grid_charge.sum() * DT for p in r.plans],
        "battery_at_peak_start_kwh": r.e_bat[peak_start + np.arange(N_DAYS) * STEPS_PER_DAY],
        "battery_discharge_kwh": per_day(np.clip(r.p_bat, 0, None) * DT),
        "max_import_kw": per_day(np.clip(r.p_grid, 0, None), "max"),
        "max_export_kw": per_day(np.clip(-r.p_grid, 0, None), "max"),
        "cost_eur": per_day(r.p_grid * DT * data.price),
        "baseline_cost_eur": per_day(cons * data.price),
    })


def forecast_quality(data: YearData, fc: Forecasts) -> dict:
    """Accuracy of the midnight forecasts (household-specific for demand, shared for solar and peak window)."""
    demand = data.p_consumption.reshape(N_DAYS, STEPS_PER_DAY)
    solar = data.p_solar_per_panel.reshape(N_DAYS, STEPS_PER_DAY)
    overlap = np.minimum(fc.peak_end, fc.actual_peak_end) - np.maximum(fc.peak_start, fc.actual_peak_start)
    peak_hours = (fc.peak_end - fc.peak_start) * DT
    return {
        "peak_window_hours_min": float(peak_hours.min()),
        "peak_window_hours_median": float(np.median(peak_hours)),
        "peak_window_hours_max": float(peak_hours.max()),
        "demand_mae_kw": float(np.abs(fc.demand[1:] - demand[1:]).mean()),
        "demand_mean_kw": float(demand.mean()),
        "solar_daily_energy_mape_pct": float(100 * np.abs(fc.solar_per_panel[1:].sum(1) - solar[1:].sum(1)).sum()
                                             / solar[1:].sum()),
        "peak_window_overlap_pct": float(100 * np.clip(overlap, 0, None).sum() / (fc.peak_end - fc.peak_start).sum()),
    }


def run_sweep(data: YearData, panel_counts: list[int], battery_capacities: list[float],
              cfg: SimConfig | None = None) -> tuple[pd.DataFrame, dict[tuple[int, float], SimResult], Forecasts]:
    """Simulate every (panels, battery) combination for one household."""
    cfg = cfg if cfg is not None else SimConfig()
    fc = make_forecasts(data.p_consumption, data.p_solar_per_panel, data.grid_load, cfg.forecast)
    results = {}
    for n in panel_counts:
        for c in battery_capacities:
            results[(n, c)] = simulate_year(data, fc, n, c, cfg)
    table = pd.DataFrame([r.metrics for r in results.values()])

    # Part of the effect due to the battery alone: compare with the same panel count without battery
    if 0 in battery_capacities:
        no_bat = table[table["battery_kwh"] == 0].set_index("n_panels")
        ref = no_bat.loc[table["n_panels"]]
        table["battery_peak_reduction_kwh"] = ref["peak_grid_import_kwh"].to_numpy() - table["peak_grid_import_kwh"]
        table["battery_savings_eur"] = ref["energy_cost_eur"].to_numpy() - table["energy_cost_eur"]
    return table, results, fc

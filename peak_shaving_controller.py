"""
F1.6 Determine charge/discharge operating mode: optimisation-based scheduling, planned once per day at midnight.

Day plan (made at 00:00 with the forecasts of forecasting.py):
    1. the peak window of the day is taken from the forecasts (F1.4)
    2. target energy at peak start = full battery (or only the forecast peak net demand, see `target`)
    3. forecast how much excess solar will flow into the battery before the peak
    4. the rest is charged from the grid, in the cheapest pre-peak quarters (day-ahead prices are known at midnight)

Operating modes during the day:
    pre-peak  : hold the charge (no discharge), store all excess solar + the planned grid charging
    peak      : discharge to cover household demand not covered by solar, store excess solar
    post-peak : self-consumption (zero on the meter) until midnight

Variants (ControllerConfig): grid_charging=False charges from solar only; hold_before_peak=False makes the battery
do self-consumption all day (no peak priority), combine both for a solar-only self-consumption battery.

Sign convention (same as framework.py): p_bat > 0 discharges, p_bat < 0 charges,
p_grid = p_consumption - p_bat - p_solar (> 0 import, < 0 export).
"""
from dataclasses import dataclass

import numpy as np

from year_data import DT, STEPS_PER_DAY


@dataclass
class ControllerConfig:
    c_rate: float = 0.5  # max charge/discharge power per kWh of capacity (kW/kWh), the inverter limit (F5.4)
    target: str = "full"  # "full": battery as full as possible at peak start, "need": forecast peak net demand only
    solar_forecast_trust: float = 1.0  # < 1 plans more grid charging in case solar falls short of the forecast
    export_during_peak: bool = False  # True: also discharge the battery into the grid during the peak
    grid_charging: bool = True  # False: the battery is only charged from solar
    hold_before_peak: bool = True  # False: pure self-consumption all day, the peak gets no priority


@dataclass
class DayPlan:
    peak_start: int  # quarter index within the day
    peak_end: int
    grid_charge: np.ndarray  # (96,) planned battery charging power from the grid, kW
    e_target: float  # planned stored energy at peak start, kWh


def plan_day(e_now: float, capacity: float, p_max: float, peak_start: int, peak_end: int,
             demand_fc: np.ndarray, solar_fc: np.ndarray, price: np.ndarray, cfg: ControllerConfig) -> DayPlan:
    """
    :param e_now: stored energy at midnight, kWh
    :param demand_fc: forecast household demand for the day, kW per quarter
    :param solar_fc: forecast solar generation of the whole installation for the day, kW per quarter
    :param price: day-ahead prices of the day, EUR/kWh per quarter
    """
    solar_fc = solar_fc * cfg.solar_forecast_trust
    if cfg.target == "full":
        e_target = capacity
    elif cfg.target == "need":
        peak_net = np.clip(demand_fc - solar_fc, 0, None)[peak_start:peak_end]
        e_target = min(capacity, float(peak_net.sum()) * DT)
    else:
        raise ValueError(f"Unknown target '{cfg.target}'")

    # Excess solar that will charge the battery before the peak, capped by the inverter
    solar_charge = np.minimum(np.clip(solar_fc - demand_fc, 0, None)[:peak_start], p_max)
    e_from_grid = max(0.0, e_target - e_now - float(solar_charge.sum()) * DT)

    # Greedy fill of the cheapest pre-peak quarters, leaving inverter headroom for the forecast solar
    grid_charge = np.zeros(STEPS_PER_DAY)
    if not cfg.grid_charging:
        e_from_grid = 0.0
    headroom = p_max - solar_charge
    for q in np.argsort(price[:peak_start], kind="stable"):
        if e_from_grid <= 1e-9:
            break
        p = min(headroom[q], e_from_grid / DT)
        grid_charge[q] = p
        e_from_grid -= p * DT

    return DayPlan(peak_start=peak_start, peak_end=peak_end, grid_charge=grid_charge, e_target=e_target)


def control_step(q: int, plan: DayPlan, p_consumption: float, p_solar: float, e_bat: float,
                 capacity: float, p_max: float, cfg: ControllerConfig) -> float:
    """Battery power for quarter `q` of the day, limited by the inverter and the stored energy."""
    net = p_consumption - p_solar  # > 0: demand not covered by solar
    if not cfg.hold_before_peak:
        p_bat = net  # self-consumption: cover demand and store surplus all day
    elif q < plan.peak_start:
        p_bat = -(max(-net, 0.0) + plan.grid_charge[q])
    elif q < plan.peak_end:
        p_bat = p_max if cfg.export_during_peak else net
    else:
        p_bat = net

    p_bat = min(max(p_bat, -p_max), p_max)
    # Battery cannot go below empty or above full (perfect transfer, usable capacity)
    return min(max(p_bat, -(capacity - e_bat) / DT), e_bat / DT)

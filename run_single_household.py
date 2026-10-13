"""
Run the year simulation sweep (number of panels x battery capacity) for one household.

Run:   python run_single_household.py                       -> household 301, default sweep
       python run_single_household.py --household 450 --panels 0,4,8,12 --batteries 0,5,10,15
       python run_single_household.py --show                -> also open the figures
Writes results/household_<id>/scenarios.csv and the figures next to it.
"""
import argparse
import os

import matplotlib.pyplot as plt
import pandas as pd

import year_plots
from forecasting import ForecastConfig
from peak_shaving_controller import ControllerConfig
from year_data import load_year_data
from year_simulation import SimConfig, forecast_quality, run_sweep

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def int_list(text: str) -> list[int]:
    return [int(x) for x in text.split(",")]


def float_list(text: str) -> list[float]:
    return [float(x) for x in text.split(",")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--household", type=int, default=301)
    parser.add_argument("--panels", type=int_list, default=list(range(0, 17, 2)))
    parser.add_argument("--batteries", type=float_list, default=[0, 5, 10, 15], help="usable capacity, kWh")
    parser.add_argument("--peak-method", choices=["threshold", "fixed"], default="threshold")
    parser.add_argument("--peak-threshold", type=float, default=0.8,
                        help="threshold method: fraction of the daily load range that counts as peak")
    parser.add_argument("--peak-hours", type=float, default=4.0, help="fixed method: window length")
    parser.add_argument("--c-rate", type=float, default=0.5, help="max battery power per kWh of capacity")
    parser.add_argument("--target", choices=["full", "need"], default="full")
    parser.add_argument("--plot-scenario", default="10,10", help="panels,battery_kwh for the time-series plot")
    parser.add_argument("--plot-day", type=int, default=160, help="first day (0 = 1 Jan) of the time-series plot")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    cfg = SimConfig(
        forecast=ForecastConfig(peak_method=args.peak_method, peak_threshold=args.peak_threshold,
                                peak_hours=args.peak_hours),
        controller=ControllerConfig(c_rate=args.c_rate, target=args.target),
    )
    data = load_year_data(args.household)
    table, results, fc = run_sweep(data, args.panels, args.batteries, cfg)

    out_dir = os.path.join(RESULTS_DIR, f"household_{args.household}")
    os.makedirs(out_dir, exist_ok=True)
    table.to_csv(os.path.join(out_dir, "scenarios.csv"), index=False)

    print(f"Household {args.household}: {data.p_consumption.sum() * 0.25:.0f} kWh/yr consumption")
    for k, v in forecast_quality(data, fc).items():
        print(f"  {k}: {v:.2f}")
    with pd.option_context("display.width", 200, "display.max_columns", None, "display.float_format", "{:.1f}".format):
        print(table[["n_panels", "battery_kwh", "solar_kwh", "peak_grid_import_kwh", "peak_draw_reduction_pct",
                     "days_peak_fully_covered", "offpeak_grid_import_kwh", "offpeak_draw_change_kwh",
                     "grid_export_kwh", "max_import_kw", "savings_eur", "battery_equivalent_cycles"]]
              .to_string(index=False))

    figures = {
        "sweep.png": year_plots.plot_sweep(table, args.household),
        "heatmap_peak_import.png": year_plots.plot_heatmap(
            table, "peak_grid_import_kwh", "grid import during peak hours [kWh/yr]", args.household),
        "heatmap_export.png": year_plots.plot_heatmap(
            table, "grid_export_kwh", "grid export [kWh/yr]", args.household),
    }
    n_panels, capacity = args.plot_scenario.split(",")
    key = (int(n_panels), float(capacity))
    if key in results:
        figures["week.png"] = year_plots.plot_days(data, results[key], args.plot_day)
    for name, fig in figures.items():
        fig.savefig(os.path.join(out_dir, name), dpi=130)
    print(f"Saved results to {out_dir}")
    if args.show:
        plt.show()


if __name__ == "__main__":
    main()

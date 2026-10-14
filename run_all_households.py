"""
Run the year simulation sweep (number of panels x battery capacity) for many households, in parallel.

Run:   python run_all_households.py                          -> all 300 households, 4 worker processes
       python run_all_households.py --households 301,302,303 --workers 2
       python run_all_households.py --plots                  -> also save the per-household figures (slower)
Re-running with the same --out skips households that are already done (use --overwrite to redo them).

Writes to results/<out>/:
    run_config.json           settings, git commit and timing of the run
    scenarios.csv             one row per household x scenario, annual statistics
    monthly.csv               one row per household x scenario x month
    median_per_scenario.csv   median household per scenario
    forecast_quality.csv      one row per household
    errors.log                households that failed (only if any)
    households/<id>_*.csv(.gz) per-household parts, including the daily table (one row per scenario x day):
                              pd.concat(pd.read_csv(f) for f in glob.glob("results/<out>/households/*_daily.csv.gz"))
"""
import argparse
import glob
import json
import os
import subprocess
import time
import traceback
from datetime import datetime
from multiprocessing import Pool

import matplotlib
import pandas as pd

from forecasting import ForecastConfig
from peak_shaving_controller import ControllerConfig
from run_single_household import RESULTS_DIR, float_list, int_list
from year_data import load_household_table, load_shared_data, load_year_data
from year_simulation import SimConfig, daily_table, forecast_quality, run_sweep

_worker = {}


def monthly_from_daily(daily: pd.DataFrame) -> pd.DataFrame:
    keys = ["household_id", "n_panels", "battery_kwh", "month"]
    daily = daily.assign(
        peak_fully_covered=daily["peak_grid_import_kwh"] < 1e-6,
        battery_not_full_at_peak=(daily["battery_kwh"] > 0)
                                 & (daily["battery_at_peak_start_kwh"] < 0.99 * daily["battery_kwh"]),
    )
    sums = [c for c in daily.columns if c.endswith(("_kwh", "_eur")) and c not in keys + ["battery_at_peak_start_kwh"]]
    monthly = daily.groupby(keys).agg(
        **{c: (c, "sum") for c in sums},
        mean_battery_at_peak_start_kwh=("battery_at_peak_start_kwh", "mean"),
        max_import_kw=("max_import_kw", "max"),
        max_export_kw=("max_export_kw", "max"),
        days=("date", "count"),
        days_peak_fully_covered=("peak_fully_covered", "sum"),
        days_battery_not_full_at_peak=("battery_not_full_at_peak", "sum"),
    )
    return monthly.reset_index()


def init_worker(cfg: SimConfig, panels: list[int], batteries: list[float], plots: bool, parts_dir: str):
    """Load the data once per worker process instead of once per household."""
    _worker.update(shared=load_shared_data(), households=load_household_table(), cfg=cfg, panels=panels,
                   batteries=batteries, plots=plots, parts_dir=parts_dir)


def run_household(household_id: int) -> tuple[int, str | None]:
    """Simulate one household and write its parts; returns (id, error message or None)."""
    w = _worker
    try:
        data = load_year_data(household_id, w["shared"], w["households"])
        table, results, fc = run_sweep(data, w["panels"], w["batteries"], w["cfg"])
        daily = pd.concat([daily_table(data, r) for r in results.values()], ignore_index=True)
        prefix = os.path.join(w["parts_dir"], str(household_id))
        daily.to_csv(f"{prefix}_daily.csv.gz", index=False, float_format="%.4f")
        monthly_from_daily(daily).to_csv(f"{prefix}_monthly.csv", index=False)
        pd.DataFrame([{"household_id": household_id, **forecast_quality(data, fc)}]).to_csv(
            f"{prefix}_forecast.csv", index=False)
        # written last: its presence marks the household as done
        table.to_csv(f"{prefix}_scenarios.csv", index=False)
        if w["plots"]:
            save_plots(table, household_id)
        return household_id, None
    except Exception:
        return household_id, traceback.format_exc()


def save_plots(table: pd.DataFrame, household_id: int):
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import year_plots
    out_dir = os.path.join(RESULTS_DIR, f"household_{household_id}")
    os.makedirs(out_dir, exist_ok=True)
    for name, fig in {
        "sweep.png": year_plots.plot_sweep(table, household_id),
        "heatmap_peak_import.png": year_plots.plot_heatmap(
            table, "peak_grid_import_kwh", "grid import during peak hours [kWh/yr]", household_id),
    }.items():
        fig.savefig(os.path.join(out_dir, name), dpi=130)
        plt.close(fig)


def git_commit() -> str:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        return commit + (" (uncommitted changes)" if dirty else "")
    except OSError:
        return "unknown"


def combine(out_dir: str, parts_dir: str):
    def read_all(suffix: str) -> pd.DataFrame:
        return pd.concat((pd.read_csv(f) for f in sorted(glob.glob(os.path.join(parts_dir, f"*_{suffix}.csv")))),
                         ignore_index=True)

    scenarios = read_all("scenarios").sort_values(["household_id", "n_panels", "battery_kwh"])
    scenarios.to_csv(os.path.join(out_dir, "scenarios.csv"), index=False)
    read_all("monthly").sort_values(["household_id", "n_panels", "battery_kwh", "month"]).to_csv(
        os.path.join(out_dir, "monthly.csv"), index=False)
    read_all("forecast").sort_values("household_id").to_csv(os.path.join(out_dir, "forecast_quality.csv"),
                                                             index=False)
    medians = scenarios.drop(columns="household_id").groupby(["n_panels", "battery_kwh"]).median().reset_index()
    medians.to_csv(os.path.join(out_dir, "median_per_scenario.csv"), index=False)
    return scenarios, medians


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--households", default="all", help="'all' or a comma-separated list of EAN_IDs")
    parser.add_argument("--workers", type=int, default=4, help="parallel processes (number of CPU cores)")
    parser.add_argument("--panels", type=int_list, default=list(range(0, 17, 2)))
    parser.add_argument("--batteries", type=float_list, default=[0, 5, 10, 15], help="usable capacity, kWh")
    parser.add_argument("--peak-method", choices=["threshold", "fixed"], default="threshold")
    parser.add_argument("--peak-threshold", type=float, default=0.8)
    parser.add_argument("--peak-hours", type=float, default=4.0)
    parser.add_argument("--c-rate", type=float, default=0.5)
    parser.add_argument("--target", choices=["full", "need"], default="full")
    parser.add_argument("--no-grid-charging", action="store_true", help="charge the battery from solar only")
    parser.add_argument("--no-hold", action="store_true",
                        help="self-consumption all day instead of holding the charge for the peak")
    parser.add_argument("--plots", action="store_true", help="also save per-household figures")
    parser.add_argument("--out", default="all_households", help="output folder name inside results/")
    parser.add_argument("--overwrite", action="store_true", help="redo households that already have results")
    args = parser.parse_args()

    cfg = SimConfig(
        forecast=ForecastConfig(peak_method=args.peak_method, peak_threshold=args.peak_threshold,
                                peak_hours=args.peak_hours),
        controller=ControllerConfig(c_rate=args.c_rate, target=args.target, grid_charging=not args.no_grid_charging,
                                    hold_before_peak=not args.no_hold),
    )
    out_dir = os.path.join(RESULTS_DIR, args.out)
    parts_dir = os.path.join(out_dir, "households")
    os.makedirs(parts_dir, exist_ok=True)

    ids = load_household_table()[0].tolist() if args.households == "all" else int_list(args.households)
    done = {i for i in ids if os.path.exists(os.path.join(parts_dir, f"{i}_scenarios.csv"))}
    todo = ids if args.overwrite else [i for i in ids if i not in done]
    print(f"{len(ids)} households, {len(ids) - len(todo)} already done, {len(todo)} to run")

    config_path = os.path.join(out_dir, "run_config.json")
    run_config = {"arguments": vars(args), "sim_config": repr(cfg), "git_commit": git_commit(),
                  "started": datetime.now().isoformat(timespec="seconds")}

    start = time.time()
    errors = []
    with Pool(args.workers, initializer=init_worker,
              initargs=(cfg, args.panels, args.batteries, args.plots, parts_dir)) as pool:
        for i, (household_id, error) in enumerate(pool.imap_unordered(run_household, todo), 1):
            if error:
                errors.append(f"household {household_id}\n{error}")
            elapsed = time.time() - start
            print(f"\r{i}/{len(todo)} households, {len(errors)} failed, {elapsed:.0f} s elapsed, "
                  f"~{elapsed / i * (len(todo) - i):.0f} s left", end="", flush=True)
    print()

    if errors:
        with open(os.path.join(out_dir, "errors.log"), "w") as f:
            f.write("\n".join(errors))
        print(f"{len(errors)} households failed, see {os.path.join(out_dir, 'errors.log')}")

    scenarios, medians = combine(out_dir, parts_dir)
    run_config.update(finished=datetime.now().isoformat(timespec="seconds"), seconds=round(time.time() - start),
                      households_with_results=int(scenarios["household_id"].nunique()), failed=len(errors))
    with open(config_path, "w") as f:
        json.dump(run_config, f, indent=2)

    with pd.option_context("display.width", 200, "display.max_columns", None, "display.float_format", "{:.1f}".format):
        print("Median over households:")
        print(medians[["n_panels", "battery_kwh", "peak_grid_import_kwh", "peak_draw_reduction_pct",
                       "days_peak_fully_covered", "offpeak_grid_import_kwh", "grid_export_kwh", "max_import_kw",
                       "savings_eur"]].to_string(index=False))
    print(f"Saved results of {scenarios['household_id'].nunique()} households to {out_dir}")


if __name__ == "__main__":
    main()

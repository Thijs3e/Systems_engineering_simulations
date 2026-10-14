"""
Figures across all households for one finished run of run_all_households.py.

Run:   python make_summary_plots.py                    -> results/all_full
       python make_summary_plots.py --run all_need
       python make_summary_plots.py --scatter-panels 4  -> panel count used in the per-household figures
       python make_summary_plots.py --compare all_full,all_need,all_fixed4h
Writes results/<run>/figures/*.png, or results/comparison/compare_runs.png with --compare
"""
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from run_single_household import RESULTS_DIR
from year_plots import MUTED, SERIES_COLORS, TEXT

BATTERY_LABEL = "{:g} kWh"


def band_plot(ax, scenarios: pd.DataFrame, column: str, title: str):
    """Median over households (line) and the 25-75 % household range (band), one series per battery size."""
    stats = scenarios.groupby(["battery_kwh", "n_panels"])[column].quantile([0.25, 0.5, 0.75]).unstack()
    for i, cap in enumerate(sorted(scenarios["battery_kwh"].unique())):
        s = stats.loc[cap]
        ax.fill_between(s.index, s[0.25], s[0.75], color=SERIES_COLORS[i], alpha=0.15, linewidth=0)
        ax.plot(s.index, s[0.5], color=SERIES_COLORS[i], linewidth=2, marker="o", markersize=5,
                label=BATTERY_LABEL.format(cap))
    ax.set_title(title, fontsize=10, loc="left")
    ax.set_xlabel("Number of 400 Wp panels")


def figure_bands(scenarios: pd.DataFrame, n_households: int):
    kpis = [
        ("peak_draw_reduction_pct", "Peak-hour grid draw reduction [%]"),
        ("savings_eur", "Savings vs no panels/battery [EUR/yr]"),
        ("max_import_kw", "Highest 15-min grid draw [kW]"),
        ("offpeak_draw_change_kwh", "Change in off-peak grid draw [kWh/yr]"),
    ]
    fig, axs = plt.subplots(2, 2, figsize=(13, 8.5), sharex=True)
    fig.suptitle(f"{n_households} households: median (line) and middle 50 % of households (band)", color=TEXT)
    for ax, (col, title) in zip(axs.ravel(), kpis):
        band_plot(ax, scenarios, col, title)
        ax.axhline(0, color=MUTED, linewidth=0.8)
    for ax in axs[0]:
        ax.set_xlabel("")
    handles, labels = axs[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, title="Battery", loc="upper right", ncol=len(labels), fontsize=8, title_fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def figure_peak_draw_yearly(scenarios: pd.DataFrame, n_households: int):
    """Yearly grid draw during peak hours; right panel zooms in on the battery scenarios."""
    fig, (ax_all, ax_zoom) = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(f"Yearly grid draw during peak hours, {n_households} households: "
                 f"median (line) and middle 50 % (band)", color=TEXT)
    band_plot(ax_all, scenarios, "peak_grid_import_kwh", "All scenarios [kWh/yr]")
    # zoom: same colours as the left panel, without the no-battery series
    zoom = scenarios[scenarios["battery_kwh"] > 0]
    stats = zoom.groupby(["battery_kwh", "n_panels"])["peak_grid_import_kwh"].quantile([0.25, 0.5, 0.75]).unstack()
    for i, cap in enumerate(sorted(scenarios["battery_kwh"].unique())):
        if cap == 0:
            continue
        s = stats.loc[cap]
        ax_zoom.fill_between(s.index, s[0.25], s[0.75], color=SERIES_COLORS[i], alpha=0.15, linewidth=0)
        ax_zoom.plot(s.index, s[0.5], color=SERIES_COLORS[i], linewidth=2, marker="o", markersize=5,
                     label=BATTERY_LABEL.format(cap))
    ax_zoom.set_title("Zoom on battery scenarios [kWh/yr]", fontsize=10, loc="left")
    ax_zoom.set_xlabel("Number of 400 Wp panels")
    for ax in (ax_all, ax_zoom):
        ax.set_ylim(bottom=0)
    ax_all.legend(title="Battery", fontsize=8, title_fontsize=8)
    fig.tight_layout()
    return fig


def figure_monthly(monthly: pd.DataFrame, n_panels: int):
    """Peak-hour grid draw per month, summed over households, for each battery size at one panel count."""
    sub = monthly[monthly["n_panels"] == n_panels]
    per_month = sub.groupby(["battery_kwh", "month"])[["peak_grid_import_kwh", "peak_demand_kwh"]].sum()
    fig, (ax_abs, ax_pct) = plt.subplots(1, 2, figsize=(13, 4.8))
    fig.suptitle(f"Peak-hour grid draw per month, all households, {n_panels} panels", color=TEXT)
    for i, cap in enumerate(sorted(sub["battery_kwh"].unique())):
        m = per_month.loc[cap]
        ax_abs.plot(m.index, m["peak_grid_import_kwh"] / 1000, color=SERIES_COLORS[i], linewidth=2, marker="o",
                    markersize=5, label=BATTERY_LABEL.format(cap))
        ax_pct.plot(m.index, 100 * m["peak_grid_import_kwh"] / m["peak_demand_kwh"], color=SERIES_COLORS[i],
                    linewidth=2, marker="o", markersize=5, label=BATTERY_LABEL.format(cap))
    ax_abs.set_title("Grid draw during peak hours [MWh, all households]", fontsize=10, loc="left")
    ax_pct.set_title("Share of peak-hour demand still drawn from the grid [%]", fontsize=10, loc="left")
    for ax in (ax_abs, ax_pct):
        ax.set_xticks(range(1, 13), ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
        ax.set_xlabel("Month")
        ax.set_ylim(bottom=0)
    ax_pct.legend(title="Battery", fontsize=8, title_fontsize=8)
    fig.tight_layout()
    return fig


def figure_household_size(scenarios: pd.DataFrame, n_panels: int):
    """Per household: annual consumption vs share of peak demand still drawn from the grid."""
    sub = scenarios[(scenarios["n_panels"] == n_panels) & (scenarios["battery_kwh"] > 0)]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for i, cap in enumerate(sorted(scenarios["battery_kwh"].unique())):
        s = sub[sub["battery_kwh"] == cap]
        if len(s):
            ax.scatter(s["consumption_kwh"], s["peak_import_share_pct"], s=18, color=SERIES_COLORS[i],
                       edgecolor="white", linewidth=0.5, label=BATTERY_LABEL.format(cap))
    ax.set_xlabel("Household consumption [kWh/yr]")
    ax.set_ylabel("Peak-hour demand still from the grid [%]")
    ax.set_title(f"Which households need a bigger battery? ({n_panels} panels, one dot per household)",
                 fontsize=10, loc="left", color=TEXT)
    ax.legend(title="Battery", fontsize=8, title_fontsize=8)
    fig.tight_layout()
    return fig


def figure_sufficient_battery(scenarios: pd.DataFrame, coverage_pct: float = 99.0):
    """Share of households where each battery size reaches the coverage target, per panel count."""
    ok = scenarios.assign(ok=scenarios["peak_draw_reduction_pct"] >= coverage_pct)
    share = ok.groupby(["battery_kwh", "n_panels"])["ok"].mean().unstack(0) * 100
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, cap in enumerate(share.columns):
        ax.plot(share.index, share[cap], color=SERIES_COLORS[i], linewidth=2, marker="o", markersize=5,
                label=BATTERY_LABEL.format(cap))
    ax.set_ylim(0, 105)
    ax.set_xlabel("Number of 400 Wp panels")
    ax.set_ylabel("Households [%]")
    ax.set_title(f"Share of households with at least {coverage_pct:g} % peak-hour grid draw reduction",
                 fontsize=10, loc="left", color=TEXT)
    ax.legend(title="Battery", fontsize=8, title_fontsize=8)
    fig.tight_layout()
    return fig


def figure_compare(runs: dict[str, pd.DataFrame], coverage_pct: float = 99.0):
    """Runs side by side: one row per KPI, one column per battery size, one line per run."""
    kpis = [
        ("peak_grid_import_kwh", "Median yearly grid draw in peak hours [kWh/yr]"),
        ("covered", f"Households with >= {coverage_pct:g} % peak reduction [%]"),
        ("max_import_kw", "Median highest 15-min grid draw [kW]"),
        ("battery_grid_charge_kwh", "Median battery charging from grid [kWh/yr]"),
        ("savings_eur", "Median savings [EUR/yr]"),
    ]
    batteries = sorted(c for c in next(iter(runs.values()))["battery_kwh"].unique() if c > 0)
    fig, axs = plt.subplots(len(kpis), len(batteries), figsize=(4.2 * len(batteries), 3.0 * len(kpis)),
                            sharex=True, sharey="row", squeeze=False)
    fig.suptitle("Comparison of runs (peak KPIs use each run's own peak window definition)", color=TEXT)
    for i, (name, scenarios) in enumerate(runs.items()):
        s = scenarios.assign(covered=100.0 * (scenarios["peak_draw_reduction_pct"] >= coverage_pct))
        agg = s.groupby(["battery_kwh", "n_panels"]).agg(
            peak_grid_import_kwh=("peak_grid_import_kwh", "median"),
            covered=("covered", "mean"), max_import_kw=("max_import_kw", "median"),
            battery_grid_charge_kwh=("battery_grid_charge_kwh", "median"), savings_eur=("savings_eur", "median"))
        for col, cap in enumerate(batteries):
            for row, (kpi, _) in enumerate(kpis):
                a = agg.loc[cap]
                axs[row, col].plot(a.index, a[kpi], color=SERIES_COLORS[i], linewidth=2, marker="o", markersize=4,
                                   label=name)
    for col, cap in enumerate(batteries):
        axs[0, col].set_title(f"Battery {cap:g} kWh", fontsize=10, color=TEXT)
        axs[-1, col].set_xlabel("Number of 400 Wp panels")
    for row, (_, label) in enumerate(kpis):
        axs[row, 0].set_ylabel(label, fontsize=8)
    handles, labels = axs[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, title="Run", loc="upper right", ncol=len(labels), fontsize=8, title_fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="all_full", help="output folder of run_all_households.py inside results/")
    parser.add_argument("--compare", help="comma-separated runs to compare, e.g. all_full,all_need,all_fixed4h; "
                                          "writes results/comparison/compare_runs.png instead of per-run figures")
    parser.add_argument("--scatter-panels", type=int, default=8, help="panel count for the monthly/household plots")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    if args.compare:
        runs = {name: pd.read_csv(os.path.join(RESULTS_DIR, name, "scenarios.csv"))
                for name in args.compare.split(",")}
        out_dir = os.path.join(RESULTS_DIR, "comparison")
        os.makedirs(out_dir, exist_ok=True)
        figure_compare(runs).savefig(os.path.join(out_dir, "compare_runs.png"), dpi=130)
        print(f"Saved comparison of {len(runs)} runs to {out_dir}")
        if args.show:
            plt.show()
        return

    run_dir = os.path.join(RESULTS_DIR, args.run)
    scenarios = pd.read_csv(os.path.join(run_dir, "scenarios.csv"))
    monthly = pd.read_csv(os.path.join(run_dir, "monthly.csv"))
    n_households = scenarios["household_id"].nunique()

    out_dir = os.path.join(run_dir, "figures")
    os.makedirs(out_dir, exist_ok=True)
    figures = {
        "kpi_bands.png": figure_bands(scenarios, n_households),
        "peak_draw_yearly.png": figure_peak_draw_yearly(scenarios, n_households),
        "monthly_peak_draw.png": figure_monthly(monthly, args.scatter_panels),
        "household_size.png": figure_household_size(scenarios, args.scatter_panels),
        "sufficient_battery.png": figure_sufficient_battery(scenarios),
    }
    for name, fig in figures.items():
        fig.savefig(os.path.join(out_dir, name), dpi=130)
    print(f"Saved {len(figures)} figures to {out_dir}")
    if args.show:
        plt.show()


if __name__ == "__main__":
    main()

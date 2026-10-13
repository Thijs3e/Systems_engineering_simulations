import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from year_data import DT, STEPS_PER_DAY, YearData
from year_simulation import SimResult

# Fixed categorical order, one colour per battery size (never cycled), text stays in neutral ink
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
PEAK_SHADE = "#e34948"

plt.rcParams.update({
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
    "axes.spines.right": False, "axes.titlecolor": TEXT, "legend.frameon": False,
})


def plot_sweep(table: pd.DataFrame, household_id: int):
    """KPIs against the number of panels, one line per battery capacity."""
    kpis = [
        ("peak_grid_import_kwh", "Grid import during peak hours [kWh/yr]"),
        ("offpeak_grid_import_kwh", "Grid import outside peak hours [kWh/yr]"),
        ("grid_export_kwh", "Grid export [kWh/yr]"),
        ("savings_eur", "Savings vs no panels/battery, day-ahead price [EUR/yr]"),
    ]
    fig, axs = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
    fig.suptitle(f"Household {household_id}: panels x battery sweep", color=TEXT)
    batteries = sorted(table["battery_kwh"].unique())
    for ax, (col, title) in zip(axs.ravel(), kpis):
        for i, cap in enumerate(batteries):
            sub = table[table["battery_kwh"] == cap].sort_values("n_panels")
            ax.plot(sub["n_panels"], sub[col], color=SERIES_COLORS[i], linewidth=2, marker="o", markersize=5,
                    label=f"{cap:g} kWh")
        ax.set_title(title, fontsize=10, loc="left")
        ax.axhline(0, color=MUTED, linewidth=0.8)
    for ax in axs[1]:
        ax.set_xlabel("Number of 400 Wp panels")
    # battery lines often overlap, so one shared legend instead of direct labels
    handles, labels = axs[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, title="Battery", loc="upper right", ncol=len(batteries), fontsize=8,
               title_fontsize=8)
    fig.tight_layout()
    return fig


def plot_heatmap(table: pd.DataFrame, column: str, title: str, household_id: int):
    """One KPI over the full grid of scenarios, single-hue sequential scale."""
    grid = table.pivot(index="battery_kwh", columns="n_panels", values=column).sort_index(ascending=False)
    fig, ax = plt.subplots(figsize=(1.0 * grid.shape[1] + 2, 0.7 * grid.shape[0] + 1.6))
    im = ax.imshow(grid.to_numpy(), cmap="Blues", aspect="auto")
    ax.grid(False)
    ax.set_xticks(range(grid.shape[1]), [str(c) for c in grid.columns])
    ax.set_yticks(range(grid.shape[0]), [f"{c:g} kWh" for c in grid.index])
    ax.set_xlabel("Number of 400 Wp panels")
    ax.set_ylabel("Battery capacity")
    ax.set_title(f"Household {household_id}: {title}", fontsize=10, loc="left")
    for (y, x), v in np.ndenumerate(grid.to_numpy()):
        # white text on dark cells, judged on the rendered colour's luminance
        r, g, b, _ = im.cmap(im.norm(v))
        ax.text(x, y, f"{v:.0f}", ha="center", va="center", fontsize=8,
                color="white" if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5 else TEXT)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    return fig


def plot_days(data: YearData, r: SimResult, start_day: int, n_days: int = 7):
    """Time series of one scenario over a few days, planned peak windows shaded."""
    sl = slice(start_day * STEPS_PER_DAY, (start_day + n_days) * STEPS_PER_DAY)
    t = data.timestamps[sl]
    fig, (ax_p, ax_e) = plt.subplots(2, 1, figsize=(13, 7), sharex=True, height_ratios=[2, 1])
    fig.suptitle(f"Household {data.household_id}: {r.n_panels} panels, {r.capacity:g} kWh battery", color=TEXT)

    for ax in (ax_p, ax_e):
        in_peak = r.peak_mask[sl]
        ax.fill_between(t, 0, 1, where=in_peak, transform=ax.get_xaxis_transform(), color=PEAK_SHADE,
                        alpha=0.08, step="post", linewidth=0, label="Planned peak")

    ax_p.step(t, data.p_consumption[sl], where="post", color=SERIES_COLORS[0], linewidth=1.5, label="Consumption")
    ax_p.step(t, r.p_solar[sl], where="post", color=SERIES_COLORS[3], linewidth=1.5, label="Solar")
    ax_p.step(t, r.p_bat[sl], where="post", color=SERIES_COLORS[2], linewidth=1.5, label="Battery (+ discharge)")
    ax_p.step(t, r.p_grid[sl], where="post", color=SERIES_COLORS[1], linewidth=1.5, label="Grid (+ import)")
    ax_p.axhline(0, color=MUTED, linewidth=0.8)
    ax_p.set_ylabel("Power [kW]")
    ax_p.legend(ncol=5, fontsize=8, loc="upper left")

    ax_e.plot(t, r.e_bat[sl], color=SERIES_COLORS[2], linewidth=2, label="Stored energy")
    ax_e.axhline(r.capacity, color=MUTED, linewidth=0.8, linestyle="--")
    ax_e.set_ylabel("Battery [kWh]")
    ax_e.set_ylim(0, max(r.capacity, 0.1) * 1.08)
    fig.tight_layout()
    return fig

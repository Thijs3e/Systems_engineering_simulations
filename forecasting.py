"""
Day-ahead forecasts made at midnight, using only data from previous days.

- F1.1 household demand : rolling average of the same weekday over the previous weeks
- F1.2 solar generation : season-based profile = average daily profile of the previous days
- F1.4 grid peak period : from the average grid load profile of the previous week, either
                          "threshold": the contiguous block around the maximum where the load stays above
                                       min + peak_threshold * (max - min) of that profile (length changes per day)
                          "fixed":     the `peak_hours` long window with the highest load

Everything is returned per day as (N_DAYS, STEPS_PER_DAY) arrays so it can be computed once per household
and shared between all battery / panel scenarios.
"""
from dataclasses import dataclass

import numpy as np

from year_data import N_DAYS, STEPS_PER_DAY, DT


@dataclass
class ForecastConfig:
    peak_method: str = "threshold"  # "threshold" (dynamic length) or "fixed"
    peak_threshold: float = 0.8  # "threshold": fraction of the profile's daily range that counts as peak
    peak_hours: float = 4.0  # "fixed": length of the window; also the length of the day-0 fallback window
    peak_history_days: int = 7  # rolling average of the previous week
    fallback_peak_start_hour: float = 17.0  # used on day 0, when there is no history yet
    demand_history_weeks: int = 4  # same-weekday measurements used for the demand forecast
    solar_history_days: int = 14  # days used for the season-based solar profile


@dataclass
class Forecasts:
    peak_start: np.ndarray  # (N_DAYS,) first quarter of the planned peak window
    peak_end: np.ndarray  # (N_DAYS,) quarter after the planned peak window
    actual_peak_start: np.ndarray  # (N_DAYS,) hindsight peak window of the day itself, for evaluation only
    actual_peak_end: np.ndarray
    demand: np.ndarray  # (N_DAYS, 96) forecast household demand, kW
    solar_per_panel: np.ndarray  # (N_DAYS, 96) forecast output of one panel, kW


def best_window(profile: np.ndarray, length: int) -> tuple[int, int]:
    """Start/end index of the contiguous window of `length` steps with the highest total."""
    totals = np.convolve(profile, np.ones(length), "valid")
    start = int(np.argmax(totals))
    return start, start + length


def threshold_window(profile: np.ndarray, threshold: float) -> tuple[int, int]:
    """Contiguous block around the maximum where the profile stays above min + threshold * (max - min)."""
    level = profile.min() + threshold * (profile.max() - profile.min())
    start = end = int(np.argmax(profile))
    while start > 0 and profile[start - 1] >= level:
        start -= 1
    while end < len(profile) and profile[end] >= level:
        end += 1
    return start, end


def window_of(profile: np.ndarray, cfg: ForecastConfig) -> tuple[int, int]:
    if cfg.peak_method == "threshold":
        return threshold_window(profile, cfg.peak_threshold)
    if cfg.peak_method == "fixed":
        return best_window(profile, round(cfg.peak_hours / DT))
    raise ValueError(f"Unknown peak_method '{cfg.peak_method}'")


def peak_windows(grid_load: np.ndarray, cfg: ForecastConfig) -> tuple[np.ndarray, np.ndarray]:
    """F1.4: at midnight, pick the peak window from the average load profile of the previous week."""
    daily = grid_load.reshape(N_DAYS, STEPS_PER_DAY)
    starts = np.zeros(N_DAYS, dtype=int)
    ends = np.zeros(N_DAYS, dtype=int)
    for d in range(N_DAYS):
        history = daily[max(0, d - cfg.peak_history_days):d]
        if len(history) == 0:
            starts[d] = round(cfg.fallback_peak_start_hour / DT)
            ends[d] = starts[d] + round(cfg.peak_hours / DT)
        else:
            starts[d], ends[d] = window_of(history.mean(axis=0), cfg)
    return starts, ends


def actual_peak_windows(grid_load: np.ndarray, cfg: ForecastConfig) -> tuple[np.ndarray, np.ndarray]:
    """Peak window of each day known in hindsight (same method), to evaluate how good the F1.4 choice was."""
    daily = grid_load.reshape(N_DAYS, STEPS_PER_DAY)
    windows = np.array([window_of(day, cfg) for day in daily])
    return windows[:, 0], windows[:, 1]


def demand_forecast(p_consumption: np.ndarray, cfg: ForecastConfig) -> np.ndarray:
    """F1.1: mean of the same weekday over the previous `demand_history_weeks` weeks.

    In the first week (no same weekday yet) the mean of all previous days is used; day 0 has no history (zeros).
    """
    daily = p_consumption.reshape(N_DAYS, STEPS_PER_DAY)
    forecast = np.zeros_like(daily)
    for d in range(1, N_DAYS):
        same_weekday = [d - 7 * k for k in range(1, cfg.demand_history_weeks + 1) if d - 7 * k >= 0]
        forecast[d] = daily[same_weekday].mean(axis=0) if same_weekday else daily[:d].mean(axis=0)
    return forecast


def solar_forecast(p_solar: np.ndarray, cfg: ForecastConfig) -> np.ndarray:
    """F1.2: average daily generation profile of the previous `solar_history_days` days; day 0 has none (zeros)."""
    daily = p_solar.reshape(N_DAYS, STEPS_PER_DAY)
    forecast = np.zeros_like(daily)
    for d in range(1, N_DAYS):
        forecast[d] = daily[max(0, d - cfg.solar_history_days):d].mean(axis=0)
    return forecast


def make_forecasts(p_consumption: np.ndarray, p_solar_per_panel: np.ndarray, grid_load: np.ndarray,
                   cfg: ForecastConfig) -> Forecasts:
    peak_start, peak_end = peak_windows(grid_load, cfg)
    actual_start, actual_end = actual_peak_windows(grid_load, cfg)
    return Forecasts(
        peak_start=peak_start,
        peak_end=peak_end,
        actual_peak_start=actual_start,
        actual_peak_end=actual_end,
        demand=demand_forecast(p_consumption, cfg),
        solar_per_panel=solar_forecast(p_solar_per_panel, cfg),
    )

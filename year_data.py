"""
Load one full year (2024) of input data for the year simulation, aligned on the same 35136 quarter-hour rows.

All sources use local CET/CEST wall-clock time, 366 days x 96 quarters: the DST hour is missing on 31 Mar and
repeated on 27 Oct in every file, so the rows line up one to one (Fluvius only orders the 8 repeated quarters on
27 Oct differently, which is irrelevant at night). Hourly day-ahead prices are repeated over their 4 quarters.

Sources (see data_fetch/):
- datasources/fluvius_household_data.csv : household consumption (kWh per quarter), households without PV
- datasources/pvgis_solar_panel.csv      : output of ONE 400 Wp south-facing panel in Delft (W)
- datasources/entsoe_grid_load.csv       : NL actual total grid load (MW)
- datasources/entsoe_energy_prices.csv   : NL day-ahead price (EUR/MWh)
"""
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datasources")
HOUSEHOLD_CSV = os.path.join(DATA_DIR, "fluvius_household_data.csv")
HOUSEHOLD_CACHE = os.path.join(DATA_DIR, "cache", "fluvius_households_kwh.npz")
SOLAR_CSV = os.path.join(DATA_DIR, "pvgis_solar_panel.csv")
GRID_LOAD_CSV = os.path.join(DATA_DIR, "entsoe_grid_load.csv")
PRICES_CSV = os.path.join(DATA_DIR, "entsoe_energy_prices.csv")

DT = 0.25  # timestep in hours
STEPS_PER_DAY = 96
N_DAYS = 366
N_STEPS = N_DAYS * STEPS_PER_DAY  # 35136
PANEL_WP = 400  # peak power of the panel simulated in pvgis_solar_panel.csv


@dataclass
class YearData:
    household_id: int
    timestamps: pd.DatetimeIndex  # local wall-clock start of each quarter
    p_consumption: np.ndarray  # household demand, kW
    p_solar_per_panel: np.ndarray  # output of one panel, kW
    grid_load: np.ndarray  # NL actual total load, MW
    price: np.ndarray  # day-ahead price, EUR/kWh


def load_household_table() -> tuple[np.ndarray, np.ndarray]:
    """All households as (ids, kW array of shape (n_households, N_STEPS)).

    The 790 MB CSV is parsed once (~15 s) and cached as a compressed .npz in datasources/cache/.
    """
    if os.path.exists(HOUSEHOLD_CACHE):
        cache = np.load(HOUSEHOLD_CACHE)
        return cache["ids"], cache["kw"]

    df = pd.read_csv(HOUSEHOLD_CSV, usecols=["EAN_ID", "Volume_Afname_KWh"],
                     dtype={"EAN_ID": np.int32, "Volume_Afname_KWh": np.float32})
    ean = df["EAN_ID"].to_numpy()
    if not (np.diff(ean) >= 0).all():
        raise ValueError("Fluvius CSV is expected to be grouped by EAN_ID")
    ids, counts = np.unique(ean, return_counts=True)
    if (counts != N_STEPS).any():
        raise ValueError(f"Every household must have {N_STEPS} rows, got {sorted(set(counts))}")
    # Households have no PV, so the energy taken from the grid is the full consumption
    kw = df["Volume_Afname_KWh"].to_numpy().reshape(len(ids), N_STEPS) / DT

    os.makedirs(os.path.dirname(HOUSEHOLD_CACHE), exist_ok=True)
    np.savez_compressed(HOUSEHOLD_CACHE, ids=ids, kw=kw)
    return ids, kw


def load_shared_data() -> dict[str, np.ndarray | pd.DatetimeIndex]:
    """Solar, grid load and prices: identical for every household."""
    solar = pd.read_csv(SOLAR_CSV)
    grid = pd.read_csv(GRID_LOAD_CSV)
    prices = pd.read_csv(PRICES_CSV)
    if len(solar) != N_STEPS or len(grid) != N_STEPS or len(prices) * 4 != N_STEPS:
        raise ValueError("Input files do not cover the 2024 year on the expected 15-min / hourly grid")
    return {
        "timestamps": pd.DatetimeIndex(pd.to_datetime(solar["Datum_Startuur"])),
        "p_solar_per_panel": solar["Power_W"].to_numpy() / 1000,
        "grid_load": grid["Actual Total Load (MW)"].to_numpy(dtype=float),
        "price": np.repeat(prices["Day-ahead Price (EUR/MWh)"].to_numpy(dtype=float) / 1000, 4),
    }


def load_year_data(household_id: int, shared: dict | None = None,
                   households: tuple[np.ndarray, np.ndarray] | None = None) -> YearData:
    """
    :param household_id: Fluvius EAN_ID (301..600)
    :param shared: output of load_shared_data(), pass it in when looping over households to avoid re-reading
    :param households: output of load_household_table(), same reason
    """
    shared = shared if shared is not None else load_shared_data()
    ids, kw = households if households is not None else load_household_table()
    row = np.searchsorted(ids, household_id)
    if row >= len(ids) or ids[row] != household_id:
        raise ValueError(f"Unknown household {household_id}, valid ids are {ids[0]}..{ids[-1]}")
    return YearData(household_id=int(household_id), p_consumption=kw[row].astype(float), **shared)

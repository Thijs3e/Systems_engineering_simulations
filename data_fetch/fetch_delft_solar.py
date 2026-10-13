"""
Simulate the output of ONE south-facing solar panel on a house in Delft, as 15-min values
for 2024, using PVGIS (via pvlib.iotools.get_pvgis_hourly).

PVGIS only has weather data up to 2023, so the 2023 hourly output is mapped onto the
2024 calendar (29 Feb is a copy of 28 Feb). Hourly values are then split into 15-min
values (smooth interpolation, rescaled so every hour keeps exactly the PVGIS energy).

The output follows the same convention as the Fluvius / ENTSO-E data: local Belgian/Dutch
wall-clock time (CET/CEST), 2024-01-01 00:00 .. 2024-12-31 23:45, 35136 rows, with
02:00-02:45 missing on 31 Mar and repeated on 27 Oct.

Run:   python fetch_delft_solar.py   -> writes datasources/pvgis_solar_panel.csv
"""
import os

import numpy as np
import pandas as pd
from pvlib.iotools import get_pvgis_hourly

LAT, LON = 52.0116, 4.3571     # Delft
TILT = 37                      # PVGIS optimum for Delft; 45 gives ~0.7% less per year
AZIMUTH = 180                  # pvlib convention: 180 = south
PANEL_WP = 400                 # peak power of one panel (W)
LOSS = 14                      # system losses (%), PVGIS default (inverter, cables, dirt)
WEATHER_YEAR = 2023            # latest year available in PVGIS (SARAH3)
TARGET_YEAR = 2024
TZ = "Europe/Amsterdam"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "datasources")
OUT_CSV = os.path.join(OUT_DIR, "pvgis_solar_panel.csv")


def fetch_hourly():
    """Hourly AC power (W) of one panel, indexed by the UTC start of each hour."""
    data, meta = get_pvgis_hourly(
        LAT, LON, start=WEATHER_YEAR, end=WEATHER_YEAR,
        surface_tilt=TILT, surface_azimuth=AZIMUTH,
        pvcalculation=True, peakpower=PANEL_WP / 1000, loss=LOSS,
        mountingplace="free", components=False,
        url="https://re.jrc.ec.europa.eu/api/v5_3/")
    print("PVGIS:", meta["inputs"]["meteo_data"]["radiation_db"], "| mounting:",
          meta["inputs"]["mounting_system"]["fixed"])
    p = data["P"]
    p.index = p.index.floor("h")  # PVGIS stamps hours as HH:11; value covers the whole hour
    return p


def to_target_year(p):
    """Map the weather-year hourly series onto the target-year UTC hours that cover local 2024."""
    lookup = {(t.month, t.day, t.hour): v for t, v in p.items()}
    start = pd.Timestamp(f"{TARGET_YEAR}-01-01", tz=TZ).tz_convert("UTC")
    end = pd.Timestamp(f"{TARGET_YEAR + 1}-01-01", tz=TZ).tz_convert("UTC")
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    vals = [lookup[(t.month, 28 if (t.month, t.day) == (2, 29) else t.day, t.hour)]
            for t in hours]
    return pd.Series(vals, index=hours)


def to_quarters(p):
    """Split hourly mean power into 15-min mean power, preserving each hour's energy."""
    hourly = p.to_numpy()
    centers_h = np.arange(len(hourly)) + 0.5
    centers_q = np.arange(len(hourly) * 4) / 4 + 0.125
    q = np.clip(np.interp(centers_q, centers_h, hourly), 0, None).reshape(-1, 4)
    sums = q.sum(axis=1, keepdims=True)
    q = np.where(sums > 0, q / np.where(sums > 0, sums, 1) * hourly[:, None] * 4,
                 hourly[:, None])
    index = pd.date_range(p.index[0], periods=q.size, freq="15min")
    return pd.Series(q.ravel(), index=index)


def main():
    q = to_quarters(to_target_year(fetch_hourly()))
    local = q.index.tz_convert(TZ)
    df = pd.DataFrame({
        "Datum": local.strftime("%Y-%m-%d"),
        "Datum_Startuur": local.strftime("%Y-%m-%dT%H:%M:%S"),
        "Power_W": q.round(3).to_numpy(),
        "Energy_Wh": (q * 0.25).round(4).to_numpy(),
    })
    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"saved {OUT_CSV}: {len(df)} rows, {df['Datum_Startuur'].iloc[0]} .. "
          f"{df['Datum_Startuur'].iloc[-1]}")
    print(f"annual yield: {df['Energy_Wh'].sum() / 1000:.1f} kWh "
          f"({df['Energy_Wh'].sum() / PANEL_WP:.0f} kWh/kWp), peak {df['Power_W'].max():.0f} W")


if __name__ == "__main__":
    main()

import numpy as np
import pandas as pd


def load_solar_range(
        csv_path: str,
        start_day: str,
        start_hour: float,
        end_day: str,
        end_hour: float,
) -> np.ndarray:
    df = pd.read_csv(csv_path)
    df["Datum/tijd"] = pd.to_datetime(
        df["Datum/tijd"],
        format="%m/%d/%Y %H:%M"
    )
    start = (
            pd.to_datetime(start_day, format="%d/%m/%Y")
            + pd.to_timedelta(start_hour, unit="h")
    )
    end = (
            pd.to_datetime(end_day, format="%d/%m/%Y")
            + pd.to_timedelta(end_hour, unit="h")
    )
    mask = (
            (df["Datum/tijd"] >= start)
            & (df["Datum/tijd"] <= end)
    )
    watthours = df.loc[mask, "Geproduceerde energie (Wh)"].to_numpy()
    return watthours / 0.25  # data sampled per fifteen minutes. So convert watthour to kilowatts


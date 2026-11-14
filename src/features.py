"""Build the modelling table: one row per station-hour with calendar, weather, lag and station features."""
import numpy as np
import pandas as pd

from config import RAW, PROCESSED
import db

# Known data-quality incidents found during cleaning (see notebooks/01_cleaning.ipynb)
OUTAGE_DATES = ["2025-08-05"]   # only 183 trips network-wide vs ~25k normal: system/data outage

# Approximate London state-school holidays for 2025/26 (most boroughs follow these;
# a few differ by a day or two). Used as an optional feature.
SCHOOL_HOLIDAYS = [
    ("2025-07-23", "2025-09-02"),  # summer
    ("2025-10-27", "2025-10-31"),  # October half term
    ("2025-12-22", "2026-01-02"),  # Christmas
    ("2026-02-16", "2026-02-20"),  # February half term
    ("2026-03-30", "2026-04-10"),  # Easter
    ("2026-05-25", "2026-05-29"),  # May half term
]

FEATURES = [
    "hour", "dow", "month", "is_weekend", "is_bank_holiday", "is_school_holiday",
    "temperature", "precipitation", "wind_speed",
    "lag_24", "lag_48", "lag_168", "same_hour_mean_7d", "roll_7d_mean",
    "nb_docks", "lat", "lon", "station_code",
]
TARGET = "departures"


def load_weather():
    w = pd.read_csv(RAW / "reference" / "weather_hourly.csv")
    w["hour_ts"] = pd.to_datetime(w["hour_ts"])
    # Open-Meteo returns local clock time; drop the repeated hour at the October clock change
    w = w.drop_duplicates("hour_ts").rename(columns={
        "temperature_2m": "temperature", "wind_speed_10m": "wind_speed",
        "relative_humidity_2m": "humidity"})
    return w[["hour_ts", "temperature", "precipitation", "rain", "wind_speed", "humidity", "weather_code"]]


def load_holidays():
    h = pd.read_csv(RAW / "reference" / "bank_holidays.csv", parse_dates=["date"])
    return h


def school_holiday_flag(dates: pd.Series) -> pd.Series:
    flag = pd.Series(False, index=dates.index)
    for a, b in SCHOOL_HOLIDAYS:
        flag |= dates.between(pd.Timestamp(a), pd.Timestamp(b))
    return flag.astype(int)


def build_feature_table() -> pd.DataFrame:
    hd = db.read_table("hourly_demand")
    st = db.read_table("top_stations")
    hd["hour_ts"] = pd.to_datetime(hd["hour_ts"])
    df = hd.merge(st[["station_id", "display_name", "nb_docks", "lat", "lon", "demand_rank"]],
                  on="station_id", how="left")

    # Calendar
    df["date"] = df["hour_ts"].dt.normalize()
    df["hour"] = df["hour_ts"].dt.hour
    df["dow"] = df["hour_ts"].dt.day_of_week
    df["month"] = df["hour_ts"].dt.month
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    bh = load_holidays()
    df["is_bank_holiday"] = df["date"].isin(bh["date"]).astype(int)
    df["is_school_holiday"] = school_holiday_flag(df["date"])

    # Outage: unknown true demand, so mask the target (and therefore lags built from it)
    df["is_outage"] = df["date"].isin(pd.to_datetime(OUTAGE_DATES)).astype(int)
    for c in ("departures", "arrivals", "departures_ebike"):
        df[c] = df[c].astype(float)
        df.loc[df["is_outage"] == 1, c] = np.nan

    # Weather (observed values used as a stand-in for a day-ahead forecast)
    df = df.merge(load_weather(), on="hour_ts", how="left")

    # Lags: the grid is complete (every station-hour present), so shift() = hours back.
    # All lags are >= 24h so the forecast can be made the evening before.
    df = df.sort_values(["station_id", "hour_ts"]).reset_index(drop=True)
    g = df.groupby("station_id")["departures"]
    for k in (24, 48, 168):
        df[f"lag_{k}"] = g.shift(k)
    same_hour = np.column_stack([g.shift(24 * d) for d in range(1, 8)])
    df["same_hour_mean_7d"] = np.nanmean(same_hour, axis=1)
    df["roll_7d_mean"] = g.transform(lambda s: s.shift(24).rolling(168, min_periods=120).mean())

    df["station_code"] = df["station_id"].astype("category").cat.codes
    return df


def save_feature_table(df):
    df.to_parquet(PROCESSED / "features.parquet", index=False)


if __name__ == "__main__":
    import warnings; warnings.simplefilter("ignore", RuntimeWarning)
    df = build_feature_table()
    save_feature_table(df)
    print(df.shape)
    print(df[FEATURES + [TARGET]].isna().mean().round(4))

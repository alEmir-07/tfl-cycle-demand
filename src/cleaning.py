"""Ingest and clean TfL Santander Cycles journey extracts.

TfL has changed the extract schema several times. This module maps every known
variant onto one standard schema, so older files can be added without code changes:

  2015-2022 style: Rental Id, Duration (s), Bike Id, End Date, EndStation Id, EndStation Name,
                   Start Date, StartStation Id, StartStation Name  (dates dd/mm/yyyy HH:MM)
  2022+ style:     Number, Start date, Start station number, Start station, End date,
                   End station number, End station, Bike number, Bike model,
                   Total duration, Total duration (ms)            (dates yyyy-mm-dd HH:MM)
"""
from pathlib import Path
import re
import pandas as pd

from config import RAW, PROCESSED, MIN_DURATION_S, MAX_DURATION_S, JOURNEY_FILES

STANDARD_COLS = ["rental_id", "start_ts", "start_station_id", "start_station_name",
                 "end_ts", "end_station_id", "end_station_name", "bike_id", "bike_model",
                 "duration_s"]

COLUMN_MAP = {
    # 2022+ schema
    "Number": "rental_id", "Start date": "start_ts", "Start station number": "start_station_id",
    "Start station": "start_station_name", "End date": "end_ts",
    "End station number": "end_station_id", "End station": "end_station_name",
    "Bike number": "bike_id", "Bike model": "bike_model", "Total duration (ms)": "duration_ms",
    # legacy schema
    "Rental Id": "rental_id", "Start Date": "start_ts", "StartStation Id": "start_station_id",
    "StartStation Name": "start_station_name", "End Date": "end_ts",
    "EndStation Id": "end_station_id", "EndStation Name": "end_station_name",
    "Bike Id": "bike_id", "Duration": "duration_s", "Duration_Seconds": "duration_s",
}


def read_extract(path: Path) -> pd.DataFrame:
    """Read one extract file and return it in the standard schema (unfiltered)."""
    header = pd.read_csv(path, nrows=0).columns
    usecols = [c for c in header if c in COLUMN_MAP]
    df = pd.read_csv(path, usecols=usecols, dtype=str).rename(columns=COLUMN_MAP)

    if "duration_ms" in df:
        df["duration_s"] = pd.to_numeric(df.pop("duration_ms"), errors="coerce") / 1000
    else:
        df["duration_s"] = pd.to_numeric(df["duration_s"], errors="coerce")

    # The two schemas use different date formats: detect from the first value.
    sample = df["start_ts"].dropna().iloc[0]
    fmt = "%Y-%m-%d %H:%M" if re.match(r"\d{4}-", sample) else "%d/%m/%Y %H:%M"
    for c in ("start_ts", "end_ts"):
        df[c] = pd.to_datetime(df[c], format=fmt, errors="coerce")

    if "bike_model" not in df:
        df["bike_model"] = pd.NA
    df["rental_id"] = pd.to_numeric(df["rental_id"], errors="coerce").astype("Int64")
    for c in ("start_station_id", "end_station_id"):
        df[c] = df[c].str.strip()
    df["source_file"] = path.name
    return df[STANDARD_COLS + ["source_file"]]


def canonical_name(name: str) -> str:
    """Strip TfL's rename markers, e.g. 'London Fields, Hackney Central_OLD'."""
    if pd.isna(name):
        return name
    return re.sub(r"(_OLD|\s*\(OLD\))\s*$", "", name.strip(), flags=re.I).strip()


def remap_station_id(ids: pd.Series) -> pd.Series:
    """Merge retired station codes back onto the live station.

    When TfL relocates or re-registers a dock it keeps the 6-digit code for the new
    record and retires the old one by appending 4s (e.g. 200025 -> 200025444,
    200145 -> 2001454444). The retired name also gets an '_OLD' suffix. Both refer to
    the same physical location, so their trips are combined under the 6-digit code.
    """
    retired = ids.str.len().gt(6) & ids.str[6:].str.fullmatch(r"4+")
    return ids.where(~retired, ids.str[:6])


def build_station_lookup(df: pd.DataFrame, bikepoint: pd.DataFrame) -> pd.DataFrame:
    """One row per station id.

    Station *names* change (renames, relocations, '_OLD' suffixes) but the station
    *number* (TfL terminal code) is stable, so it is the join key throughout. The
    display name is the most recent name seen in the journey data, falling back to
    the current BikePoint name.
    """
    names = pd.concat([
        df[["start_station_id", "start_station_name", "start_ts"]]
          .set_axis(["station_id", "name", "ts"], axis=1),
        df[["end_station_id", "end_station_name", "end_ts"]]
          .set_axis(["station_id", "name", "ts"], axis=1),
    ]).dropna(subset=["station_id"])
    names["clean_name"] = names["name"].map(canonical_name)

    n_variants = names.groupby("station_id")["name"].nunique().rename("n_name_variants")
    latest = (names.sort_values("ts").groupby("station_id").tail(1)
                   .set_index("station_id")["clean_name"].rename("journey_name"))

    bp = bikepoint.rename(columns={"terminal_name": "station_id"}).copy()
    bp["station_id"] = bp["station_id"].astype(str).str.strip()
    lk = (pd.concat([latest, n_variants], axis=1).reset_index()
            .rename(columns={"index": "station_id"})
            .merge(bp[["station_id", "bikepoint_id", "station_name", "lat", "lon", "nb_docks"]],
                   on="station_id", how="left"))
    lk["display_name"] = lk["journey_name"].fillna(lk["station_name"])
    lk["in_bikepoint"] = lk["bikepoint_id"].notna()
    return lk[["station_id", "display_name", "n_name_variants", "bikepoint_id",
               "lat", "lon", "nb_docks", "in_bikepoint"]]


def clean_journeys(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply the cleaning rules and return (clean_df, audit_counts)."""
    audit = {"raw_rows": len(raw)}
    df = raw.drop_duplicates(subset="rental_id")          # extracts overlap at boundaries
    audit["after_dedup"] = len(df)
    df = df.dropna(subset=["start_ts", "end_ts", "start_station_id", "duration_s"])
    audit["after_dropna"] = len(df)
    df = df[df["duration_s"] >= MIN_DURATION_S]
    audit["after_min_duration"] = len(df)
    df = df[df["duration_s"] <= MAX_DURATION_S]
    audit["after_max_duration"] = len(df)
    # Short round trips (same dock, < 2 min) are almost always a rider re-docking a faulty bike
    false_start = (df["start_station_id"] == df["end_station_id"]) & (df["duration_s"] < 120)
    df = df[~false_start]
    audit["after_false_starts"] = len(df)

    df = df.copy()
    for c in ("start_station_id", "end_station_id"):
        df[c] = remap_station_id(df[c])
    df["start_station_name"] = df["start_station_name"].map(canonical_name)
    df["end_station_name"] = df["end_station_name"].map(canonical_name)
    df["start_hour"] = df["start_ts"].dt.floor("h")
    df["end_hour"] = df["end_ts"].dt.floor("h")
    return df.sort_values("start_ts").reset_index(drop=True), audit


def run(files=JOURNEY_FILES, start=None, end=None):
    raw = pd.concat([read_extract(RAW / "journeys" / f) for f in files], ignore_index=True)
    clean, audit = clean_journeys(raw)
    if start is not None:
        n = len(clean)
        clean = clean[(clean["start_ts"] >= start) & (clean["start_ts"] < end)]
        audit["outside_study_window"] = n - len(clean)
        audit["final_rows"] = len(clean)
    bikepoint = pd.read_csv(RAW / "reference" / "bikepoint_stations.csv", dtype={"terminal_name": str})
    stations = build_station_lookup(clean, bikepoint)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(PROCESSED / "journeys_clean.parquet", index=False)
    stations.to_csv(PROCESSED / "stations.csv", index=False)
    return clean, stations, audit, raw


if __name__ == "__main__":
    from config import START_DATE, END_DATE
    clean, stations, audit, _ = run(start=pd.Timestamp(START_DATE),
                                    end=pd.Timestamp(END_DATE) + pd.Timedelta(days=1))
    print(audit)

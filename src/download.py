"""Download raw inputs: TfL journey extracts, BikePoint stations, Open-Meteo weather, UK bank holidays.

Usage:  python src/download.py [journeys|stations|weather|holidays|all]
"""
import json, sys, time
from pathlib import Path
import pandas as pd
import requests

from config import (RAW, JOURNEY_FILES, BUCKET, START_DATE, END_DATE, LONDON_LAT, LONDON_LON)


def download_journeys():
    out = RAW / "journeys"; out.mkdir(parents=True, exist_ok=True)
    for name in JOURNEY_FILES:
        dest = out / name
        if dest.exists() and dest.stat().st_size > 1_000_000:
            print("skip", name); continue
        for attempt in range(3):
            try:
                with requests.get(BUCKET + "usage-stats/" + name, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    tmp = dest.with_suffix(".part")
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                    tmp.rename(dest)
                print("ok", name, f"{dest.stat().st_size/1e6:.1f}MB", flush=True); break
            except Exception as e:
                print("retry", name, e, flush=True); time.sleep(5)


def download_stations():
    """BikePoint API -> one row per docking station with coordinates and capacity."""
    r = requests.get("https://api.tfl.gov.uk/BikePoint", timeout=120); r.raise_for_status()
    rows = []
    for bp in r.json():
        props = {p["key"]: p["value"] for p in bp.get("additionalProperties", [])}
        rows.append({
            "bikepoint_id": bp["id"], "station_name": bp["commonName"],
            "terminal_name": props.get("TerminalName"),
            "lat": bp["lat"], "lon": bp["lon"],
            "nb_docks": pd.to_numeric(props.get("NbDocks"), errors="coerce"),
            "nb_bikes": pd.to_numeric(props.get("NbBikes"), errors="coerce"),
            "nb_empty_docks": pd.to_numeric(props.get("NbEmptyDocks"), errors="coerce"),
            "installed": props.get("Installed"), "locked": props.get("Locked"),
            "snapshot_utc": pd.Timestamp.now("UTC").isoformat(),
        })
    df = pd.DataFrame(rows)
    df.to_csv(RAW / "reference" / "bikepoint_stations.csv", index=False)
    print("stations", len(df))


def download_weather():
    """Open-Meteo archive: hourly weather for central London, in local time."""
    params = {
        "latitude": LONDON_LAT, "longitude": LONDON_LON,
        "start_date": START_DATE, "end_date": END_DATE,
        "hourly": "temperature_2m,precipitation,rain,wind_speed_10m,relative_humidity_2m,weather_code",
        "timezone": "Europe/London",
    }
    r = requests.get("https://archive-api.open-meteo.com/v1/archive", params=params, timeout=120)
    r.raise_for_status()
    h = r.json()["hourly"]
    df = pd.DataFrame(h).rename(columns={"time": "hour_ts"})
    df.to_csv(RAW / "reference" / "weather_hourly.csv", index=False)
    print("weather rows", len(df))


def download_holidays():
    r = requests.get("https://www.gov.uk/bank-holidays.json", timeout=60); r.raise_for_status()
    ev = r.json()["england-and-wales"]["events"]
    df = pd.DataFrame(ev)[["date", "title"]]
    df.to_csv(RAW / "reference" / "bank_holidays.csv", index=False)
    print("holidays", len(df))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    (RAW / "reference").mkdir(parents=True, exist_ok=True)
    if what in ("stations", "all"): download_stations()
    if what in ("weather", "all"): download_weather()
    if what in ("holidays", "all"): download_holidays()
    if what in ("journeys", "all"): download_journeys()

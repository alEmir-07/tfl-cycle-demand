"""Load cleaned data into SQLite and run the SQL aggregation layer in sql/."""
import sqlite3
import pandas as pd
from config import ROOT, PROCESSED, DB_PATH, START_DATE, END_DATE, N_STATIONS

SQL = ROOT / "sql"


def run_sql_file(con, name, params=None):
    text = (SQL / name).read_text()
    if params:
        # sqlite3.executescript has no parameter binding; run statements one at a time
        for stmt in [s.strip() for s in text.split(";") if s.strip()]:
            used = {k: v for k, v in params.items() if f":{k}" in stmt}
            con.execute(stmt, used)
    else:
        con.executescript(text)
    con.commit()


def build_database(journeys: pd.DataFrame, stations: pd.DataFrame, n_stations=N_STATIONS):
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    run_sql_file(con, "01_schema.sql")
    fmt = "%Y-%m-%d %H:%M:%S"
    j = journeys[["rental_id", "start_ts", "start_hour", "start_station_id", "end_ts", "end_hour",
                  "end_station_id", "bike_model", "duration_s"]].copy()
    for c in ("start_ts", "start_hour", "end_ts", "end_hour"):
        j[c] = j[c].dt.strftime(fmt)
    j.to_sql("journeys", con, if_exists="append", index=False, chunksize=200_000)
    stations.to_sql("stations", con, if_exists="append", index=False)
    run_sql_file(con, "02_indexes.sql")
    params = {"n_stations": n_stations, "start_date": START_DATE, "end_date": END_DATE}
    for f in ("03_top_stations.sql", "04_hourly_demand.sql", "05_station_profiles.sql"):
        run_sql_file(con, f, params)
    return con


def read_table(name, con=None):
    con = con or sqlite3.connect(DB_PATH)
    return pd.read_sql(f"SELECT * FROM {name}", con)


if __name__ == "__main__":
    import cleaning
    clean, stations, audit, _ = cleaning.run(start=pd.Timestamp(START_DATE),
                                             end=pd.Timestamp(END_DATE) + pd.Timedelta(days=1))
    print(audit)
    con = build_database(clean, stations)
    for t in ("journeys", "top_stations", "hourly_demand", "station_profiles"):
        print(t, con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])

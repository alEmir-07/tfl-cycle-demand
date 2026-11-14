-- Schema for the cleaned journey data and reference tables (SQLite).
DROP TABLE IF EXISTS journeys;
CREATE TABLE journeys (
    rental_id          INTEGER PRIMARY KEY,
    start_ts           TEXT NOT NULL,      -- local London time, 'YYYY-MM-DD HH:MM:SS'
    start_hour         TEXT NOT NULL,      -- start_ts floored to the hour
    start_station_id   TEXT NOT NULL,      -- TfL terminal code: stable across station renames
    end_ts             TEXT NOT NULL,
    end_hour           TEXT NOT NULL,
    end_station_id     TEXT,
    bike_model         TEXT,               -- CLASSIC / PBSC_EBIKE
    duration_s         REAL NOT NULL
);

DROP TABLE IF EXISTS stations;
CREATE TABLE stations (
    station_id       TEXT PRIMARY KEY,
    display_name     TEXT,
    n_name_variants  INTEGER,
    bikepoint_id     TEXT,
    lat              REAL,
    lon              REAL,
    nb_docks         INTEGER,
    in_bikepoint     INTEGER
);

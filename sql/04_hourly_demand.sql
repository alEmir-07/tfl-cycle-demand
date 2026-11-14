-- Hourly departures AND arrivals per top station, with every station-hour present.
-- Hours with no trips are filled with 0 using a recursive calendar spine.
DROP TABLE IF EXISTS hourly_demand;
CREATE TABLE hourly_demand AS
WITH RECURSIVE hours(hour_ts) AS (
    SELECT datetime(:start_date)
    UNION ALL
    SELECT datetime(hour_ts, '+1 hour') FROM hours
    WHERE  hour_ts < datetime(:end_date, '+23 hours')
),
dep AS (
    SELECT start_station_id AS station_id, start_hour AS hour_ts, COUNT(*) AS n,
           SUM(bike_model = 'PBSC_EBIKE') AS n_ebike
    FROM   journeys
    WHERE  start_station_id IN (SELECT station_id FROM top_stations)
    GROUP BY 1, 2
),
arr AS (
    SELECT end_station_id AS station_id, end_hour AS hour_ts, COUNT(*) AS n
    FROM   journeys
    WHERE  end_station_id IN (SELECT station_id FROM top_stations)
    GROUP BY 1, 2
)
SELECT  t.station_id,
        h.hour_ts,
        COALESCE(d.n, 0)       AS departures,
        COALESCE(d.n_ebike, 0) AS departures_ebike,
        COALESCE(a.n, 0)       AS arrivals
FROM    top_stations t
CROSS JOIN hours h
LEFT JOIN dep d ON d.station_id = t.station_id AND d.hour_ts = h.hour_ts
LEFT JOIN arr a ON a.station_id = t.station_id AND a.hour_ts = h.hour_ts
ORDER BY t.station_id, h.hour_ts;

CREATE INDEX ix_hd ON hourly_demand (station_id, hour_ts);

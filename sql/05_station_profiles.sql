-- Station "character": share of departures in the AM peak, PM peak and at weekends,
-- and average net flow (arrivals - departures) in the AM peak. Used in EDA to tell
-- commuter-origin hubs (mainline stations) from destinations and leisure (park) stations.
DROP TABLE IF EXISTS station_profiles;
CREATE TABLE station_profiles AS
WITH base AS (
    SELECT  station_id,
            CAST(strftime('%H', hour_ts) AS INTEGER) AS hr,
            CASE WHEN strftime('%w', hour_ts) IN ('0', '6') THEN 1 ELSE 0 END AS is_weekend,
            departures, arrivals
    FROM    hourly_demand
)
SELECT  b.station_id,
        t.display_name,
        t.nb_docks,
        SUM(departures)                                                            AS departures,
        SUM(arrivals)                                                              AS arrivals,
        ROUND(1.0 * SUM(CASE WHEN is_weekend = 0 AND hr BETWEEN 7 AND 9  THEN departures END) / SUM(departures), 3) AS share_am_peak,
        ROUND(1.0 * SUM(CASE WHEN is_weekend = 0 AND hr BETWEEN 16 AND 18 THEN departures END) / SUM(departures), 3) AS share_pm_peak,
        ROUND(1.0 * SUM(CASE WHEN is_weekend = 1 THEN departures END) / SUM(departures), 3)                         AS share_weekend,
        ROUND(AVG(CASE WHEN is_weekend = 0 AND hr BETWEEN 7 AND 9 THEN arrivals - departures END) * 3, 1)          AS am_peak_net_flow_per_day
FROM    base b
JOIN    top_stations t USING (station_id)
GROUP BY b.station_id;

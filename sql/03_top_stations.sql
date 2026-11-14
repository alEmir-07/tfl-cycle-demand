-- Pick the N busiest start stations. Only stations that still exist in BikePoint
-- (so capacity and coordinates are known) are eligible.
DROP TABLE IF EXISTS top_stations;
CREATE TABLE top_stations AS
SELECT  s.station_id,
        s.display_name,
        s.nb_docks,
        s.lat,
        s.lon,
        COUNT(*)                                   AS departures_12m,
        ROUND(COUNT(*) / 365.0, 1)                 AS departures_per_day,
        RANK() OVER (ORDER BY COUNT(*) DESC)       AS demand_rank
FROM    journeys j
JOIN    stations s ON s.station_id = j.start_station_id
WHERE   s.in_bikepoint = 1 AND s.nb_docks > 0
GROUP BY s.station_id
ORDER BY departures_12m DESC
LIMIT   :n_stations;

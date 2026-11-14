CREATE INDEX IF NOT EXISTS ix_j_start ON journeys (start_station_id, start_hour);
CREATE INDEX IF NOT EXISTS ix_j_end   ON journeys (end_station_id, end_hour);

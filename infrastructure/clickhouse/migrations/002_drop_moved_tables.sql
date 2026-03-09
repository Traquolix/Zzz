-- Migration 002: Drop tables moved to PostgreSQL or deleted as unused
--
-- fiber_monitored_sections → now a Django model in PostgreSQL
-- fiber_danger_zones → deleted (unused)
-- actors → deleted (unused)
--
-- Run with: clickhouse-client --multiquery < 002_drop_moved_tables.sql

DROP TABLE IF EXISTS sequoia.fiber_monitored_sections;
DROP TABLE IF EXISTS sequoia.fiber_danger_zones;
DROP TABLE IF EXISTS sequoia.actors;

SELECT 'Migration 002: dropped fiber_monitored_sections, fiber_danger_zones, actors' AS status;

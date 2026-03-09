-- Migration 001: Add direction column to tables that lack it
-- Safe to run before code deploy (existing code ignores the new column)
-- Run with: clickhouse-client --multiquery < 001_add_direction_columns.sql

-- ============================================================================
-- 1. Add direction columns
-- ============================================================================

ALTER TABLE sequoia.fiber_incidents
    ADD COLUMN IF NOT EXISTS direction UInt8 DEFAULT 0 AFTER fiber_id;

-- fiber_monitored_sections and fiber_danger_zones removed from ClickHouse
-- (sections moved to PostgreSQL, danger zones deleted as unused)

SELECT 'Migration 001: direction column added to fiber_incidents' AS status;

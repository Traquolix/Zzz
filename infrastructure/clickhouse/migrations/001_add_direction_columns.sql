-- Migration 001: Add direction column to tables that lack it
-- Safe to run before code deploy (existing code ignores the new column)
-- Run with: clickhouse-client --multiquery < 001_add_direction_columns.sql

-- ============================================================================
-- 1. Add direction columns
-- ============================================================================

ALTER TABLE sequoia.fiber_incidents
    ADD COLUMN IF NOT EXISTS direction UInt8 DEFAULT 0 AFTER fiber_id;

ALTER TABLE sequoia.fiber_monitored_sections
    ADD COLUMN IF NOT EXISTS direction UInt8 DEFAULT 0 AFTER fiber_id;

ALTER TABLE sequoia.fiber_danger_zones
    ADD COLUMN IF NOT EXISTS direction UInt8 DEFAULT 0 AFTER fiber_id;

-- ============================================================================
-- 2. Backfill fiber_monitored_sections
-- ============================================================================
-- Existing rows may have fiber_id = "carros:0" (direction encoded in string).
-- Extract direction into the new column and strip the suffix from fiber_id.
-- ReplacingMergeTree merges on updated_at, so the newer corrected row wins.

INSERT INTO sequoia.fiber_monitored_sections
    (section_id, fiber_id, direction, section_name, channel_start, channel_end,
     expected_travel_time_seconds, alert_threshold_percent,
     is_active, created_at, created_by, updated_at)
SELECT
    section_id,
    splitByChar(':', fiber_id)[1] AS fiber_id,
    toUInt8(splitByChar(':', fiber_id)[2]) AS direction,
    section_name, channel_start, channel_end,
    expected_travel_time_seconds, alert_threshold_percent,
    is_active, created_at, created_by, now()
FROM sequoia.fiber_monitored_sections FINAL
WHERE position(fiber_id, ':') > 0;

SELECT 'Migration 001: direction columns added, sections backfilled' AS status;

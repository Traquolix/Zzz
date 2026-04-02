-- Migration 104: Drop severity column from fiber_incidents.
-- Tags are now stored in PostgreSQL, not ClickHouse.

ALTER TABLE sequoia.fiber_incidents DROP INDEX IF EXISTS idx_severity;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS severity;

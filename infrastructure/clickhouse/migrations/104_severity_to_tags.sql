-- Migration 104: Replace severity enum with tags array on fiber_incidents.
--
-- Adds tags column, backfills from severity, then drops severity.

-- ============================================================================
-- 1. Add tags column
-- ============================================================================

ALTER TABLE sequoia.fiber_incidents
    ADD COLUMN IF NOT EXISTS tags Array(String) DEFAULT [] CODEC(ZSTD(1));

-- ============================================================================
-- 2. Backfill tags from severity for existing rows
-- ============================================================================

ALTER TABLE sequoia.fiber_incidents
    UPDATE tags = [severity] WHERE length(tags) = 0;

-- ============================================================================
-- 3. Index for efficient tag filtering (has(tags, 'critical') etc.)
-- ============================================================================

ALTER TABLE sequoia.fiber_incidents
    ADD INDEX IF NOT EXISTS idx_tags (tags) TYPE bloom_filter GRANULARITY 1;

-- ============================================================================
-- 4. Drop severity column and its index
-- ============================================================================

ALTER TABLE sequoia.fiber_incidents DROP INDEX IF EXISTS idx_severity;
ALTER TABLE sequoia.fiber_incidents DROP COLUMN IF EXISTS severity;

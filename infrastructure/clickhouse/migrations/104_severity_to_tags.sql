-- Migration 104: Replace severity enum with tags array on fiber_incidents.
--
-- The DEFAULT [severity] expression auto-populates tags from the existing
-- severity column for historical rows — no backfill UPDATE required.
-- Safe to run before code deploy.

-- ============================================================================
-- 1. Add tags column with auto-population from severity
-- ============================================================================

ALTER TABLE sequoia.fiber_incidents
    ADD COLUMN IF NOT EXISTS tags Array(String) DEFAULT [severity] CODEC(ZSTD(1));

-- ============================================================================
-- 2. Index for efficient tag filtering (has(tags, 'critical') etc.)
-- ============================================================================

ALTER TABLE sequoia.fiber_incidents
    ADD INDEX IF NOT EXISTS idx_tags (tags) TYPE bloom_filter GRANULARITY 1;

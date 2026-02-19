-- ============================================================================
-- Sequoia Retention Policy - Simplified 3-Tier Architecture
-- ============================================================================
-- With the new 3-tier architecture, retention is handled automatically by
-- ClickHouse TTL on each table:
--
--   speed_hires / count_hires: 48 hours (TTL ts + INTERVAL 48 HOUR)
--   speed_1m / count_1m:       90 days  (TTL ts + INTERVAL 90 DAY)
--   speed_1h / count_1h:       Forever  (no TTL)
--
-- Manual retention scripts are NO LONGER NEEDED for data tables.
-- ============================================================================

-- ============================================================================
-- STORAGE MONITORING VIEW
-- ============================================================================
-- Updated for new unified table names

CREATE OR REPLACE VIEW sequoia.storage_by_resolution AS
-- High-resolution data (48h TTL)
SELECT
    'speed_hires' AS data_type,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS disk_size
FROM system.parts
WHERE database = 'sequoia'
AND table = 'speed_hires'
AND active = 1

UNION ALL

SELECT
    'count_hires' AS data_type,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS disk_size
FROM system.parts
WHERE database = 'sequoia'
AND table = 'count_hires'
AND active = 1

UNION ALL

-- 1-minute aggregation (90 days TTL)
SELECT
    'speed_1m' AS data_type,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS disk_size
FROM system.parts
WHERE database = 'sequoia'
AND table = 'speed_1m'
AND active = 1

UNION ALL

SELECT
    'count_1m' AS data_type,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS disk_size
FROM system.parts
WHERE database = 'sequoia'
AND table = 'count_1m'
AND active = 1

UNION ALL

-- 1-hour aggregation (forever)
SELECT
    'speed_1h' AS data_type,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS disk_size
FROM system.parts
WHERE database = 'sequoia'
AND table = 'speed_1h'
AND active = 1

UNION ALL

SELECT
    'count_1h' AS data_type,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS disk_size
FROM system.parts
WHERE database = 'sequoia'
AND table = 'count_1h'
AND active = 1;

-- ============================================================================
-- INCIDENT DATA PRESERVATION
-- ============================================================================
-- Incidents now need to be handled differently. Since high-res data has 48h TTL,
-- if we want to preserve data around incidents for longer, we have two options:
--
-- Option 1: Accept that old incidents only have 1m/1h resolution data
--           (This is the simplest and usually sufficient for analysis)
--
-- Option 2: Create a dedicated incident_data_snapshots table that stores
--           high-res data for incident windows at the time of detection
--
-- For now, we use Option 1 - the aggregated data at 1m and 1h resolution
-- provides sufficient context for incident investigation.

-- ============================================================================
-- SUCCESS
-- ============================================================================
SELECT 'Schema 07: Retention policy simplified (TTL-based)' as status;
SELECT '  speed_hires/count_hires: 48h TTL (automatic cleanup)' as info;
SELECT '  speed_1m/count_1m: 90 day TTL (automatic cleanup)' as info;
SELECT '  speed_1h/count_1h: Forever (no TTL)' as info;


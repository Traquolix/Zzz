-- Migration 005: Storage monitoring view
-- Extracted from init/07_retention_policy.sql for deploy-time idempotent migrations.
--
-- Retention is handled automatically by ClickHouse TTL on each table:
--   detection_hires: 48 hours
--   detection_1m:    90 days
--   detection_1h:    forever

CREATE OR REPLACE VIEW ${CH_DATABASE}.storage_by_resolution AS
SELECT
    'detection_hires' AS data_type,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS disk_size
FROM system.parts
WHERE database = '${CH_DATABASE}'
AND table = 'detection_hires'
AND active = 1

UNION ALL

SELECT
    'detection_1m' AS data_type,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS disk_size
FROM system.parts
WHERE database = '${CH_DATABASE}'
AND table = 'detection_1m'
AND active = 1

UNION ALL

SELECT
    'detection_1h' AS data_type,
    sum(rows) AS total_rows,
    formatReadableSize(sum(bytes_on_disk)) AS disk_size
FROM system.parts
WHERE database = '${CH_DATABASE}'
AND table = 'detection_1h'
AND active = 1;

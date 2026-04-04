-- ============================================================================
-- Read-only ClickHouse user for Grafana dashboards
-- ============================================================================
-- Principle of least privilege: Grafana only needs SELECT on sequoia tables
-- and system.parts (for storage monitoring view).
--
-- IMPORTANT: This password must match CLICKHOUSE_GRAFANA_PASSWORD in .env.
-- ClickHouse init scripts don't support env var interpolation, so if you
-- change the password in .env, also run:
--   ALTER USER grafana_readonly IDENTIFIED BY 'your_new_password';
-- ============================================================================

CREATE USER IF NOT EXISTS grafana_readonly
    IDENTIFIED WITH sha256_password BY 'CHANGE_ME_GRAFANA'
    DEFAULT DATABASE sequoia;

GRANT SELECT ON ${CH_DATABASE}.* TO grafana_readonly;
GRANT SELECT ON system.parts TO grafana_readonly;

SELECT 'Schema 09: Read-only Grafana user created' as status;

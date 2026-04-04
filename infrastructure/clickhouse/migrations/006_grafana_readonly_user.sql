-- Migration 006: Read-only ClickHouse user for Grafana dashboards
-- Extracted from init/10_grafana_readonly_user.sql for deploy-time idempotent migrations.
--
-- IMPORTANT: This password must match CLICKHOUSE_GRAFANA_PASSWORD in .env.
-- If you change the password, also run:
--   ALTER USER grafana_readonly IDENTIFIED BY 'your_new_password';

CREATE USER IF NOT EXISTS grafana_readonly
    IDENTIFIED WITH sha256_password BY 'CHANGE_ME_GRAFANA'
    DEFAULT DATABASE sequoia;

GRANT SELECT ON ${CH_DATABASE}.* TO grafana_readonly;
GRANT SELECT ON system.parts TO grafana_readonly;

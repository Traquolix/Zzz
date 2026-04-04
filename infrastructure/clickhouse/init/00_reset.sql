-- ============================================================================
-- DEV ONLY: Drop old tables for clean schema re-creation
-- ============================================================================
-- This file is for development resets only. Do NOT include in production init.
-- It drops legacy per-fiber tables and current tables to allow 02_sampling_tables.sql
-- to recreate everything from scratch.
-- ============================================================================

-- Drop old per-fiber speed tables
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s_promenade_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s_promenade;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s_carros_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s_carros;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s_mathis_raw_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s_mathis_raw;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s_mathis_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s_mathis;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_100ms_promenade_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_100ms_promenade;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_100ms_carros_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_100ms_carros;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_100ms_mathis_raw_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_100ms_mathis_raw;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_100ms_mathis_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_100ms_mathis;

-- Drop old combined speed tables
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_1h_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_1h;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_30m_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_30m;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_5m_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_5m;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_1m_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_1m;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_30s_promenade_mv;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_30s_carros_mv;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_30s_mathis_raw_mv;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_30s_mathis_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_30s;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data_1s;

-- Drop old raw speed table
DROP VIEW IF EXISTS ${CH_DATABASE}.speed_points_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_speed_data;

-- Drop old per-fiber count tables
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_1s_promenade_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_count_data_1s_promenade;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_1s_carros_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_count_data_1s_carros;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_1s_mathis_raw_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_count_data_1s_mathis_raw;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_1s_mathis_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_count_data_1s_mathis;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_100ms_promenade_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_count_data_100ms_promenade;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_100ms_carros_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_count_data_100ms_carros;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_100ms_mathis_raw_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_count_data_100ms_mathis_raw;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_100ms_mathis_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_count_data_100ms_mathis;

-- Drop old combined count tables
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_vehicle_counts_1h_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_vehicle_counts_1h;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_vehicle_counts_30m_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_vehicle_counts_30m;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_vehicle_counts_5m_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_vehicle_counts_5m;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_vehicle_counts_1m_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_vehicle_counts_1m;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_30s_promenade_mv;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_30s_carros_mv;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_30s_mathis_raw_mv;
DROP VIEW IF EXISTS ${CH_DATABASE}.fiber_count_data_30s_mathis_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_count_data_30s;

-- Drop old raw count table
DROP VIEW IF EXISTS ${CH_DATABASE}.vehicle_counts_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.fiber_vehicle_counts;

-- Drop old Kafka tables
DROP VIEW IF EXISTS ${CH_DATABASE}.speed_kafka_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.speed_kafka;
DROP VIEW IF EXISTS ${CH_DATABASE}.count_kafka_mv;
DROP TABLE IF EXISTS ${CH_DATABASE}.count_kafka;
DROP TABLE IF EXISTS ${CH_DATABASE}.speed_points_kafka;
DROP TABLE IF EXISTS ${CH_DATABASE}.speed_points_kafka_segment_a;
DROP TABLE IF EXISTS ${CH_DATABASE}.speed_points_kafka_segment_b;
DROP TABLE IF EXISTS ${CH_DATABASE}.vehicle_counts_kafka;
DROP TABLE IF EXISTS ${CH_DATABASE}.vehicle_counts_kafka_segment_a;
DROP TABLE IF EXISTS ${CH_DATABASE}.vehicle_counts_kafka_segment_b;

SELECT 'Schema 00: Old tables dropped (dev reset)' as status;

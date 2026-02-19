-- ============================================================================
-- Sequoia Kafka Stream Processors - Unified Multi-Fiber Architecture
-- ============================================================================
-- Single Kafka consumers for all fibers. The unified topics (das.speeds,
-- das.counts) are partitioned by fiber_id for horizontal scaling.
--
-- Data flow:
--   das.speeds → speed_kafka → speed_hires (48h TTL)
--   das.counts   → count_kafka → count_hires (48h TTL)
--
-- Adding a new fiber requires NO changes here - just add to fiber_cables table!
-- ============================================================================

-- ============================================================================
-- DROP OLD KAFKA TABLES (Complete cleanup of legacy per-fiber architecture)
-- ============================================================================

-- Drop old MVs first (they depend on Kafka tables)
DROP VIEW IF EXISTS sequoia.speed_data_processor;
DROP VIEW IF EXISTS sequoia.speed_data_processor_segment_a;
DROP VIEW IF EXISTS sequoia.speed_data_processor_segment_b;
DROP VIEW IF EXISTS sequoia.vehicle_counts_processor;
DROP VIEW IF EXISTS sequoia.vehicle_counts_processor_segment_a;
DROP VIEW IF EXISTS sequoia.vehicle_counts_processor_segment_b;

-- Drop old Kafka tables
DROP TABLE IF EXISTS sequoia.speed_points_kafka;
DROP TABLE IF EXISTS sequoia.speed_points_kafka_segment_a;
DROP TABLE IF EXISTS sequoia.speed_points_kafka_segment_b;
DROP TABLE IF EXISTS sequoia.vehicle_counts_kafka;
DROP TABLE IF EXISTS sequoia.vehicle_counts_kafka_segment_a;
DROP TABLE IF EXISTS sequoia.vehicle_counts_kafka_segment_b;

-- Drop any new tables if they exist (for re-runs)
DROP VIEW IF EXISTS sequoia.speed_kafka_mv;
DROP VIEW IF EXISTS sequoia.count_kafka_mv;
DROP TABLE IF EXISTS sequoia.speed_kafka;
DROP TABLE IF EXISTS sequoia.count_kafka;

-- ============================================================================
-- SPEED DATA - Unified Kafka Consumer
-- ============================================================================
-- Single consumer for all fibers. Messages are partitioned by fiber_id in Kafka,
-- ensuring same fiber always goes to same partition for ordering guarantees.

CREATE TABLE sequoia.speed_kafka
(
    fiber_id String,
    timestamp_ns UInt64,
    speeds Array(Tuple(channel_number UInt32, speed Float32)),
    channel_start UInt32,
    ai_metadata Tuple(engine_version String, spatial_points UInt32, time_index UInt32)
)
ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'das.speeds',
    kafka_group_name = 'clickhouse_speed_consumer',
    kafka_format = 'AvroConfluent',
    format_avro_schema_registry_url = 'http://schema-registry:8081',
    kafka_num_consumers = 3;

-- MV: Kafka → speed_hires
-- ARRAY JOIN unpacks the speeds array into individual rows
-- LEFT JOIN adds coordinates from fiber_cables configuration
CREATE MATERIALIZED VIEW sequoia.speed_kafka_mv TO sequoia.speed_hires AS
SELECT
    s.fiber_id AS fiber_id,
    fromUnixTimestamp64Nano(s.timestamp_ns) AS ts,
    toUInt16(speed_tuple.channel_number) AS ch,
    speed_tuple.speed AS speed,
    CAST(arrayElement(c.channel_coordinates, speed_tuple.channel_number + 1).1 AS Nullable(Float64)) AS lng,
    CAST(arrayElement(c.channel_coordinates, speed_tuple.channel_number + 1).2 AS Nullable(Float64)) AS lat
FROM sequoia.speed_kafka s
LEFT JOIN sequoia.fiber_cables c ON s.fiber_id = c.fiber_id
ARRAY JOIN s.speeds AS speed_tuple;

-- ============================================================================
-- COUNT DATA - Unified Kafka Consumer
-- ============================================================================
-- Single consumer for all fibers. Vehicle counts from AI engine.

CREATE TABLE sequoia.count_kafka
(
    fiber_id String,
    channel_start UInt32,
    channel_end UInt32,
    count_timestamp_ns UInt64,
    vehicle_count Float32,
    engine_version String,
    model_type String
)
ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'das.counts',
    kafka_group_name = 'clickhouse_count_consumer',
    kafka_format = 'AvroConfluent',
    format_avro_schema_registry_url = 'http://schema-registry:8081',
    kafka_num_consumers = 2;

-- MV: Kafka → count_hires
CREATE MATERIALIZED VIEW sequoia.count_kafka_mv TO sequoia.count_hires AS
SELECT
    fiber_id,
    fromUnixTimestamp64Nano(count_timestamp_ns) AS ts,
    toUInt16(channel_start) AS ch_start,
    toUInt16(channel_end) AS ch_end,
    vehicle_count AS count
FROM sequoia.count_kafka;

-- ============================================================================
-- SUCCESS
-- ============================================================================
SELECT 'Schema 03: Kafka processors created (2 consumers + 2 MVs)' as status;
SELECT '  Speed: das.speeds → speed_kafka → speed_hires' as info;
SELECT '  Count: das.counts → count_kafka → count_hires' as info;


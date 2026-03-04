-- ============================================================================
-- Sequoia Kafka Stream Processors - Unified Detection Architecture
-- ============================================================================
-- Single Kafka consumer for all fibers. The unified topic (das.detections)
-- is partitioned by fiber_id for horizontal scaling.
--
-- Data flow:
--   das.detections → detection_kafka → detection_hires (48h TTL)
--
-- Adding a new fiber requires NO changes here - just add to fiber_cables table!
-- ============================================================================

-- ============================================================================
-- DROP OLD TABLES (Complete cleanup of legacy architecture)
-- ============================================================================

-- Drop legacy per-fiber MVs and tables
DROP VIEW IF EXISTS sequoia.speed_data_processor;
DROP VIEW IF EXISTS sequoia.speed_data_processor_segment_a;
DROP VIEW IF EXISTS sequoia.speed_data_processor_segment_b;
DROP VIEW IF EXISTS sequoia.vehicle_counts_processor;
DROP VIEW IF EXISTS sequoia.vehicle_counts_processor_segment_a;
DROP VIEW IF EXISTS sequoia.vehicle_counts_processor_segment_b;

DROP TABLE IF EXISTS sequoia.speed_points_kafka;
DROP TABLE IF EXISTS sequoia.speed_points_kafka_segment_a;
DROP TABLE IF EXISTS sequoia.speed_points_kafka_segment_b;
DROP TABLE IF EXISTS sequoia.vehicle_counts_kafka;
DROP TABLE IF EXISTS sequoia.vehicle_counts_kafka_segment_a;
DROP TABLE IF EXISTS sequoia.vehicle_counts_kafka_segment_b;

-- Drop previous split speed/count consumers
DROP VIEW IF EXISTS sequoia.speed_kafka_mv;
DROP VIEW IF EXISTS sequoia.count_kafka_mv;
DROP TABLE IF EXISTS sequoia.speed_kafka;
DROP TABLE IF EXISTS sequoia.count_kafka;

-- Drop unified detection tables if they exist (for re-runs)
DROP VIEW IF EXISTS sequoia.detection_kafka_mv;
DROP TABLE IF EXISTS sequoia.detection_kafka;

-- ============================================================================
-- UNIFIED DETECTION - Kafka Consumer
-- ============================================================================
-- Single consumer for all fibers. Each message = one detection interval with
-- speed, vehicle count, car/truck classification.

CREATE TABLE sequoia.detection_kafka
(
    fiber_id String,
    timestamp_ns UInt64,
    channel UInt32,
    speed_kmh Float32,
    direction UInt8 DEFAULT 0,
    vehicle_count Float32 DEFAULT 1,
    n_cars Float32 DEFAULT 0,
    n_trucks Float32 DEFAULT 0,
    glrt_max Float32 DEFAULT 0,
    engine_version String DEFAULT '1.0'
)
ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'das.detections',
    kafka_group_name = 'clickhouse_detection_consumer',
    kafka_format = 'AvroConfluent',
    format_avro_schema_registry_url = 'http://schema-registry:8081',
    kafka_num_consumers = 3;

-- MV: Kafka → detection_hires
-- LEFT JOIN adds coordinates from fiber_cables configuration
CREATE MATERIALIZED VIEW sequoia.detection_kafka_mv TO sequoia.detection_hires AS
SELECT
    d.fiber_id AS fiber_id,
    fromUnixTimestamp64Nano(d.timestamp_ns) AS ts,
    toUInt16(d.channel) AS ch,
    d.direction AS direction,
    d.speed_kmh AS speed,
    d.vehicle_count AS vehicle_count,
    d.n_cars AS n_cars,
    d.n_trucks AS n_trucks,
    CAST(arrayElement(c.channel_coordinates, d.channel + 1).1 AS Nullable(Float64)) AS lng,
    CAST(arrayElement(c.channel_coordinates, d.channel + 1).2 AS Nullable(Float64)) AS lat
FROM sequoia.detection_kafka d
LEFT JOIN sequoia.fiber_cables c ON d.fiber_id = c.fiber_id;

-- ============================================================================
-- SUCCESS
-- ============================================================================
SELECT 'Schema 03: Kafka processors created (1 consumer + 1 MV)' as status;
SELECT '  das.detections → detection_kafka → detection_hires' as info;

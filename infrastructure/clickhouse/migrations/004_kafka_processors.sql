-- Migration 004: Kafka stream processor for unified detections
-- Extracted from init/03_kafka_processors.sql for deploy-time idempotent migrations.
--
-- Data flow: das.detections -> detection_kafka -> detection_hires (48h TTL)
--
-- NOTE: Kafka engine tables don't support IF NOT EXISTS well (settings can't
-- be altered). We use DROP IF EXISTS + CREATE which is safe because Kafka
-- engine tables are stateless — they just define a consumer position.
-- The consumer group offset is stored in Kafka, not in ClickHouse.

-- Drop legacy per-fiber Kafka tables (from before unified architecture)
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

-- Recreate unified detection consumer
DROP VIEW IF EXISTS sequoia.detection_kafka_mv;
DROP TABLE IF EXISTS sequoia.detection_kafka;

CREATE TABLE sequoia.detection_kafka
(
    fiber_id String,
    engine_version String,
    `detections.timestamp_ns` Array(UInt64),
    `detections.channel` Array(UInt32),
    `detections.speed_kmh` Array(Float32),
    `detections.direction` Array(UInt8),
    `detections.vehicle_count` Array(Float32),
    `detections.n_cars` Array(Float32),
    `detections.n_trucks` Array(Float32),
    `detections.glrt_max` Array(Float32)
)
ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'das.detections',
    kafka_group_name = 'clickhouse_detection_consumer',
    kafka_format = 'AvroConfluent',
    format_avro_schema_registry_url = 'http://schema-registry:8081',
    kafka_num_consumers = 3;

-- MV: Kafka -> detection_hires (ARRAY JOIN flattens batched detections)
CREATE MATERIALIZED VIEW sequoia.detection_kafka_mv TO sequoia.detection_hires AS
SELECT
    d.fiber_id AS fiber_id,
    fromUnixTimestamp64Nano(det_ts) AS ts,
    toUInt16(det_ch) AS ch,
    det_dir AS direction,
    det_speed AS speed,
    det_vcount AS vehicle_count,
    det_ncars AS n_cars,
    det_ntrucks AS n_trucks,
    CAST(arrayElement(c.channel_coordinates, det_ch + 1).1 AS Nullable(Float64)) AS lng,
    CAST(arrayElement(c.channel_coordinates, det_ch + 1).2 AS Nullable(Float64)) AS lat
FROM sequoia.detection_kafka d
ARRAY JOIN
    `detections.timestamp_ns` AS det_ts,
    `detections.channel` AS det_ch,
    `detections.speed_kmh` AS det_speed,
    `detections.direction` AS det_dir,
    `detections.vehicle_count` AS det_vcount,
    `detections.n_cars` AS det_ncars,
    `detections.n_trucks` AS det_ntrucks
LEFT JOIN sequoia.fiber_cables c ON d.fiber_id = c.fiber_id;

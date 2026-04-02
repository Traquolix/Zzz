-- Migration 103: Add strain_peak and strain_rms columns to detection_hires,
-- and recreate Kafka consumer + MV to include the new fields.
--
-- Safe to run before code deploy (existing messages have Avro defaults of 0.0).

-- ============================================================================
-- 1. Add strain columns to detection_hires
-- ============================================================================

ALTER TABLE sequoia.detection_hires
    ADD COLUMN IF NOT EXISTS strain_peak Float32 DEFAULT 0 CODEC(Gorilla);

ALTER TABLE sequoia.detection_hires
    ADD COLUMN IF NOT EXISTS strain_rms Float32 DEFAULT 0 CODEC(Gorilla);

-- ============================================================================
-- 2. Recreate Kafka consumer + MV to include strain fields
-- ============================================================================
-- Kafka engine tables are stateless (consumer offsets live in Kafka).
-- DROP + CREATE is the standard approach for schema changes.

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
    `detections.glrt_max` Array(Float32),
    `detections.strain_peak` Array(Float32),
    `detections.strain_rms` Array(Float32)
)
ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'das.detections',
    kafka_group_name = 'clickhouse_detection_consumer',
    kafka_format = 'AvroConfluent',
    format_avro_schema_registry_url = 'http://schema-registry:8081',
    kafka_num_consumers = 3;

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
    CAST(arrayElement(c.channel_coordinates, det_ch + 1).2 AS Nullable(Float64)) AS lat,
    det_strain_peak AS strain_peak,
    det_strain_rms AS strain_rms
FROM sequoia.detection_kafka d
ARRAY JOIN
    `detections.timestamp_ns` AS det_ts,
    `detections.channel` AS det_ch,
    `detections.speed_kmh` AS det_speed,
    `detections.direction` AS det_dir,
    `detections.vehicle_count` AS det_vcount,
    `detections.n_cars` AS det_ncars,
    `detections.n_trucks` AS det_ntrucks,
    `detections.strain_peak` AS det_strain_peak,
    `detections.strain_rms` AS det_strain_rms
LEFT JOIN sequoia.fiber_cables c ON d.fiber_id = c.fiber_id;

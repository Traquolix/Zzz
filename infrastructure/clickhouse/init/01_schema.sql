-- ============================================================================
-- Sequoia Database Schema - Multi-Fiber Architecture
-- ============================================================================
-- Configuration tables for the fiber optic monitoring system.
-- Data tables are defined in 02_sampling_tables.sql (3-tier architecture).
-- Run order: 01_schema.sql -> 02_sampling_tables.sql -> 03_kafka_processors.sql
-- ============================================================================

-- ============================================================================
-- DATABASE
-- ============================================================================
CREATE DATABASE IF NOT EXISTS sequoia;

-- ============================================================================
-- FIBER CABLES CONFIGURATION
-- ============================================================================
-- Geographic configuration of fiber optic cables.
-- To add a new fiber: INSERT into this table with fiber_id and coordinates.
-- No other infrastructure changes needed!
CREATE TABLE IF NOT EXISTS sequoia.fiber_cables
(
    fiber_id String CODEC(ZSTD(1)),
    fiber_name String CODEC(ZSTD(1)),
    channel_coordinates Array(Tuple(Nullable(Float64), Nullable(Float64))) CODEC(ZSTD(3)),
    color String DEFAULT '#000000' CODEC(ZSTD(1)),
    landmark_labels Array(Nullable(String)) CODEC(ZSTD(3)),
    updated_at DateTime DEFAULT now() CODEC(DoubleDelta, LZ4)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY fiber_id
COMMENT 'Geographic configuration of fiber optic cables';

-- ============================================================================
-- INCIDENTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS sequoia.fiber_incidents
(
    -- Identification
    incident_id String CODEC(ZSTD(1)),
    fiber_id String CODEC(ZSTD(1)),
    direction UInt8 DEFAULT 0 CODEC(LZ4),

    -- Time
    timestamp_ns UInt64 CODEC(DoubleDelta, LZ4),
    timestamp DateTime MATERIALIZED fromUnixTimestamp64Nano(timestamp_ns) CODEC(DoubleDelta, LZ4),

    -- Location
    channel_start UInt32 CODEC(LZ4),
    channel_end UInt32 CODEC(LZ4),

    -- Classification
    incident_type Enum8('accident' = 1, 'congestion' = 2, 'anomaly' = 3, 'slowdown' = 4) CODEC(ZSTD(1)),
    severity Enum8('critical' = 1, 'high' = 2, 'medium' = 3, 'low' = 4) CODEC(ZSTD(1)),

    -- Detection metadata
    speed_before_kmh Nullable(Float32) CODEC(Gorilla),
    speed_during_kmh Nullable(Float32) CODEC(Gorilla),
    speed_drop_percent Float32 CODEC(Gorilla),
    duration_seconds UInt32 CODEC(LZ4),

    -- Workflow
    status Enum8('active' = 1, 'investigating' = 2, 'resolved' = 3, 'false_positive' = 4) DEFAULT 'active' CODEC(ZSTD(1)),

    -- Version key for ReplacingMergeTree
    updated_at DateTime DEFAULT now() CODEC(DoubleDelta, LZ4)
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (fiber_id, timestamp_ns, incident_id)
SETTINGS index_granularity = 8192
COMMENT 'Incident detection events';

-- Incident indexes
ALTER TABLE sequoia.fiber_incidents ADD INDEX IF NOT EXISTS idx_incident_id (incident_id) TYPE bloom_filter GRANULARITY 1;
ALTER TABLE sequoia.fiber_incidents ADD INDEX IF NOT EXISTS idx_location (channel_start, channel_end) TYPE minmax GRANULARITY 4;
ALTER TABLE sequoia.fiber_incidents ADD INDEX IF NOT EXISTS idx_status (status) TYPE set(10) GRANULARITY 1;
ALTER TABLE sequoia.fiber_incidents ADD INDEX IF NOT EXISTS idx_type (incident_type) TYPE set(10) GRANULARITY 1;
ALTER TABLE sequoia.fiber_incidents ADD INDEX IF NOT EXISTS idx_severity (severity) TYPE set(10) GRANULARITY 1;

-- ============================================================================
-- SUCCESS
-- ============================================================================
SELECT 'Schema 01: Configuration tables created (fiber_cables, fiber_incidents)' as status;

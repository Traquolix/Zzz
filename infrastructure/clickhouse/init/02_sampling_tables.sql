-- ============================================================================
-- Sequoia Data Tables - Unified Detection Architecture
-- ============================================================================
-- Multi-fiber unified tables with automatic TTL-based retention.
-- All fibers share the same tables, partitioned by (fiber_id, date).
--
-- Each row = one detection interval from the AI engine, carrying:
--   speed, vehicle_count, n_cars, n_trucks, strain_peak, strain_rms, coordinates
--
-- TIERS:
--   1. detection_hires  - High-resolution (48h TTL)
--   2. detection_1m     - 1-minute aggregation (90 days TTL)
--   3. detection_1h     - 1-hour aggregation (forever)
--
-- Adding a new fiber requires NO changes here - fiber_cables is synced
-- from JSON by `manage.py sync_fiber_data` on startup.
-- ============================================================================

-- ============================================================================
-- DETECTION DATA - 3-Tier Architecture
-- ============================================================================

-- Tier 1: High-resolution detection data (interval-based detections)
-- Each row = one detection interval: speed + vehicle count + car/truck at a
-- specific channel and timestamp.
-- Partitioned by (fiber_id, date) for efficient per-fiber queries and TTL.
-- ORDER BY includes direction to prevent forward/reverse collisions in
-- ReplacingMergeTree — two vehicles at the same (ts, ch) but different
-- directions are distinct detections.
CREATE TABLE IF NOT EXISTS ${CH_DATABASE}.detection_hires
(
    fiber_id LowCardinality(String) CODEC(ZSTD(1)),
    ts DateTime64(1) CODEC(DoubleDelta),
    ch UInt16 CODEC(LZ4),
    direction UInt8 DEFAULT 0 CODEC(LZ4),
    speed Float32 CODEC(Gorilla),
    vehicle_count Float32 DEFAULT 1 CODEC(Gorilla),
    n_cars Float32 DEFAULT 0 CODEC(Gorilla),
    n_trucks Float32 DEFAULT 0 CODEC(Gorilla),
    lng Nullable(Float64) CODEC(Gorilla),
    lat Nullable(Float64) CODEC(Gorilla),
    strain_peak Float32 DEFAULT 0 CODEC(Gorilla),
    strain_rms Float32 DEFAULT 0 CODEC(Gorilla)
)
ENGINE = ReplacingMergeTree()
PARTITION BY (fiber_id, toYYYYMMDD(ts))
ORDER BY (fiber_id, ts, ch, direction)
TTL toDateTime(ts) + INTERVAL 48 HOUR
SETTINGS index_granularity = 4096
COMMENT 'High-resolution detection data (interval detections). TTL: 48 hours';

-- Add indexes for common query patterns
ALTER TABLE ${CH_DATABASE}.detection_hires ADD INDEX IF NOT EXISTS idx_speed (speed) TYPE minmax GRANULARITY 4;

-- Tier 2: 1-minute aggregated detection data
-- Uses AggregatingMergeTree so partial-batch inserts from the MV merge correctly.
--
-- QUERYING: Use -Merge combinators to finalize:
--   SELECT fiber_id, ts, ch, direction,
--          maxMerge(speed_max_state) AS speed_max,
--          avgMerge(speed_avg_state) AS speed_avg,
--          minMerge(speed_min_state) AS speed_min,
--          sumMerge(count_sum_state) AS vehicle_count,
--          sumMerge(cars_sum_state)  AS n_cars,
--          sumMerge(trucks_sum_state) AS n_trucks,
--          sumMerge(samples_state)   AS samples
--   FROM detection_1m
--   GROUP BY fiber_id, ts, ch, direction
CREATE TABLE IF NOT EXISTS ${CH_DATABASE}.detection_1m
(
    fiber_id LowCardinality(String) CODEC(ZSTD(1)),
    ts DateTime CODEC(DoubleDelta),
    ch UInt16 CODEC(LZ4),
    direction UInt8 DEFAULT 0 CODEC(LZ4),
    speed_max_state AggregateFunction(max, Float32),
    speed_avg_state AggregateFunction(avg, Float32),
    speed_min_state AggregateFunction(min, Float32),
    count_sum_state AggregateFunction(sum, Float32),
    cars_sum_state AggregateFunction(sum, Float32),
    trucks_sum_state AggregateFunction(sum, Float32),
    samples_state AggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (fiber_id, ts, ch, direction)
TTL ts + INTERVAL 90 DAY
COMMENT '1-minute aggregated detection data (AggregatingMergeTree). TTL: 90 days';

-- Tier 3: 1-hour aggregated detection data (forever)
CREATE TABLE IF NOT EXISTS ${CH_DATABASE}.detection_1h
(
    fiber_id LowCardinality(String) CODEC(ZSTD(1)),
    ts DateTime CODEC(DoubleDelta),
    ch UInt16 CODEC(LZ4),
    direction UInt8 DEFAULT 0 CODEC(LZ4),
    speed_max_state AggregateFunction(max, Float32),
    speed_avg_state AggregateFunction(avg, Float32),
    speed_min_state AggregateFunction(min, Float32),
    count_sum_state AggregateFunction(sum, Float32),
    cars_sum_state AggregateFunction(sum, Float32),
    trucks_sum_state AggregateFunction(sum, Float32),
    samples_state AggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (fiber_id, ts, ch, direction)
COMMENT '1-hour aggregated detection data (AggregatingMergeTree). Permanent storage';

-- MV: detection_hires → detection_1m
-- Uses -State combinators to produce intermediate aggregate states
CREATE MATERIALIZED VIEW IF NOT EXISTS ${CH_DATABASE}.detection_1m_mv TO ${CH_DATABASE}.detection_1m AS
SELECT
    src.fiber_id AS fiber_id,
    toStartOfMinute(src.ts) AS ts,
    src.ch AS ch,
    src.direction AS direction,
    maxState(src.speed) AS speed_max_state,
    avgState(src.speed) AS speed_avg_state,
    minState(src.speed) AS speed_min_state,
    sumState(src.vehicle_count) AS count_sum_state,
    sumState(src.n_cars) AS cars_sum_state,
    sumState(src.n_trucks) AS trucks_sum_state,
    sumState(toUInt64(1)) AS samples_state
FROM ${CH_DATABASE}.detection_hires AS src
GROUP BY src.fiber_id, toStartOfMinute(src.ts), src.ch, src.direction;

-- MV: detection_1m → detection_1h
-- Merges 1m states into 1h states using -Merge + -State round-trip
CREATE MATERIALIZED VIEW IF NOT EXISTS ${CH_DATABASE}.detection_1h_mv TO ${CH_DATABASE}.detection_1h AS
SELECT
    src.fiber_id AS fiber_id,
    toStartOfHour(src.ts) AS ts,
    src.ch AS ch,
    src.direction AS direction,
    maxMergeState(src.speed_max_state) AS speed_max_state,
    avgMergeState(src.speed_avg_state) AS speed_avg_state,
    minMergeState(src.speed_min_state) AS speed_min_state,
    sumMergeState(src.count_sum_state) AS count_sum_state,
    sumMergeState(src.cars_sum_state) AS cars_sum_state,
    sumMergeState(src.trucks_sum_state) AS trucks_sum_state,
    sumMergeState(src.samples_state) AS samples_state
FROM ${CH_DATABASE}.detection_1m AS src
GROUP BY src.fiber_id, toStartOfHour(src.ts), src.ch, src.direction;

-- ============================================================================
-- SUCCESS
-- ============================================================================
SELECT 'Schema 02: Detection tables created (3 tables + 2 MVs)' as status;
SELECT '  detection_hires (48h) → detection_1m (90d) → detection_1h (forever)' as info;

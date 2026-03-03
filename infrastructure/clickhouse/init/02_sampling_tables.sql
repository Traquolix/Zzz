-- ============================================================================
-- Sequoia Data Tables - Simplified 3-Tier Architecture
-- ============================================================================
-- Multi-fiber unified tables with automatic TTL-based retention.
-- All fibers share the same tables, partitioned by (fiber_id, date).
--
-- TIERS:
--   1. speed_hires / count_hires - High-resolution (48h TTL)
--   2. speed_1m / count_1m       - 1-minute aggregation (90 days TTL)
--   3. speed_1h / count_1h       - 1-hour aggregation (forever)
--
-- Adding a new fiber requires NO changes here - just add to fiber_cables table!
-- NOTE: DROP statements for legacy tables live in 00_reset.sql (dev-only).
-- ============================================================================

-- ============================================================================
-- SPEED DATA - 3-Tier Architecture
-- ============================================================================

-- Tier 1: High-resolution speed data (replaces all 100ms + 1s per-fiber tables)
-- Partitioned by (fiber_id, date) for efficient per-fiber queries and TTL
-- NOTE: ReplacingMergeTree without a version column deduplicates on the full ORDER BY
-- key (fiber_id, ts, ch). This is intentional: at 10Hz sampling, the same
-- (fiber, timestamp, channel) triple should never appear twice in normal operation.
-- Late-arriving duplicates from Kafka retries are simply deduplicated on merge.
CREATE TABLE IF NOT EXISTS sequoia.speed_hires
(
    fiber_id LowCardinality(String) CODEC(ZSTD(1)),
    ts DateTime64(1) CODEC(DoubleDelta),
    ch UInt16 CODEC(LZ4),
    speed Float32 CODEC(Gorilla),
    lng Nullable(Float64) CODEC(Gorilla),
    lat Nullable(Float64) CODEC(Gorilla)
)
ENGINE = ReplacingMergeTree()
PARTITION BY (fiber_id, toYYYYMMDD(ts))
ORDER BY (fiber_id, ts, ch)
TTL toDateTime(ts) + INTERVAL 48 HOUR
SETTINGS index_granularity = 4096
COMMENT 'High-resolution speed data (10Hz). TTL: 48 hours';

-- Add indexes for common query patterns
ALTER TABLE sequoia.speed_hires ADD INDEX IF NOT EXISTS idx_speed (speed) TYPE minmax GRANULARITY 4;

-- Tier 2: 1-minute aggregated speed data
-- Uses AggregatingMergeTree so partial-batch inserts from the MV merge correctly.
-- When data for the same (fiber_id, minute, channel) arrives in multiple Kafka batches,
-- the aggregate states combine on background merge rather than overwriting each other.
--
-- QUERYING: Use -Merge combinators to finalize:
--   SELECT fiber_id, ts, ch,
--          maxMerge(speed_max_state) AS speed_max,
--          avgMerge(speed_avg_state) AS speed_avg,
--          minMerge(speed_min_state) AS speed_min,
--          sumMerge(samples_state)   AS samples
--   FROM speed_1m
--   GROUP BY fiber_id, ts, ch
CREATE TABLE IF NOT EXISTS sequoia.speed_1m
(
    fiber_id LowCardinality(String) CODEC(ZSTD(1)),
    ts DateTime CODEC(DoubleDelta),
    ch UInt16 CODEC(LZ4),
    speed_max_state AggregateFunction(max, Float32),
    speed_avg_state AggregateFunction(avg, Float32),
    speed_min_state AggregateFunction(min, Float32),
    samples_state AggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (fiber_id, ts, ch)
TTL ts + INTERVAL 90 DAY
COMMENT '1-minute aggregated speed data (AggregatingMergeTree). TTL: 90 days';

-- Tier 3: 1-hour aggregated speed data (forever)
CREATE TABLE IF NOT EXISTS sequoia.speed_1h
(
    fiber_id LowCardinality(String) CODEC(ZSTD(1)),
    ts DateTime CODEC(DoubleDelta),
    ch UInt16 CODEC(LZ4),
    speed_max_state AggregateFunction(max, Float32),
    speed_avg_state AggregateFunction(avg, Float32),
    speed_min_state AggregateFunction(min, Float32),
    samples_state AggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (fiber_id, ts, ch)
COMMENT '1-hour aggregated speed data (AggregatingMergeTree). Permanent storage';

-- MV: speed_hires → speed_1m
-- Uses -State combinators to produce intermediate aggregate states
CREATE MATERIALIZED VIEW IF NOT EXISTS sequoia.speed_1m_mv TO sequoia.speed_1m AS
SELECT
    src.fiber_id AS fiber_id,
    toStartOfMinute(src.ts) AS ts,
    src.ch AS ch,
    maxState(src.speed) AS speed_max_state,
    avgState(src.speed) AS speed_avg_state,
    minState(src.speed) AS speed_min_state,
    sumState(toUInt64(1)) AS samples_state
FROM sequoia.speed_hires AS src
GROUP BY src.fiber_id, toStartOfMinute(src.ts), src.ch;

-- MV: speed_1m → speed_1h
-- Merges 1m states into 1h states using -Merge + -State round-trip
CREATE MATERIALIZED VIEW IF NOT EXISTS sequoia.speed_1h_mv TO sequoia.speed_1h AS
SELECT
    src.fiber_id AS fiber_id,
    toStartOfHour(src.ts) AS ts,
    src.ch AS ch,
    maxMergeState(src.speed_max_state) AS speed_max_state,
    avgMergeState(src.speed_avg_state) AS speed_avg_state,
    minMergeState(src.speed_min_state) AS speed_min_state,
    sumMergeState(src.samples_state) AS samples_state
FROM sequoia.speed_1m AS src
GROUP BY src.fiber_id, toStartOfHour(src.ts), src.ch;

-- ============================================================================
-- COUNT DATA - 3-Tier Architecture
-- ============================================================================

-- Tier 1: High-resolution count data
-- NOTE: ORDER BY includes ch_end because the AI engine can produce records with
-- the same (fiber_id, ts, ch_start) but different ch_end values (overlapping
-- detection zones of different lengths). Without ch_end, ReplacingMergeTree
-- would silently deduplicate them on merge, losing vehicle counts.
CREATE TABLE IF NOT EXISTS sequoia.count_hires
(
    fiber_id LowCardinality(String) CODEC(ZSTD(1)),
    ts DateTime64(1) CODEC(DoubleDelta),
    ch_start UInt16 CODEC(LZ4),
    ch_end UInt16 CODEC(LZ4),
    count Float32 CODEC(Gorilla)
)
ENGINE = ReplacingMergeTree()
PARTITION BY (fiber_id, toYYYYMMDD(ts))
ORDER BY (fiber_id, ts, ch_start, ch_end)
TTL toDateTime(ts) + INTERVAL 48 HOUR
COMMENT 'High-resolution vehicle count data. TTL: 48 hours';

-- Tier 2: 1-minute aggregated count data
-- Same AggregatingMergeTree pattern as speed tables.
--
-- QUERYING:
--   SELECT fiber_id, ts, ch_start, ch_end,
--          sumMerge(count_sum_state) AS count_sum,
--          maxMerge(count_max_state) AS count_max,
--          sumMerge(samples_state)   AS samples
--   FROM count_1m
--   GROUP BY fiber_id, ts, ch_start, ch_end
CREATE TABLE IF NOT EXISTS sequoia.count_1m
(
    fiber_id LowCardinality(String) CODEC(ZSTD(1)),
    ts DateTime CODEC(DoubleDelta),
    ch_start UInt16 CODEC(LZ4),
    ch_end UInt16 CODEC(LZ4),
    count_sum_state AggregateFunction(sum, Float32),
    count_max_state AggregateFunction(max, Float32),
    samples_state AggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (fiber_id, ts, ch_start, ch_end)
TTL ts + INTERVAL 90 DAY
COMMENT '1-minute aggregated vehicle count data (AggregatingMergeTree). TTL: 90 days';

-- Tier 3: 1-hour aggregated count data (forever)
CREATE TABLE IF NOT EXISTS sequoia.count_1h
(
    fiber_id LowCardinality(String) CODEC(ZSTD(1)),
    ts DateTime CODEC(DoubleDelta),
    ch_start UInt16 CODEC(LZ4),
    ch_end UInt16 CODEC(LZ4),
    count_sum_state AggregateFunction(sum, Float32),
    count_max_state AggregateFunction(max, Float32),
    samples_state AggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (fiber_id, ts, ch_start, ch_end)
COMMENT '1-hour aggregated vehicle count data (AggregatingMergeTree). Permanent storage';

-- MV: count_hires → count_1m
CREATE MATERIALIZED VIEW IF NOT EXISTS sequoia.count_1m_mv TO sequoia.count_1m AS
SELECT
    src.fiber_id AS fiber_id,
    toStartOfMinute(src.ts) AS ts,
    src.ch_start AS ch_start,
    src.ch_end AS ch_end,
    sumState(src.count) AS count_sum_state,
    maxState(src.count) AS count_max_state,
    sumState(toUInt64(1)) AS samples_state
FROM sequoia.count_hires AS src
GROUP BY src.fiber_id, toStartOfMinute(src.ts), src.ch_start, src.ch_end;

-- MV: count_1m → count_1h
CREATE MATERIALIZED VIEW IF NOT EXISTS sequoia.count_1h_mv TO sequoia.count_1h AS
SELECT
    src.fiber_id AS fiber_id,
    toStartOfHour(src.ts) AS ts,
    src.ch_start AS ch_start,
    src.ch_end AS ch_end,
    sumMergeState(src.count_sum_state) AS count_sum_state,
    maxMergeState(src.count_max_state) AS count_max_state,
    sumMergeState(src.samples_state) AS samples_state
FROM sequoia.count_1m AS src
GROUP BY src.fiber_id, toStartOfHour(src.ts), src.ch_start, src.ch_end;

-- ============================================================================
-- SUCCESS
-- ============================================================================
SELECT 'Schema 02: Data tables created (6 tables + 4 MVs)' as status;
SELECT '  Speed: speed_hires (48h) → speed_1m (90d) → speed_1h (forever)' as info;
SELECT '  Count: count_hires (48h) → count_1m (90d) → count_1h (forever)' as info;

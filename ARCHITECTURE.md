# SequoIA Architecture

## System Topology

```
                        DAS Interrogators
                    (ASN OptoDAS, 125 Hz raw)
                              |
                         port 9092
                              |
    +-------------------------v---------------------------+
    |                     KAFKA (KRaft)                   |
    |  Topics:                                            |
    |    das.raw.<fiber>    (1 partition, Avro, lz4)      |
    |    das.processed      (1 partition, Avro, lz4)      |
    |    das.detections     (1 partition, Avro, lz4)      |
    |    das.dlq            (1 partition, 7d retention)    |
    |                                                     |
    |  Schema Registry (port 8081)                        |
    +---------+-------------------+-----------------------+
              |                   |
              v                   v
    +---------+--------+  +-------+---------+
    |   PROCESSOR      |  |   AI ENGINE     |
    |   (per fiber)    |  |   (per fiber)   |
    |                  |  |                 |
    |   das.raw.*  -->-+->|  das.processed  |
    |   das.processed  |  |  --> das.detections
    |                  |  |  --> ClickHouse  |
    |  Bandpass filter |  |  DTAN model     |
    |  Decimation      |  |  Speed est.     |
    |  CMR             |  |  GLRT counting  |
    |  Normalization   |  |  Classification |
    +------------------+  +-------+---------+
                                  |
            +---------------------+--------------------+
            |                     |                    |
            v                     v                    v
    +-------+--------+   +-------+--------+   +-------+------+
    |   CLICKHOUSE    |   |  DJANGO API    |   |   GRAFANA    |
    |                 |   |  (DRF + ASGI)  |   |  (otel-lgtm) |
    |  detection_     |   |                |   |              |
    |    hires (48h)  |   |  Kafka bridge  |   |  Dashboards  |
    |    1m (90d)     |   |  --> Redis     |   |  Alerting    |
    |    1h (forever) |   |  --> WebSocket |   |  Traces      |
    +-----------------+   |                |   +--------------+
                          |  PostgreSQL    |
                          |  (users, orgs) |
                          +-------+--------+
                                  |
                                  v
                          +-------+--------+
                          |    FRONTEND    |
                          |  (React+Vite)  |
                          |  Mapbox GL     |
                          |  WebSocket     |
                          +----------------+
```

## Services

### Processor (`services/pipeline/processor/`)
- **Consumes:** `das.raw.<fiber_id>` (raw DAS measurements, Avro)
- **Produces:** `das.processed` (filtered/decimated measurements, Avro)
- **Entry point:** `processor/main.py`
- **Pattern:** RollingBufferedTransformer (inherits from ServiceBase)
- **Processing chain:** Bandpass filter → Spatial decimation → Temporal decimation → Common mode removal → Energy normalization
- **One instance per fiber** — configured via `FIBER_ID` env var

### AI Engine (`services/pipeline/ai_engine/`)
- **Consumes:** `das.processed` (filtered by `FIBER_ID`)
- **Produces:** `das.detections` (vehicle detections, Avro) + direct ClickHouse inserts
- **Entry point:** `ai_engine/main.py`
- **Requires:** NVIDIA GPU (CUDA 12.4)
- **Model:** DTAN (Diffeomorphic Temporal Alignment Network) for speed estimation
- **Detection:** GLRT (Generalized Likelihood Ratio Test) for peak counting
- **Classification:** Car vs truck via energy thresholds per section
- **One instance per fiber** — configured via `FIBER_ID` env var

### Backend (`services/platform/backend/`)
- **Consumes:** Kafka `das.detections` via Kafka bridge → Redis channels → WebSocket
- **Produces:** REST API responses, WebSocket real-time events
- **Entry point:** `entrypoint.sh` → `manage.py run_realtime`
- **Framework:** Django 5.2 + DRF + Channels (ASGI via Daphne/Uvicorn)
- **Auth:** JWT RS256 (SimpleJWT) + API key auth
- **Multi-tenant:** Organization-scoped data access
- **Databases:** PostgreSQL (users/orgs/config), ClickHouse (time-series), Redis (cache + channels)

### Frontend (`services/platform/frontend/`)
- **Consumes:** Backend REST API + WebSocket
- **Produces:** Browser UI
- **Framework:** React 19 + Vite + TypeScript
- **Map:** Mapbox GL JS with fiber/section overlays
- **Real-time:** WebSocket for live detection data, waterfall canvas visualization
- **State:** Zustand stores
- **Deployed:** Static build served by nginx (separate server from backend)

## Infrastructure

| Component | Image | Port(s) | Purpose |
|-----------|-------|---------|---------|
| Kafka | cp-kafka:7.8.4 | 9092 (external), 29092 (internal) | Message broker, KRaft mode |
| Schema Registry | cp-schema-registry:7.8.4 | 8081 | Avro schema management |
| PostgreSQL | postgres:16-alpine | 5432 (internal) | Django ORM (users, orgs, fibers) |
| ClickHouse | clickhouse:24.8-alpine | 8123, 9000 (localhost) | Time-series detection data |
| Redis | redis:7-alpine | 6379 (internal) | Django Channels + cache |
| otel-lgtm | grafana/otel-lgtm | 3002→3000 (localhost) | Grafana + Loki + Tempo + Prometheus |
| Kafka UI | kafka-ui | 8080 (localhost) | Kafka topic browser |

## Server Topology

- **Backend server** (IMREDD): Xeon E5-2690 v4, RTX 4000 Ada, 900GB RAM
  - Runs: Kafka, Schema Registry, Processor, AI Engine, ClickHouse, PostgreSQL, Redis, Django backend, Grafana
  - IP: 192.168.99.113 (internal) — `beaujoin@192.168.99.113`
- **Frontend server** (separate):
  - Runs: nginx serving static frontend build
  - IP: 134.59.98.100 — `frontend@134.59.98.100`
  - Deploy: `scp -r dist/* frontend@134.59.98.100:/var/www/sequoia/`

## Kafka Topics

| Topic | Key Schema | Value Schema | Partitions | Retention | Compression |
|-------|-----------|-------------|------------|-----------|-------------|
| `das.raw.<fiber>` | string | Raw DAS frame (external producer) | 1 | 24h / 10GB | lz4 |
| `das.processed` | string | `das_processed_measurement.avsc` | 1 | 24h / 10GB | lz4 |
| `das.detections` | string | `das_detection.avsc` | 1 | 24h / 10GB | lz4 |
| `das.dlq` | string | `das_dlq_message.avsc` | 1 | 7d / 10GB | lz4 |

**Why single partition:** DAS data requires strict temporal ordering per fiber. Multiple partitions would break the sliding-window processing in Processor and buffered inference in AI Engine.

## ClickHouse Tables

| Table | Granularity | TTL | Purpose |
|-------|-------------|-----|---------|
| `detection_hires` | Per-detection event | 48 hours | Full-resolution detection data |
| `detection_1m` | 1-minute aggregates | 90 days | Section-level traffic stats |
| `detection_1h` | 1-hour aggregates | Forever | Long-term trend analysis |
| `fiber_cables` | Static | None | Fiber cable GPS coordinates |
| `danger_zones` | Static | None | Known high-risk road segments |

Aggregation: Materialized views auto-aggregate from `detection_hires` → `detection_1m` → `detection_1h`.

## Key Architectural Decisions

1. **ClickHouse over PostgreSQL for time-series**: ClickHouse handles 50+ detections/second with sub-second aggregation queries. PostgreSQL would struggle with this write throughput and analytical query pattern.

2. **Single-partition Kafka**: DAS processing requires strict temporal ordering — the sliding window buffers in Processor and AI Engine would produce incorrect results with out-of-order messages.

3. **Per-fiber service instances**: Each Processor and AI Engine instance handles one fiber. Horizontal scaling = add more fiber instances. This isolates failure domains — one fiber's issues don't affect others.

4. **DTAN model for speed estimation**: Diffeomorphic Temporal Alignment Networks learn the warping function between signal pairs, giving continuous speed estimates rather than discrete correlation peaks.

5. **Avro + Schema Registry**: Enforces schema evolution compatibility. DAS hardware (external producer) and pipeline services all validate against registered schemas.

6. **Django Channels for real-time**: Backend bridges Kafka → Redis → WebSocket. Frontend receives live detection events without polling. Simulation fallback when Kafka is unavailable.

## Avro Schemas

### `das_processed_measurement.avsc` (Processor → AI Engine)
Located: `services/pipeline/processor/schema/`

### `das_detection.avsc` (AI Engine → Backend/ClickHouse)
Located: `services/pipeline/ai_engine/schema/`

### `das_dlq_message.avsc` (Any service → DLQ)
Located: `services/pipeline/shared/schema/`

### `string_key.avsc` (Kafka message key)
Located: `services/pipeline/schema/`

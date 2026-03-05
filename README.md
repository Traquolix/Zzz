# SequoIA

Real-time vehicle detection and traffic monitoring using Distributed Acoustic Sensing (DAS) fiber optic cables. The system processes raw DAS signals through a multi-stage pipeline to produce speed estimates, vehicle counts, and traffic incident alerts.

## Architecture

```
DAS Interrogators (ASN OptoDAS, 125 Hz)
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│  Kafka (KRaft)          Schema Registry                          │
│  ┌─────────────┐        ┌──────────────┐                        │
│  │ das.raw.*    │───────▶│ Avro schemas │                        │
│  │ das.processed│        └──────────────┘                        │
│  │ das.detections│                                               │
│  │ das.dlq      │                                                │
│  └─────────────┘                                                 │
└───────┬──────────────────────┬───────────────────────────────────┘
        │                      │
        ▼                      ▼
┌───────────────┐      ┌───────────────┐
│  Processor    │      │  AI Engine    │
│  (Python)     │─────▶│  (Python+CUDA)│
│               │      │  DTAN model   │
│  Bandpass     │      │  Speed est.   │
│  Decimation   │      │  Counting     │
│  CMR          │      │  Classification│
└───────────────┘      └───────┬───────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌──────────────┐
│  ClickHouse   │      │  Django API   │      │  Grafana     │
│               │      │  (DRF + ASGI) │      │  (otel-lgtm) │
│  detection_   │      │               │      │              │
│   hires (48h) │      │  PostgreSQL   │      │  Dashboards  │
│   1m (90d)    │      │  Redis        │      │  Alerts      │
│   1h (forever)│      │               │      │  Traces      │
└───────────────┘      └───────┬───────┘      └──────────────┘
                               │
                               ▼
                       ┌───────────────┐
                       │  Frontend     │
                       │  (React+Vite) │
                       │  Mapbox GL    │
                       │  WebSocket    │
                       └───────────────┘
```

## Services

| Service | Directory | Description |
|---------|-----------|-------------|
| **Processor** | `services/pipeline/processor/` | Consumes raw DAS data, applies bandpass filtering, temporal/spatial decimation. Outputs processed measurements. |
| **AI Engine** | `services/pipeline/ai_engine/` | DTAN-based vehicle detection: speed estimation via temporal alignment, GLRT peak counting, car/truck classification. Requires NVIDIA GPU. |
| **Backend** | `services/platform/backend/` | Django REST API + ASGI WebSocket server. Serves historical data from ClickHouse, real-time data via Kafka bridge. Multi-tenant with JWT auth. |
| **Frontend** | `services/platform/frontend/` | React SPA with Mapbox GL map, real-time traffic visualization, incident management (CIGT workflow). |

## Infrastructure

| Component | Purpose |
|-----------|---------|
| **Kafka** | Message broker (KRaft mode, no Zookeeper). Avro-serialized messages with Schema Registry. |
| **ClickHouse** | Time-series storage with 3-tier aggregation: high-res (48h) → 1-minute (90d) → 1-hour (forever). |
| **PostgreSQL** | Django ORM storage: users, organizations, fiber config, permissions. |
| **Redis** | Django Channels layer for WebSocket pub/sub. |
| **otel-lgtm** | Grafana + Loki + Tempo + Prometheus. Collects OpenTelemetry traces, metrics, and logs. |

## Quick Start

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env — generate real passwords (see comments in file for commands)

# 2. Start all services
docker compose up -d

# 3. Verify
docker compose ps          # All services healthy
open http://localhost:3000  # Frontend
open http://localhost:3002  # Grafana (admin/admin)
```

### Local Development (pipeline only)

```bash
cd services/pipeline
pip install -e ".[dev]"    # Install with dev dependencies
pytest tests/ -v           # Run tests
```

### Local Development (platform only)

```bash
# Backend
cd services/platform/backend
pip install -r requirements.txt
python manage.py runserver

# Frontend
cd services/platform/frontend
npm install
npm run dev
```

## Configuration

- **Fiber/section/model config**: `services/pipeline/config/fibers.yaml` (hot-reloads, no restart needed)
- **Environment variables**: `.env` (see `.env.example` for all options)
- **ClickHouse schema**: `infrastructure/clickhouse/init/` (runs on first startup)
- **Grafana dashboards**: `infrastructure/grafana/dashboards/` (auto-provisioned)
- **Alerting**: `infrastructure/grafana/provisioning/alerting/alerting.yaml`

## Adding a New Fiber

1. Add fiber entry in `services/pipeline/config/fibers.yaml`
2. Insert cable coordinates into `sequoia.fiber_cables` table
3. Create raw topic `das.raw.<fiber_name>` in Kafka (or let auto-create handle it)
4. No code changes required

## Key Documentation

- [Architecture](ARCHITECTURE.md) — Full system topology and inter-service contracts
- [Contributing](CONTRIBUTING.md) — Branch strategy, conventional commits, PR workflow
- [Pipeline Tuning Guide](tools/pipeline/experiments/PIPELINE_TUNING_GUIDE.md) — DTAN retraining and calibration workflow
- API docs: `/api/docs/` (Swagger UI, available in dev mode)

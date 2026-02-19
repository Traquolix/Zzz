# SequoIA

Real-time Distributed Acoustic Sensing (DAS) platform for vehicle detection, speed estimation, and traffic monitoring.

## Architecture

```
DAS Hardware                                                         Frontend
     |                                                                  ^
     v                                                                  |
  Kafka       +-----------+    +-----------+    +------------+    +---------+
 das.raw.* -> | Processor | -> | AI Engine | -> | ClickHouse | <- | Backend | -> WebSocket
              +-----------+    +-----------+    +------------+    +---------+
              Signal proc.     DTAN inference   Time-series DB    Django API
```

**Data flow:** DAS hardware streams raw acoustic data via Kafka. The Processor service applies bandpass filtering, decimation, and noise removal. The AI Engine runs neural network inference (DTAN) to detect vehicles, estimate speeds, and count traffic. Results are stored in ClickHouse with 3-tier aggregation (48h high-res, 90d 1-minute, forever 1-hour). The Django backend serves REST APIs and WebSocket real-time feeds to the React frontend.

## Project Structure

```
sequoia/
|-- services/
|   |-- pipeline/                 # DAS signal processing pipeline
|   |   |-- processor/            # Bandpass, decimation, CMR (Kafka consumer/producer)
|   |   |-- ai_engine/            # DTAN vehicle detection + speed inference (GPU)
|   |   |-- shared/               # Kafka service abstractions + utilities
|   |   |-- config/               # Pipeline configuration (fibers.yaml)
|   |   |-- tests/                # Pipeline service tests
|   |   `-- schema/               # Avro schemas
|   |
|   `-- platform/
|       |-- backend/              # Django 5.2 + DRF API server
|       |   |-- apps/             # accounts, monitoring, fibers, preferences, realtime
|       |   |-- sequoia/settings/ # base, dev, prod, test
|       |   `-- tests/            # API tests
|       |
|       `-- frontend/             # React 19 + Vite + TypeScript SPA
|           `-- src/              # Components, hooks, contexts, API client
|
|-- infrastructure/               # Deployment and ops configuration
|   |-- clickhouse/               # Schema (3-tier), init scripts, fiber cable data
|   |-- grafana/                  # Dashboards and provisioning
|   `-- tempo/                    # Distributed tracing config
|
|-- docker-compose.yml            # Full stack orchestration (10 services)
|-- .env.example                  # Documented environment variables
|-- docs/                         # Deployment guides
`-- .github/workflows/            # CI (lint + test)
```

## Services

| Service | Purpose | Port | Tech |
|---------|---------|------|------|
| **Processor** | Signal processing (bandpass, decimation) | - | Python 3.9, Kafka |
| **AI Engine** | Vehicle detection + speed inference | - | PyTorch, CUDA 12.4 |
| **Backend** | REST API + WebSocket + Admin | 8001 | Django 5.2, Daphne |
| **Frontend** | Monitoring dashboard | 3000 | React 19, Vite, Mapbox |
| **ClickHouse** | Time-series storage | 8123/9000 | ClickHouse 24.8 |
| **Kafka** | Message streaming | 9092 | Confluent 7.8 (KRaft) |
| **Redis** | Cache + WebSocket channels | 6379 | Redis 7 |
| **Grafana** | Pipeline observability | 3002 | Grafana + LGTM |

## Quick Start

```bash
# Copy environment config
cp .env.example .env
# Edit .env with your secrets (ClickHouse password, Mapbox token, etc.)

# Start everything
docker-compose up -d

# Or start specific service groups:
docker-compose up -d kafka clickhouse redis         # Infrastructure
docker-compose up -d processor ai-engine            # Pipeline
docker-compose up -d platform-backend platform-frontend  # Platform
```

### Local Development

```bash
# Pipeline services
cd services/pipeline
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v

# Backend (Django)
cd services/platform/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py seed_users
python manage.py run_realtime --source sim  # Starts backend + simulation

# Frontend (React)
cd services/platform/frontend
npm install && npm run dev
```

## Authentication

JWT RS256 with httpOnly refresh cookies. Login via `POST /api/auth/login`, include token as `Authorization: Bearer <token>`. WebSocket auth via query string `?token=<jwt>`.

## Deployment

See the deployment guides in `docs/`:

- **[DEPLOYMENT_IMREDD.md](docs/DEPLOYMENT_IMREDD.md)** - Split deployment (backend + frontend servers)
- **[DEPLOYMENT_LINUX.md](docs/DEPLOYMENT_LINUX.md)** - Single-server Linux deployment
- **[BACKUP_STRATEGY.md](docs/BACKUP_STRATEGY.md)** - Backup and recovery procedures

## License

Proprietary - All rights reserved.

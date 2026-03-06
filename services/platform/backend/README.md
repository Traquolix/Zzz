# Backend

Django REST API and ASGI WebSocket server. Serves historical traffic data from ClickHouse, streams real-time detections via WebSocket, and provides multi-tenant user management with JWT authentication.

## Data Flow

```
                    ┌─────────────┐
                    │  ClickHouse │ ◄── historical queries
                    └──────┬──────┘
                           │
Kafka (das.detections) ──► Kafka Bridge ──► Redis Channels ──► WebSocket
                           │                                      │
                     alert checking                          React frontend
                           │
                    ┌──────┴──────┐
                    │ PostgreSQL  │ ◄── users, orgs, config, alerts
                    └─────────────┘
```

## Django Apps

| App | Purpose |
|-----|---------|
| `accounts` | Custom User model, JWT login/refresh/logout, account lockout |
| `organizations` | Multi-tenant org model, org settings |
| `fibers` | Fiber-to-org assignment, fiber list API |
| `monitoring` | Incidents, sections, stats, infrastructure, SHM |
| `alerting` | Alert rules (speed/incident triggers), dispatch (webhook/email/log) |
| `realtime` | WebSocket consumer, Kafka bridge, simulation engine |
| `reporting` | Report builder, schedules, email dispatch |
| `preferences` | User dashboard config |
| `api_keys` | Programmatic API access (`sqk_` prefixed keys) |
| `admin_api` | Superuser-only org/user/infra management |
| `shared` | ClickHouse client, permissions, health checks, audit log, metrics |

## Key Files

```
backend/
├── manage.py
├── Dockerfile                      # Python 3.10-slim, non-root
├── entrypoint.sh                   # Migrate, seed, start Daphne
├── requirements.txt
├── sequoia/
│   ├── asgi.py                     # HTTP + WebSocket routing
│   ├── urls.py                     # Root URL config
│   └── settings/
│       ├── base.py                 # Shared settings
│       ├── dev.py                  # SQLite, in-memory channels, auto JWT keys
│       ├── prod.py                 # PostgreSQL, Redis, strict security
│       └── test.py                 # pytest-django config
├── apps/
│   ├── api/urls.py                 # All API routes
│   ├── realtime/
│   │   ├── consumers.py            # RealtimeConsumer (WebSocket)
│   │   ├── kafka_bridge.py         # Kafka → Redis Channels → WebSocket
│   │   └── simulation.py           # Synthetic data for dev mode
│   ├── monitoring/views.py         # Incidents, sections, stats
│   ├── shared/
│   │   ├── clickhouse.py           # Thread-local client, circuit breaker
│   │   └── permissions.py          # IsActiveUser, IsNotViewer
│   └── ...
└── tests/
```

## API Endpoints

All routes under `/api/`. Full OpenAPI docs at `/api/docs/` (dev mode).

**Auth:** `/auth/login`, `/auth/verify`, `/auth/refresh`, `/auth/logout`
**Data:** `/fibers`, `/incidents`, `/sections`, `/stats`, `/user/preferences`
**Reports:** `/reports`, `/reports/generate`, `/reports/schedules`
**Export:** `/export/incidents`, `/export/detections` (CSV)
**Admin:** `/admin/organizations`, `/admin/users`, `/admin/alert-rules`, `/admin/api-keys`
**Health:** `/health`, `/health/ready`, `/metrics`

## WebSocket

Endpoint: `/ws/`

```json
{"action": "authenticate", "token": "<jwt_access_token>"}
{"action": "subscribe", "channel": "detections"}
{"action": "unsubscribe", "channel": "incidents"}
{"action": "ping"}
```

Channels: `detections`, `counts`, `incidents`, `shm_readings`, `fibers`

All broadcasts are org-scoped — users only receive data for fibers assigned to their organization.

## Configuration

### Settings

| Setting | Dev | Prod |
|---------|-----|------|
| Database | SQLite | PostgreSQL |
| Channels layer | In-memory | Redis |
| Cache | LocMemCache | Redis |
| JWT keys | Auto-generated RSA | Env vars / Docker secrets |
| Realtime source | Simulation (auto-start) | Kafka bridge |
| CORS | Allow all | Explicit origins |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DJANGO_SETTINGS_MODULE` | `sequoia.settings.dev` or `sequoia.settings.prod` |
| `POSTGRES_HOST`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | PostgreSQL connection |
| `CLICKHOUSE_HOST`, `CLICKHOUSE_DATABASE` | ClickHouse connection |
| `REDIS_HOST`, `REDIS_DB` | Redis for channels + cache |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker (optional in dev) |
| `JWT_SIGNING_KEY`, `JWT_VERIFYING_KEY` | RS256 keys (auto-generated in dev) |
| `FRONTEND_URL` | CORS allowed origin |

## Running

```bash
# Docker (standard)
make rebuild SERVICE=platform-backend

# Local development
cd services/platform/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DJANGO_SETTINGS_MODULE=sequoia.settings.dev python manage.py migrate
DJANGO_SETTINGS_MODULE=sequoia.settings.dev python manage.py run_realtime

# Management commands
python manage.py run_realtime --source sim     # Simulation only
python manage.py run_realtime --source kafka   # Kafka bridge only
python manage.py run_realtime --source auto    # Auto-detect (default)
python manage.py seed_users                    # Create demo users (dev)
```

## Design

- **ASGI:** Daphne serves both HTTP and WebSocket via Django Channels
- **Multi-tenant:** Every query scoped to `request.user.organization`
- **ClickHouse:** Thread-local clients with circuit breaker and exponential backoff
- **Kafka bridge:** Time-shifted replay buffer converts 30s AI engine bursts into ~10 Hz stream
- **Auth:** JWT RS256, httpOnly refresh cookies, 5-attempt lockout
- **Alerting:** Rules evaluated inline during Kafka bridge processing

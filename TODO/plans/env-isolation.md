# Plan: Preprod / Prod Environment Isolation

## Goal

Run two isolated environments (preprod, prod) on the same server so that changes
can be tested end-to-end — including frontend UI/UX — against real DAS data with
a real user session before rolling to production. A third "dev" environment runs
locally on your machine (separate effort, #7).

- **Preprod**: deployed on the servers, reachable by a tester at a separate URL.
  Processes real DAS data. Frontend is deployed so UI/UX changes are testable in
  a real browser.
- **Prod**: current production, untouched until preprod is validated.

## Constraints

- 2 physical servers: backend (GPU, 900 GB RAM) and frontend (nginx → NPM)
- 1 GPU (RTX 4000 Ada, 20 GB VRAM) — current prod uses ~3.2 GB VRAM, ~3-4s of
  GPU per 22.5s cycle. Doubling for preprod is fine without MPS; stagger startup
  by ~11s for cleaner scheduling.
- 1 DAS interrogator producing real data to Kafka
- Preprod must be reachable from the public internet (testers are external)
- Prod frontend moving to `app.sequoia-analytics.tech` (#323-325)
- Nginx Proxy Manager with wildcard TLS for `*.sequoia-analytics.tech` (#323)

## Architecture: Namespace Isolation on Shared Infra

Share the heavy stateful services (Kafka, ClickHouse, PostgreSQL, Redis, GPU) but
isolate at the application layer using topic prefixes, separate databases, separate
Redis DB indices, and separate URLs.

```
                 SHARED (single instance)
    ┌──────────────────────────────────────────┐
    │  Kafka         (topic prefix per env)    │
    │  Schema Registry                         │
    │  ClickHouse    (database per env)        │
    │  PostgreSQL    (database per env)        │
    │  Redis         (DB index per env)        │
    │  otel-lgtm     (ENVIRONMENT label)       │
    │  GPU           (time-shared, staggered)  │
    └──────┬──────────────┬────────────────────┘
           │              │
    ┌──────┴──────┐ ┌─────┴───────┐
    │   PREPROD   │ │    PROD     │
    │             │ │             │
    │ Topics:     │ │ Topics:     │
    │  preprod.*  │ │  das.*      │
    │             │ │             │
    │ PG database:│ │ PG database:│
    │  sequoia_pp │ │  sequoia    │
    │             │ │             │
    │ CH database:│ │ CH database:│
    │  sequoia_pp │ │  sequoia    │
    │             │ │             │
    │ Redis:      │ │ Redis:      │
    │  DB 2 + 3   │ │  DB 0 + 1   │
    │             │ │             │
    │ Backend:    │ │ Backend:    │
    │  :8002      │ │  :8001      │
    │             │ │             │
    │ Frontend:   │ │ Frontend:   │
    │  preprod.   │ │  app.       │
    │  sequoia-   │ │  sequoia-   │
    │  analytics  │ │  analytics  │
    │  .tech      │ │  .tech      │
    └─────────────┘ └─────────────┘
```

## How Preprod Gets Real DAS Data

The DAS interrogator pushes to `das.raw.carros`. The preprod processor **also**
subscribes to `das.raw.carros` (same topic, different consumer group) but writes
its output to `preprod.processed` instead of `das.processed`. The preprod AI
Engine reads `preprod.processed` and writes to `preprod.detections` + the
`sequoia_pp` ClickHouse database.

This means preprod sees the exact same raw fiber data as prod, processes it
independently, and stores results separately. Zero interference with prod.

```
DAS Interrogator
      │
      v
 das.raw.carros (shared Kafka topic)
      │
      ├──> processor         (prod)    → das.processed     → ai-engine     (prod)
      │    group: das-processor-group
      │
      └──> processor-pp      (preprod) → preprod.processed → ai-engine-pp  (preprod)
           group: das-processor-preprod-group
```

## GPU Sharing Strategy

Measured production GPU profile (2026-04-04):
- RTX 4000: 3.2 GB / 20 GB VRAM. SM utilization: bursty 35-47% for ~3-4s every
  22.5s cycle, idle between cycles.
- Two AI engines double VRAM to ~6.4 GB (plenty of headroom) and double compute
  bursts.
- With 11-second startup stagger (half the 22.5s cycle), prod and preprod bursts
  alternate — peak SM stays at 35-47% instead of doubling.
- Even without stagger, worst case is ~80% SM for 3-4s with 15s idle. Both keep
  up with real time.

Decision: **No MPS needed.** Plain CUDA time-sharing with optional startup stagger.
Close #356 as won't-do. Revisit only if a third GPU consumer is added.

## How Preprod is Reachable (Frontend + Backend)

### Backend server

Preprod backend runs on **port 8002** (prod stays on 8001). Both bind to the
server's internal IP.

### Frontend server (NPM)

With Nginx Proxy Manager (#323) and wildcard TLS for `*.sequoia-analytics.tech`:

- `app.sequoia-analytics.tech` → prod frontend (static) + reverse proxy to
  backend :8001 for `/api/` and `/ws/`
- `preprod.sequoia-analytics.tech` → preprod frontend (static) + reverse proxy
  to backend :8002 for `/api/` and `/ws/`

Each is a separate NPM proxy host. The frontend is built with `VITE_API_URL=""`
(same-origin mode) for both environments — NPM handles routing API/WS requests
to the correct backend port. No `VITE_BASE_PATH` needed since each env has its
own subdomain.

### Access control

Both subdomains are publicly reachable. The Django backend requires JWT
authentication for all API access and WebSocket connections. An unauthenticated
visitor sees the login page and nothing else.

Tester onboarding: create a user account in the preprod PostgreSQL database
(`sequoia_pp`) via Django admin or `manage.py createsuperuser`.

## Docker Compose Split

The compose topology follows the split planned in #322:

```
docker-compose.infra.yml       # Kafka, Schema Registry, ClickHouse, PG, Redis, otel-lgtm
docker-compose.pipeline.yml    # processor, ai-engine
docker-compose.platform.yml    # platform-backend
```

Preprod uses the **same pipeline and platform compose files** with a different
`--env-file` and `-p` (project name):

```bash
# Shared infra (once)
docker compose -f docker-compose.infra.yml up -d

# Prod
docker compose -f docker-compose.pipeline.yml --env-file .env up -d
docker compose -f docker-compose.platform.yml --env-file .env up -d

# Preprod
docker compose -f docker-compose.pipeline.yml --env-file .env.preprod -p sequoia-pp up -d
docker compose -f docker-compose.platform.yml --env-file .env.preprod -p sequoia-pp up -d
```

No profiles, no duplicated service definitions. Same compose file, different env.

## Implementation Phases

### Phase 1: Topic Prefix in Pipeline + Backend

Add `TOPIC_PREFIX` env var (default: `das`) to pipeline and backend so topics
become `{prefix}.processed`, `{prefix}.detections`, `{prefix}.dlq`.

Code changes:
- `config/service_loader.py` — prefix output topics, DLQ topic
- `config/fiber_config.py` — prefix bootstrap consumer group
- `shared/kafka_setup.py` — prefix consumer group ID
- Backend `kafka_bridge.py` — read topic and consumer group from Django settings
- Backend `settings/base.py` — add `KAFKA_DETECTIONS_TOPIC`, `KAFKA_CONSUMER_GROUP`

Note: the processor raw input pattern stays `^das\.raw\.[^.]+$` — preprod reads
the same raw data from the DAS interrogator, just with a different consumer group.

### Phase 2: Redis DB Isolation in Backend

Parameterize Redis port and DB indices in Django settings.

Code changes:
- `settings/base.py` — add `REDIS_PORT`, `REDIS_CHANNEL_DB`, `REDIS_CACHE_DB`
- `settings/prod.py` — use the new vars in CHANNEL_LAYERS, CACHES, REDIS_PUBSUB_URL
- Preprod uses `REDIS_CHANNEL_DB=2`, `REDIS_CACHE_DB=3`

### Phase 3: ClickHouse Database Isolation

Template ClickHouse SQL files so the database name, Kafka topic, and consumer
group are parameterizable.

Changes:
- Rename `init/*.sql` → `init/*.sql.tmpl` with `${CH_DATABASE}`,
  `${CH_KAFKA_TOPIC}`, `${CH_KAFKA_GROUP}` placeholders
- Add entrypoint wrapper: `envsubst` renders templates before `clickhouse-client`
- Same for `migrations/*.sql` — update `apply_clickhouse_migrations` command
- Create `sequoia_pp` database for preprod

### Phase 4: Compose Split + Preprod Env File

Split `docker-compose.yml` into `infra`, `pipeline`, `platform`. Create
`.env.preprod` with all environment-specific overrides.

Changes:
- Split compose file (may already be done under #322)
- Create `.env.preprod`
- Create preprod Kafka topics (`preprod.processed`, `preprod.detections`,
  `preprod.dlq`) in `kafka-setup` or separate init script
- Add Makefile targets: `up-infra`, `up-prod`, `up-preprod`, `down-preprod`

### Phase 5: CI/CD Promotion Pipeline

Restructure deployment: merge to main → deploy preprod → manual gate → deploy prod.

Changes:
- Add `develop` branch as integration branch
- Update `deploy.yml`: preprod deploys on push to `develop`, prod deploys on
  push to `main` with GitHub Environment protection (manual approval)
- Branch protection on `main`: require PR from `develop`, require
  "preprod-healthy" status check
- Both deploy jobs use the same steps but different `DEPLOY_DIR` and env vars
  (via GitHub Environment variables)

### Phase 6: Frontend Preprod Deploy

Deploy preprod frontend to `preprod.sequoia-analytics.tech`.

Changes:
- Add NPM proxy host for `preprod.sequoia-analytics.tech`
- Build preprod frontend: `VITE_API_URL="" npm run build`
- Deploy to `/var/www/sequoia-preprod/` on frontend server
- Add `deploy-preprod-frontend` job to `deploy.yml`

### Phase 7: Observability Isolation

Tag all telemetry with `ENVIRONMENT`, add dashboard filters.

Changes:
- Verify `ENVIRONMENT` resource attribute in all services (already exists)
- Add `$environment` template variable to Grafana dashboard JSON files
- Filter alerting notification policies: `environment != preprod`

## Resource Impact on Backend Server

| Component | Extra RAM | Extra CPU | Extra VRAM | Notes |
|-----------|-----------|-----------|------------|-------|
| processor-pp | ~2 GB | 1 core | 0 | Same binary, different topics |
| ai-engine-pp | ~4 GB | 2 cores | ~3.2 GB | Time-shared GPU |
| platform-backend-pp | ~512 MB | 0.5 core | 0 | Django + Daphne |
| PostgreSQL (sequoia_pp) | ~100 MB | negligible | 0 | Same server, extra DB |
| ClickHouse (sequoia_pp) | ~200 MB | negligible | 0 | Same server, extra DB |
| Redis DB 2+3 | ~50 MB | negligible | 0 | Same server, extra DB number |
| **Total** | **~7 GB** | **~3.5 cores** | **~3.2 GB** | |

The server has 900 GB RAM, 20 GB VRAM. This is nothing.

## Dependencies

- #322 (compose split) — Phase 4 depends on this
- #323 (NPM + wildcard TLS) — Phase 6 depends on this
- #325 (backend reverse proxy) — Phase 6 depends on this

## Order of Work

1. **Topic prefix** (Phase 1) — the core code change, unblocks everything
2. **Redis isolation** (Phase 2) — small, can be in same PR as Phase 1
3. **ClickHouse isolation** (Phase 3) — SQL templating
4. **Compose split + env file** (Phase 4) — infra config
5. **CI/CD promotion** (Phase 5) — workflow restructure
6. **Frontend preprod** (Phase 6) — after NPM is deployed
7. **Observability** (Phase 7) — nice-to-have, can come later

Phases 1-2 can be one PR. Phase 3 is a separate PR. Phase 4 depends on #322.
Phases 5-7 can proceed independently once Phase 4 is done.

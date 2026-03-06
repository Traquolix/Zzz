# Plan: Dev / Preprod / Prod Environment Isolation

## Goal

Run three isolated environments (dev, preprod, prod) so that changes can be tested
end-to-end — including frontend UI/UX — against real DAS data with a real user session
before rolling to production.

- **Dev**: local machine, for development. Uses simulation mode or replayed data.
- **Preprod**: deployed on the servers, reachable by a tester (or yourself) at a
  separate URL. Processes real DAS data. Frontend is deployed so UI/UX changes are
  testable in a real browser, not just localhost.
- **Prod**: current production, untouched until preprod is validated.

## Constraints

- 2 physical servers: backend (GPU, 900GB RAM) and frontend (nginx)
- 1 GPU (RTX 4000 Ada) — can't run 3 AI Engines at full load simultaneously, but
  preprod traffic is minimal so GPU time-sharing is fine
- 1 DAS interrogator producing real data to Kafka
- Preprod must be reachable from the public internet (testers are external to the
  university network)
- Prod frontend is publicly accessible at `dashboardsequoia.univ-cotedazur.fr`

## Architecture: Namespace Isolation on Shared Infra

Share the heavy stateful services (Kafka, ClickHouse, GPU) but isolate at the
application layer using topic prefixes, separate databases, and separate ports/URLs.

```
                 SHARED (single instance)
    ┌──────────────────────────────────────────┐
    │  Kafka         (topic prefix per env)    │
    │  Schema Registry                         │
    │  ClickHouse    (database per env)        │
    │  otel-lgtm     (label per env)           │
    │  GPU           (time-shared)             │
    └──────┬──────────────┬────────────────────┘
           │              │
    ┌──────┴──────┐ ┌─────┴───────┐
    │   PREPROD   │ │    PROD     │
    │             │ │             │
    │ Kafka pfx:  │ │ Kafka pfx:  │
    │  preprod.*  │ │  das.*      │
    │             │ │             │
    │ PG database:│ │ PG database:│
    │  sequoia_pp │ │  sequoia    │
    │             │ │             │
    │ CH database:│ │ CH database:│
    │  sequoia_pp │ │  sequoia    │
    │             │ │             │
    │ Redis DB: 1 │ │ Redis DB: 0 │
    │             │ │             │
    │ Backend:    │ │ Backend:    │
    │  :8002      │ │  :8001      │
    │             │ │             │
    │ Frontend:   │ │ Frontend:   │
    │  /preprod/  │ │  /          │
    └─────────────┘ └─────────────┘
```

Dev runs locally on your machine with `docker compose --profile dev up` (simulation
mode, its own DB, no server deployment needed).

## How Preprod Gets Real DAS Data

The DAS interrogator pushes to `das.raw.carros`. The preprod processor **also**
subscribes to `das.raw.carros` (same topic, different consumer group) but writes its
output to `preprod.processed` instead of `das.processed`. The preprod AI Engine reads
`preprod.processed` and writes to `preprod.detections` + the `sequoia_pp` ClickHouse
database.

This means preprod sees the exact same raw fiber data as prod, processes it
independently, and stores results separately. Zero interference with prod.

```
DAS Interrogator
      │
      v
 das.raw.carros (shared Kafka topic)
      │
      ├──> processor-carros      (prod)    → das.processed     → ai-engine (prod)
      │    consumer group: proc-carros
      │
      └──> processor-carros-pp   (preprod) → preprod.processed → ai-engine (preprod)
           consumer group: proc-carros-pp
```

## How Preprod is Reachable (Frontend + Backend)

### Backend server

Preprod backend runs on **port 8002** (prod stays on 8001). Both bind to the server's
internal IP. No extra reverse proxy needed — the port difference is the isolation.

### Frontend server (nginx)

Preprod frontend is served at a **separate path prefix** (`/preprod/`) or a
**subdomain** (`preprod.sequoia.imredd.fr` if DNS is available).

**Option A — Path prefix (simpler, no DNS needed):**

```nginx
# /etc/nginx/sites-available/sequoia

# Prod
location / {
    root /var/www/sequoia/prod;
    try_files $uri $uri/ /index.html;
}

# Preprod
location /preprod/ {
    alias /var/www/sequoia/preprod/;
    try_files $uri $uri/ /preprod/index.html;
}
```

Frontend build needs `VITE_BASE_URL=/preprod/` so Vite generates correct asset paths.
The preprod build points `VITE_API_URL` at the backend server port 8002.

**Option B — Subdomain (cleaner, needs DNS):**

```nginx
server {
    server_name preprod.sequoia.imredd.fr;
    root /var/www/sequoia/preprod;
    # ...
}
```

**Recommendation:** Start with Option A (path prefix). It works immediately without
touching DNS. Switch to subdomain later if desired.

### Access control

Both prod and preprod are publicly reachable on the internet (via the university's
reverse proxy / DNS for `dashboardsequoia.univ-cotedazur.fr`). Testers are external
to the university network.

No extra nginx-level auth is needed for preprod. The Django backend already requires
JWT authentication for all API access and WebSocket connections. An unauthenticated
visitor to `/preprod/` sees the login page and nothing else — no data is accessible
without a valid preprod user account.

The preprod frontend bundle itself (JS/HTML/CSS) is visible without auth, but this
is a university research tool, not a commercial product — exposing unreleased UI
chrome to someone who guesses the URL is not a meaningful risk. The URL is not
indexed or linked from anywhere.

**Tester onboarding:** create a user account in the preprod PostgreSQL database
(`sequoia_pp`) via Django admin or `manage.py createsuperuser`. One login, one
password. Same flow as prod.

## Implementation Steps

### Phase 1: Topic Prefix Support in Pipeline

The pipeline services currently hardcode topic names (`das.raw.{fiber}`,
`das.processed`, `das.detections`, `das.dlq`). Add a `TOPIC_PREFIX` env var to
`ServiceBase` / config so topics become `{TOPIC_PREFIX}.raw.{fiber}`, etc.

- [ ] Add `TOPIC_PREFIX` env var (default: `das` for backwards compat)
- [ ] Update `shared/service_base.py` to read prefix and apply to all topic names
- [ ] Update `config/fibers.yaml` topic references if any are hardcoded there
- [ ] Update `kafka-setup` init script to also create `preprod.*` topics
- [ ] Test: processor with `TOPIC_PREFIX=test` writes to `test.processed`

### Phase 2: Separate Databases

- [ ] Add ClickHouse init script for `sequoia_pp` database (same schema as `sequoia`)
- [ ] Add PostgreSQL init for `sequoia_pp` database
- [ ] Add `CLICKHOUSE_DATABASE` env var to AI Engine (currently hardcoded or from .env)
- [ ] Backend already reads `CLICKHOUSE_DATABASE` and `POSTGRES_DB` from env — just
      needs different values per environment

### Phase 3: Docker Compose Profiles

Add preprod service definitions to `docker-compose.yml` using profiles:

```yaml
# Existing prod services stay as-is (no profile = always started)

processor-carros-pp:
  profiles: [preprod]
  build: { context: services/pipeline, dockerfile: processor/Dockerfile }
  container_name: processor-carros-pp
  environment:
    FIBER_ID: carros
    TOPIC_PREFIX: preprod
  env_file: .env.preprod
  networks: [internal]

ai-engine-carros-pp:
  profiles: [preprod]
  # ... same pattern, TOPIC_PREFIX=preprod, CLICKHOUSE_DATABASE=sequoia_pp

platform-backend-pp:
  profiles: [preprod]
  build: { context: services/platform/backend, dockerfile: Dockerfile }
  container_name: platform-backend-pp
  ports:
    - "${BACKEND_BIND_ADDRESS:-127.0.0.1}:8002:8001"
  environment:
    DJANGO_SETTINGS_MODULE: sequoia.settings.preprod
    POSTGRES_DB: sequoia_pp
    CLICKHOUSE_DATABASE: sequoia_pp
    REDIS_DB: 1
    TOPIC_PREFIX: preprod
    ENVIRONMENT: preprod
  env_file: .env.preprod
  networks: [internal, default]
```

Commands:
```bash
make up                              # prod only (current behavior)
make up-preprod                      # prod + preprod
docker compose --profile preprod up -d   # explicit
```

- [ ] Create `.env.preprod` — Docker Compose supports multiple `env_file:` entries;
      preprod services list `[.env, .env.preprod]` so `.env` provides base values
      (Kafka bootstrap, shared passwords) and `.env.preprod` overrides env-specific
      ones (DB names, ports, topic prefix). Later entries win on conflicts.
- [ ] Add preprod service definitions to `docker-compose.yml`
- [ ] Add `settings/preprod.py` Django settings (inherits `prod.py`, different DB)
- [ ] Add Makefile targets: `up-preprod`, `down-preprod`, `logs-preprod`
- [ ] Add migration step to deploy workflow — run
      `docker compose exec platform-backend-pp python manage.py migrate` after
      preprod backend starts, so schema changes are applied to `sequoia_pp`

### Phase 4: Frontend Preprod Deploy

- [ ] Configure Vite build for preprod: `VITE_API_URL=http://<backend-ip>:8002`,
      `VITE_BASE_URL=/preprod/`
- [ ] Add nginx config for `/preprod/` location
- [ ] Update `deploy.yml` to build and deploy preprod frontend to
      `/var/www/sequoia/preprod/`
- [ ] Add deploy workflow trigger on `preprod` branch (or manual dispatch with
      environment selector)
- [ ] **Resolve HTTPS/mixed-content** — prod frontend is served over HTTPS via the
      university reverse proxy (`dashboardsequoia.univ-cotedazur.fr`). If the preprod
      frontend is also HTTPS but the preprod backend is plain HTTP on port 8002,
      browsers will block mixed-content requests. Options: (a) route preprod API
      through the university reverse proxy at a `/preprod/api/` path, or (b) add TLS
      termination on the backend server for port 8002. Decision needed before Phase 4.

### Phase 5: CI / Deploy Workflow

- [ ] Add `preprod` branch to CI triggers
- [ ] Add `deploy-preprod` jobs to `deploy.yml` (triggered by `preprod` branch push
      or manual dispatch with `environment: preprod` selector)
- [ ] Deploy flow becomes:
      ```
      feature branch → PR → merge to preprod → CI → deploy to preprod
                                                        ↓
                                              test with real user/data
                                                        ↓
                                              merge preprod → main → deploy to prod
      ```

### Phase 6: Grafana / Observability

- [ ] Add `environment` label to OTel metrics and logs (from `ENVIRONMENT` env var)
- [ ] Update Grafana dashboards to add `$environment` template variable filter
- [ ] Preprod services appear in same dashboards, filterable

## Dev Environment (Local)

See [`TODO/plans/dev-environment.md`](dev-environment.md) for the full local dev plan
(`make dev` for simulation, `make dev-full` for recorded replay).

## Resource Impact on Backend Server

| Component | Extra RAM | Extra CPU | Notes |
|-----------|-----------|-----------|-------|
| processor-carros-pp | ~2 GB | 1 core | Same binary, different topics |
| ai-engine-carros-pp | ~4 GB | 2 cores | GPU shared, minimal extra VRAM |
| platform-backend-pp | ~512 MB | 0.5 core | Django + Daphne |
| PostgreSQL (sequoia_pp) | ~100 MB | negligible | Same server, extra DB |
| ClickHouse (sequoia_pp) | ~200 MB | negligible | Same server, extra DB |
| Redis DB 1 | ~50 MB | negligible | Same server, extra DB number |
| **Total** | **~7 GB** | **~3.5 cores** | |

The server has 900 GB RAM. This is nothing.

## Order of Work

1. **Topic prefix** (Phase 1) — the only code change, everything else is config
2. **Databases** (Phase 2) — init scripts, trivial
3. **Compose profiles** (Phase 3) — the bulk of the infra work
4. **Frontend deploy** (Phase 4) — nginx + Vite config
5. **CI/CD** (Phase 5) — workflow updates
6. **Observability** (Phase 6) — nice-to-have, can come later

Phases 1-3 can be done in a single PR. Phase 4 can follow immediately. Phase 5
depends on having GitHub Actions runners installed (see TODO.md).

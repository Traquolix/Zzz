# Plan: Test Strategy

## Goal

Rebuild the test suite from scratch after the AI-generated tests were removed.
Define what's worth testing, at what granularity, and in what order. Once done,
re-enable `make test` in the Makefile, CI, and CLAUDE.md validation command.

## Philosophy

- **Test behavior, not implementation.** Don't test that a function calls another
  function — test that given input X, output Y happens.
- **Integration > unit for pipeline.** The pipeline services are glue between Kafka
  and signal processing. Mocking Kafka defeats the purpose. Test with real Kafka
  (Docker) where possible.
- **Unit tests for backend business logic.** Django views, serializers, the incident
  workflow, ClickHouse query builders — these have clear inputs/outputs.
- **Component tests for frontend.** Test that components render correct data, handle
  loading/error states, and fire correct callbacks. Don't test Mapbox GL internals.
- **Golden file tests for AI.** The DTAN model and GLRT detector are numerical —
  test by replaying known input and comparing output (see `dev-environment.md`).

## What NOT to Test

- Framework internals (Django ORM, React rendering, Kafka consumer lifecycle)
- Pure config (fibers.yaml parsing — already validated by the schema)
- One-liner wrappers with no logic
- CSS / styling

## Scope by Service

### Pipeline (`services/pipeline/`)

**Testing framework:** pytest + pytest-asyncio

**Priority 1 — Signal processing (pure functions, high value):**
- Bandpass filter: known input signal → expected frequency content
- Temporal decimation: 125 Hz input → 10.4 Hz output, correct sample count
- Spatial decimation: N channels → N/3 channels, correct selection
- Common mode removal: synthetic common mode → removed
- Energy normalization: output within expected range

These are the core processing steps. They're pure numpy — easy to test, high
confidence value.

**Priority 2 — Service plumbing (integration, medium value):**
- Processor end-to-end: raw Avro message in → processed Avro message out
  (requires Kafka + Schema Registry in Docker)
- AI Engine end-to-end: processed message in → detection out
  (requires Kafka + GPU or CPU fallback)
- Config hot-reload: change fibers.yaml → service picks up new config

These are integration tests in `tests/integration/` (already marked as
Docker-required in the codebase).

**Priority 3 — Shared utilities:**
- CircuitBreaker: state transitions (closed → open → half-open)
- DLQ: message lands in DLQ topic on processing failure
- ServiceBase: graceful shutdown, health check

**What exists today:**
- `tests/conftest.py` — fixtures for Kafka, Schema Registry, ClickHouse
- `tests/integration/` — empty but the structure is there
- No unit tests at all after the purge

> **Note:** These fixtures were created alongside AI-generated tests that have since
> been removed. Verify they still match current models/schemas before building on them.

### Backend (`services/platform/backend/`)

**Testing framework:** pytest-django + Factory Boy

**Priority 1 — Auth & multi-tenancy (security-critical):**
- Org scoping: user from org A cannot see org B's data
- Permission classes: `IsActiveUser`, `IsAdminOrSuperuser`, `IsSuperuser`
  correctly restrict endpoints
- JWT auth: valid token → access, expired token → 401, wrong org → 403

**Priority 2 — Monitoring / incident workflow:**
- Incident creation from alert threshold breach
- Incident lifecycle: open → acknowledged → resolved
- Snapshot view: returns correct ClickHouse data window around incident
- Incident list: filtered by org, section, time range

**Priority 3 — Reporting & data views:**
- ClickHouse query builder: correct SQL generated for different time ranges
  and aggregation levels
- Report builder: generates expected structure
- Detection stats API: correct aggregation

**Priority 4 — Realtime:**
- Kafka bridge: detection message → Redis channel → WebSocket
- Simulation: generates plausible detection events
- WebSocket consumer: auth required, org-scoped data

**What exists today:**
- `tests/conftest.py` with `mock_clickhouse_query` fixture
- `tests/factories.py` — needs Factory Boy factories for User, Org, Fiber, etc.
- Django test settings (`settings/test.py`) — configured

> **Note:** `factories.py` may need updates — it was created alongside now-removed
> AI-generated tests. Verify factory fields match current model definitions.

### Frontend (`services/platform/frontend/`)

**Testing framework:** vitest + @testing-library/react

**Priority 1 — Data display correctness:**
- Detection stats components: given mock API data, render correct numbers
- Incident list: renders incidents, handles empty state
- Snapshot display: renders speed/flow/occupancy data correctly

**Priority 2 — Auth flow:**
- Login form: submits credentials, stores token
- Protected routes: redirect to login when unauthenticated
- Token refresh: handles expired token

**Priority 3 — Realtime:**
- WebSocket hook: connects, receives messages, updates store
- Map markers: update positions on new detections

**What exists today:**
- vitest configured in `vite.config.ts`
- No test files

## Implementation Steps

### Phase 1: Pipeline Unit Tests

- [ ] Write signal processing tests (bandpass, decimation, CMR, normalization)
- [ ] Write CircuitBreaker state machine tests
- [ ] Write DLQ routing tests
- [ ] Add `make test-pipeline` target
- [ ] Target: ~20-30 tests, runs in <5s without Docker

### Phase 2: Backend Unit Tests

- [ ] Create Factory Boy factories (User, Organization, Fiber, Section, Incident)
- [ ] Write auth/permission tests (org scoping, permission classes)
- [ ] Write incident workflow tests
- [ ] Write ClickHouse query builder tests (mock ClickHouse, test SQL generation)
- [ ] Add `make test-backend` target
- [ ] Target: ~30-40 tests, runs in <10s

### Phase 3: Frontend Tests

- [ ] Write detection stats component tests
- [ ] Write incident list/snapshot display tests
- [ ] Write auth flow tests
- [ ] Add `make test-frontend` target
- [ ] Target: ~15-20 tests, runs in <10s

### Phase 4: Integration Tests

Depends on replay infrastructure from [`dev-environment.md`](dev-environment.md)
Phase 2 (recording scripts) and Phase 3 (Docker Compose dev profile).

- [ ] Processor end-to-end (Docker: Kafka + Schema Registry)
- [ ] AI Engine end-to-end (Docker: Kafka + Schema Registry + GPU/CPU)
- [ ] Backend Kafka bridge → WebSocket (Docker: Kafka + Redis)
- [ ] Add `make test-integration` target (requires Docker stack)

For ClickHouse query builder tests: use the existing `mock_clickhouse_query` fixture
to mock `apps.shared.clickhouse.query()` with known return data. Integration tests
(Phase 4) can use the Docker ClickHouse instance with seed data instead.

### Phase 5: Re-enable in CI

- [ ] Add test jobs back to `.github/workflows/ci.yml`
- [ ] Add `make test` to Makefile (runs pipeline + backend + frontend, not integration)
- [ ] Add `make test` back to CLAUDE.md validation command
- [ ] Integration tests run on self-hosted runner only (needs Docker + GPU)

## Order of Work

1. **Pipeline unit tests** (Phase 1) — pure functions, easiest to write, highest
   confidence for the core processing logic
2. **Backend unit tests** (Phase 2) — security-critical (auth/multi-tenancy)
3. **Frontend tests** (Phase 3) — can run in parallel with Phase 2
4. **Integration tests** (Phase 4) — depends on Docker infra and test recordings
   from `dev-environment.md`
5. **CI** (Phase 5) — flip the switch once phases 1-3 are stable

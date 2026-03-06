# SequoIA — Outstanding Tasks

> Detailed plans live in `TODO/plans/`. Task history in `TODO/history.md`.

## High Priority

- [ ] **Install self-hosted GitHub Actions runners** — prerequisite for automated deploys and preprod. Blocks env-isolation Phase 5 (CI/CD). Automated via `./scripts/server-setup.sh --role <backend|frontend> --gh-token <TOKEN>`. Requires a one-time registration token from GitHub repo → Settings → Actions → Runners → New self-hosted runner.
- [x] ~~**Backup strategy** — `scripts/backup.sh` (nightly cron, 7-day retention), `scripts/restore.sh`, ClickHouse backup disk configured in `infrastructure/clickhouse/config/backup_disk.xml`. Install with `./scripts/backup.sh --install-cron`.~~
- [ ] **Dev / Preprod / Prod environment isolation** — run three isolated stacks (shared Kafka + GPU, separate DBs/topics/ports) so changes can be tested end-to-end with real DAS data and a real frontend before rolling to prod. See [`TODO/plans/env-isolation.md`](plans/env-isolation.md)
- [ ] **Standardized dev environment** — `make dev` for simulation (laptop-friendly), `make dev-full` for recorded DAS replay (full pipeline, CPU fallback if no GPU). Includes test data recordings for reproducibility and non-regression. See [`TODO/plans/dev-environment.md`](plans/dev-environment.md)

## Medium Priority

- [ ] **Rewrite tests** — all AI-generated tests removed. Rebuild with meaningful unit, integration, and component tests across pipeline, backend, and frontend. Re-enable `make test` in Makefile/CI/CLAUDE.md when done. See [`TODO/plans/test-strategy.md`](plans/test-strategy.md)
- [ ] **Re-enable frontend typecheck in CI** — disabled in `.github/workflows/ci.yml` because committed code on `main` imports `@/lib/*` modules that were never tracked by git. Once those files (`src/lib/`) are committed and the `RealtimeProvider`/`ProtoState` type mismatches are resolved, uncomment the typecheck step.
- [ ] **Fix instant incident resolution in simulation** — incidents created during simulation mode appear to resolve immediately instead of staying open. Likely a timing or threshold issue in the simulation data generation or the incident lifecycle logic.
- [ ] **Fix incident snapshot data** — snapshot view for incidents currently shows a single data point per metric (speed / flow / occupancy) instead of a time-series window around the incident. Unclear whether the issue is in the backend ClickHouse query (fetching too narrow a window) or the frontend display (not rendering the full series). Needs investigation. Key files: `apps/monitoring/views.py` (`IncidentSnapshotView`, line ~171), `frontend/src/hooks/useIncidentSnapshot.ts`.
- [ ] **Real-time SHM data** — implement Structural Health Monitoring data flow end-to-end: simulated SHM data in the simulation engine for dev/demo, and actual SHM data ingestion in the pipeline (sensor source → Kafka → backend → WebSocket `shm_readings` channel). The frontend already subscribes to `shm_readings` but receives no real data.
- [x] ~~**Rollback strategy** — documented in `docs/ROLLBACK.md`. Deploy workflow already has auto-rollback; manual procedure covers git reset, single-service rebuild, DB restore, and migration reversal.~~
- [ ] **Log retention** — config committed (otelcol-config.yaml filelog receiver) but needs deploy verification on production server
- [ ] **Enable stricter ruff rules** — add `UP`, `B`, `SIM`, `RUF`, `C4` to both `pyproject.toml` configs. Pipeline: 326 violations (230 auto-fixable, mostly `UP` type hint modernization). Backend: 139 violations (75 are `RUF012` Django model false positives — ignore). Ignore `RUF012` and `RUF002` (French text) in backend config. Run `ruff check --fix` for the bulk, then manual fixes for the rest.

## Low Priority — Observability Roadmap

- [ ] **Deploy and verify Tempo datasource** — confirm traces are queryable in Grafana after deploying the updated datasources.yaml
- [ ] **Kafka trace propagation** — inject/extract W3C trace context in Kafka message headers so traces span producer → consumer across services
- [ ] **Log-trace correlation** — add `trace_id` and `span_id` fields to structured log output so Grafana can link logs to traces
- [ ] **Structured Django logging** — replace Django's default text logging with JSON structured output via `python-json-logger` for Loki parsing
- [ ] **Exemplars on histograms** — attach trace IDs as exemplars to Prometheus histogram metrics (inference latency, processing duration) for trace→metric drill-down

## Low Priority — Documentation

- [x] ~~**Per-service READMEs** — processor, ai_engine, backend, frontend~~

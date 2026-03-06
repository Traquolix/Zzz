# SequoIA — Outstanding Tasks

> Detailed plans live in `TODO/plans/`. Task history in `TODO/history.md`.

## High Priority

- [ ] **Install self-hosted GitHub Actions runners** — prerequisite for automated deploys and preprod. Blocks env-isolation Phase 5 (CI/CD). Instructions:
  ```bash
  # On each server (backend: beaujoin@192.168.99.113, frontend: frontend@134.59.98.100):
  mkdir -p ~/actions-runner && cd ~/actions-runner
  curl -o actions-runner-linux-x64.tar.gz -L \
    https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64-2.322.0.tar.gz
  tar xzf actions-runner-linux-x64.tar.gz
  # Get token: github.com/Traquolix/Zzz → Settings → Actions → Runners → New
  ./config.sh --url https://github.com/Traquolix/Zzz --token <TOKEN> --labels <backend|frontend>
  sudo ./svc.sh install && sudo ./svc.sh start
  ```
- [ ] **Backup strategy** — ClickHouse + PostgreSQL backup schedule. At minimum: nightly `pg_dump` and ClickHouse `BACKUP`. Data loss is unrecoverable without this.
- [ ] **Dev / Preprod / Prod environment isolation** — run three isolated stacks (shared Kafka + GPU, separate DBs/topics/ports) so changes can be tested end-to-end with real DAS data and a real frontend before rolling to prod. See [`TODO/plans/env-isolation.md`](plans/env-isolation.md)
- [ ] **Standardized dev environment** — `make dev` for simulation (laptop-friendly), `make dev-full` for recorded DAS replay (full pipeline, CPU fallback if no GPU). Includes test data recordings for reproducibility and non-regression. See [`TODO/plans/dev-environment.md`](plans/dev-environment.md)

## Medium Priority

- [ ] **Rewrite tests** — all AI-generated tests removed. Rebuild with meaningful unit, integration, and component tests across pipeline, backend, and frontend. Re-enable `make test` in Makefile/CI/CLAUDE.md when done. See [`TODO/plans/test-strategy.md`](plans/test-strategy.md)
- [ ] **Fix instant incident resolution in simulation** — incidents created during simulation mode appear to resolve immediately instead of staying open. Likely a timing or threshold issue in the simulation data generation or the incident lifecycle logic.
- [ ] **Fix incident snapshot data** — snapshot view for incidents currently shows a single data point per metric (speed / flow / occupancy) instead of a time-series window around the incident. Unclear whether the issue is in the backend ClickHouse query (fetching too narrow a window) or the frontend display (not rendering the full series). Needs investigation. Key files: `apps/monitoring/views.py` (`IncidentSnapshotView`, line ~171), `frontend/src/hooks/useIncidentSnapshot.ts`.
- [ ] **Real-time SHM data** — implement Structural Health Monitoring data flow end-to-end: simulated SHM data in the simulation engine for dev/demo, and actual SHM data ingestion in the pipeline (sensor source → Kafka → backend → WebSocket `shm_readings` channel). The frontend already subscribes to `shm_readings` but receives no real data.
- [ ] **Rollback strategy** — document manual rollback procedure alongside the deploy workflow's auto-rollback
- [ ] **Log retention** — config committed (otelcol-config.yaml filelog receiver) but needs deploy verification on production server

## Low Priority — Observability Roadmap

- [ ] **Deploy and verify Tempo datasource** — confirm traces are queryable in Grafana after deploying the updated datasources.yaml
- [ ] **Kafka trace propagation** — inject/extract W3C trace context in Kafka message headers so traces span producer → consumer across services
- [ ] **Log-trace correlation** — add `trace_id` and `span_id` fields to structured log output so Grafana can link logs to traces
- [ ] **Structured Django logging** — replace Django's default text logging with JSON structured output via `python-json-logger` for Loki parsing
- [ ] **Exemplars on histograms** — attach trace IDs as exemplars to Prometheus histogram metrics (inference latency, processing duration) for trace→metric drill-down

## Low Priority — Documentation

- [x] ~~**Per-service READMEs** — processor, ai_engine, backend, frontend~~

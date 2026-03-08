# SequoIA — Outstanding Tasks

> Detailed plans live in `TODO/plans/`. Task history in `TODO/history.md`.

## High Priority

- [ ] **Install self-hosted GitHub Actions runners** — prerequisite for automated deploys and preprod. Blocks env-isolation Phase 5 (CI/CD). Automated via `./scripts/server-setup.sh --role <backend|frontend> --gh-token <TOKEN>`. Requires a one-time registration token from GitHub repo → Settings → Actions → Runners → New self-hosted runner.
- [x] ~~**Backup strategy** — `scripts/backup.sh` (nightly cron, 7-day retention), `scripts/restore.sh`, ClickHouse backup disk configured in `infrastructure/clickhouse/config/backup_disk.xml`. Install with `./scripts/backup.sh --install-cron`.~~
- [ ] **Dev / Preprod / Prod environment isolation** — run three isolated stacks (shared Kafka + GPU, separate DBs/topics/ports) so changes can be tested end-to-end with real DAS data and a real frontend before rolling to prod. See [`TODO/plans/env-isolation.md`](plans/env-isolation.md)
- [ ] **Standardized dev environment** — `make dev` for simulation (laptop-friendly), `make dev-full` for recorded DAS replay (full pipeline, CPU fallback if no GPU). Includes test data recordings for reproducibility and non-regression. See [`TODO/plans/dev-environment.md`](plans/dev-environment.md)

## Medium Priority

- [ ] **Rewrite tests** — all AI-generated tests removed. Rebuild with meaningful unit, integration, and component tests across pipeline, backend, and frontend. Re-enable `make test` in Makefile/CI/CLAUDE.md when done. See [`TODO/plans/test-strategy.md`](plans/test-strategy.md)
- [x] ~~**Re-enable frontend typecheck in CI** — re-enabled in `.github/workflows/ci.yml`; `tsc --noEmit` passes clean.~~
- [x] ~~**Fix instant incident resolution in simulation** — enforced 2-minute minimum real-time duration for simulated incidents (was as low as 20s after 15x time compression).~~
- [x] ~~**Fix incident snapshot data** — fixed: backend aggregates detections into 1-second buckets (avg speed, flow, occupancy), serves 120 pre-computed points instead of raw detections. Payload dropped from ~1.2 MB to ~3-5 KB per poll.~~
- [ ] **Incident replay player** — interactive playback of the full 2-minute snapshot window (±60s around incident). Chart shows the complete window with a vertical incident marker at center; playback slider below the chart scrubs both a chart cursor and the map (detection dots color-coded by speed). Left half (pre-incident) fills immediately from rolling buffer, right half fills progressively as data is collected. See [`TODO/plans/incident-player.md`](TODO/plans/incident-player.md)
- [ ] **Realistic simulation engine** — overhaul the traffic simulation to be physically coherent: location-aware speed limits, time-of-day traffic patterns matching real Nice data, incident detection driven by actual vehicle behavior (speed drops, sudden stops) rather than random spawning. Incidents should emerge from the simulation, not be injected. See [`TODO/plans/simulation-overhaul.md`](TODO/plans/simulation-overhaul.md)
- [ ] **Real-time SHM data** — implement Structural Health Monitoring data flow end-to-end across three layers: (1) **Pipeline**: new SHM service or extension to ingest real sensor data (accelerometers, strain gauges on infrastructure) → Kafka `shm.readings` topic → ClickHouse storage. (2) **Simulation**: generate plausible SHM readings in the simulation engine (frequency drift, vibration patterns tied to traffic load) so the frontend works in dev/demo without real sensors. (3) **Frontend**: the SHM page currently uses static HDF5 demo data via REST; wire it to the WebSocket `shm_readings` channel for live streaming updates, with the same flow toggle (live/sim) as traffic data.
- [x] ~~**Rollback strategy** — documented in `docs/ROLLBACK.md`. Deploy workflow already has auto-rollback; manual procedure covers git reset, single-service rebuild, DB restore, and migration reversal.~~
- [ ] **Channel-to-road mapping and bad coupling** — channels are currently assumed to follow the road linearly, but the fiber may cross between unrelated roads, run through non-road areas, or have poor acoustic coupling to the surface. Need a way to tag channel ranges with their actual road association (or mark them as dead/off-road), handle fibers that jump between roads, and exclude channels with bad coupling from detection and speed estimation. This affects the simulation (which assumes all channels are on-road), the map visualization (which interpolates positions along the fiber), and the pipeline (which processes all channels equally). Needs investigation and a plan.
- [ ] **Expandable side panel** — option to enlarge the side panel for more detail, or add a secondary bottom panel for supplementary info (e.g. snapshot charts, replay player, data tables) without leaving the map view
- [ ] **Centralize aggregation in backend** — the frontend currently computes occupancy, rolling averages, and per-second bucketing for section live stats (`useLiveStats.ts`) and formerly for snapshots. Move all aggregation math (avg speed, flow, occupancy formula) to the backend so the frontend only renders pre-computed points. Eliminates duplicated `AVG_VEHICLE_LENGTH` constants and occupancy formulas across frontend/backend. The occupancy formula is now copy-pasted 5 times across `simulation.py` (×3) and `views.py` (×2).
- [ ] **Optimistic flow switch rollback** — `RealtimeProvider.tsx` `setFlow` updates local state immediately before the server confirms via WebSocket. If the send fails silently or the server responds with an error, frontend and backend disagree on the active flow. The `flow_changed` server response is currently ignored. Store the previous flow and revert on error, or defer the local state update until `flow_changed` arrives.
- [ ] **Add type hints to untyped backend functions** — 7 functions missing return/param annotations: `views.py` (`_get_fiber_ids_or_none`, `_incidents_cache_key`, `_stats_cache_key`, `_verify_infrastructure_access`), `consumers.py` (`_setup_user`, `_query_initial_incidents`, `_query_initial_fibers`).
- [ ] **Unify broadcast helpers** — `kafka_bridge._org_broadcast` and `simulation._broadcast_to_orgs` / `_broadcast_per_org` implement the same org-scoped broadcast pattern with slightly different signatures. Extract a single shared implementation (e.g., `apps/realtime/broadcast.py`) that both files import. SHM broadcast (`_broadcast_shm`) was deduplicated within each file but is also duplicated across the two files — include it in the unification. Also eliminate the separate `infra_org_map` — infrastructure items already have a `fiber_id`, so SHM org-scoping can be derived from `fiber_org_map` instead of maintaining a redundant mapping.
- [ ] **Log retention** — config committed (otelcol-config.yaml filelog receiver) but needs deploy verification on production server
- [ ] **Enable stricter ruff rules** — add `UP`, `B`, `SIM`, `RUF`, `C4` to both `pyproject.toml` configs. Pipeline: 326 violations (230 auto-fixable, mostly `UP` type hint modernization). Backend: 139 violations (75 are `RUF012` Django model false positives — ignore). Ignore `RUF012` and `RUF002` (French text) in backend config. Run `ruff check --fix` for the bulk, then manual fixes for the rest.

## Low Priority — Language Migrations

- [ ] **Rewrite pipeline in Rust** — migrate `services/pipeline/` (Processor + AI Engine) to Rust for lower latency, smaller images, and stronger type safety. ONNX export for DTAN model, `rdkafka` for Kafka, `ndarray` for signal processing. Phased: Processor first (side-by-side with Python AI Engine), then full AI Engine. See [`TODO/plans/rust-migration.md`](plans/rust-migration.md)
- [ ] **Rewrite backend in Go** — migrate `services/platform/backend/` (Django) to Go for performance and simpler deployment. Needs investigation and planning.

## Low Priority — Observability Roadmap

- [ ] **Deploy and verify Tempo datasource** — confirm traces are queryable in Grafana after deploying the updated datasources.yaml
- [ ] **Kafka trace propagation** — inject/extract W3C trace context in Kafka message headers so traces span producer → consumer across services
- [ ] **Log-trace correlation** — add `trace_id` and `span_id` fields to structured log output so Grafana can link logs to traces
- [ ] **Structured Django logging** — replace Django's default text logging with JSON structured output via `python-json-logger` for Loki parsing
- [ ] **Exemplars on histograms** — attach trace IDs as exemplars to Prometheus histogram metrics (inference latency, processing duration) for trace→metric drill-down

## Low Priority — Documentation

- [x] ~~**Per-service READMEs** — processor, ai_engine, backend, frontend~~

# SequoIA — Outstanding Tasks

> Detailed plans live in `TODO/plans/`. Task history in `TODO/history.md`.
> Each task links to its GitHub issue for discussion and traceability.

## Current Sprint

1. [x] **Unify broadcast helpers** [#17] — PR #44, merged
2. [x] **IncidentActionView not flow-aware** [#35] — PR #48, merged
3. [x] **Extract `group_by_org` helper** [#45] — PR #51, merged
4. [x] **Route SHM broadcasts via `fiber_org_map`** [#46] — PR #52, merged
5. [x] **SectionHistoryView not flow-aware** [#40] — PR #55, merged
6. [x] **Make direction a first-class field everywhere** [#58] — PR #59, merged
7. [x] **Consolidate dual Incident type definitions** [#42] — PR #65
8. [ ] **Remove dead frontend type files** [#61] — tech-debt, delete unused types in `src/types/` (selection.ts, admin.ts, report.ts, user.ts, section.ts, metrics.ts)
9. [x] **Replace `fiberLineId()` composite keys with structured keys** [#62] — PR #65
10. [ ] **Rename Proto-prefixed types** [#66] — refactor, rename ProtoIncident/ProtoState/ProtoAction to meaningful names
11. [ ] **Remove SQLite, use PostgreSQL + Redis everywhere** [#67] — infrastructure, switch dev/test from SQLite/in-memory to PostgreSQL + Redis, spin up all deps in `make dev`
12. [ ] **Frontend: poll section history API** [#54] — enhancement, replace client-side accumulation with periodic API polling
13. [ ] **Sim stats: `detectionsPerSecond` always 0** [#41] — enhancement
14. [ ] **Optimistic flow switch rollback** [#15] — bug, frontend/backend flow state desync

## High Priority

- [ ] **Install self-hosted GitHub Actions runners** [#5] — prerequisite for automated deploys and preprod. Blocks env-isolation Phase 5 (CI/CD). Automated via `./scripts/server-setup.sh --role <backend|frontend> --gh-token <TOKEN>`. Requires a one-time registration token from GitHub repo → Settings → Actions → Runners → New self-hosted runner.
- [ ] **Dev / Preprod / Prod environment isolation** [#6] — run three isolated stacks (shared Kafka + GPU, separate DBs/topics/ports) so changes can be tested end-to-end with real DAS data and a real frontend before rolling to prod. See [`TODO/plans/env-isolation.md`](plans/env-isolation.md)
- [ ] **Standardized dev environment** [#7] — `make dev` for simulation (laptop-friendly), `make dev-full` for recorded DAS replay (full pipeline, CPU fallback if no GPU). Includes test data recordings for reproducibility and non-regression. See [`TODO/plans/dev-environment.md`](plans/dev-environment.md)

## Medium Priority

- [ ] **Add direction awareness to backend-only features** [#63] — tech-debt, add direction filtering/grouping to reports, exports, alerting; audit unused WS channels
- [ ] **Rewrite tests** [#8] — all AI-generated tests removed. Rebuild with meaningful unit, integration, and component tests across pipeline, backend, and frontend. Re-enable `make test` in Makefile/CI/CLAUDE.md when done. See [`TODO/plans/test-strategy.md`](plans/test-strategy.md)
- [ ] **Incident replay player** [#9] — interactive playback of the full 2-minute snapshot window (±60s around incident). Chart shows the complete window with a vertical incident marker at center; playback slider below the chart scrubs both a chart cursor and the map (detection dots color-coded by speed). Left half (pre-incident) fills immediately from rolling buffer, right half fills progressively as data is collected. See [`TODO/plans/incident-player.md`](TODO/plans/incident-player.md)
- [ ] **Realistic simulation engine** [#10] — overhaul the traffic simulation to be physically coherent: location-aware speed limits, time-of-day traffic patterns matching real Nice data, incident detection driven by actual vehicle behavior (speed drops, sudden stops) rather than random spawning. Incidents should emerge from the simulation, not be injected. See [`TODO/plans/simulation-overhaul.md`](TODO/plans/simulation-overhaul.md)
- [ ] **Real-time SHM data** [#11] — implement Structural Health Monitoring data flow end-to-end across three layers: (1) **Pipeline**: new SHM service or extension to ingest real sensor data (accelerometers, strain gauges on infrastructure) → Kafka `shm.readings` topic → ClickHouse storage. (2) **Simulation**: generate plausible SHM readings in the simulation engine (frequency drift, vibration patterns tied to traffic load) so the frontend works in dev/demo without real sensors. (3) **Frontend**: the SHM page currently uses static HDF5 demo data via REST; wire it to the WebSocket `shm_readings` channel for live streaming updates, with the same flow toggle (live/sim) as traffic data.
- [ ] **Channel-to-road mapping and bad coupling** [#12] — channels are currently assumed to follow the road linearly, but the fiber may cross between unrelated roads, run through non-road areas, or have poor acoustic coupling to the surface. Need a way to tag channel ranges with their actual road association (or mark them as dead/off-road), handle fibers that jump between roads, and exclude channels with bad coupling from detection and speed estimation. This affects the simulation (which assumes all channels are on-road), the map visualization (which interpolates positions along the fiber), and the pipeline (which processes all channels equally). Needs investigation and a plan.
- [ ] **Expandable side panel** [#13] — option to enlarge the side panel for more detail, or add a secondary bottom panel for supplementary info (e.g. snapshot charts, replay player, data tables) without leaving the map view
- [ ] **Move sections from ClickHouse to PostgreSQL** [#33] — section definitions are CRUD config metadata stored in ClickHouse (ReplacingMergeTree soft-delete), but should be a Django model in PostgreSQL like infrastructure. Fixes: sections don't work in sim mode / CH downtime, no admin panel, no FK constraints. Section history (`detection_1m`) stays in ClickHouse for live flow; for sim flow, compute from the simulation detection buffer in memory.
- [ ] **Incident browsing and navigation** [#31] — the simulation now retains ~1 month of incidents (~10,000). The current flat list doesn't scale — need pagination, filtering (by fiber, severity, type, status, date range), sorting, and search. Consider a dedicated incident history page or a scrollable/virtualized list in the side panel.
- [ ] **Centralize aggregation in backend** [#14] — the frontend currently computes occupancy, rolling averages, and per-second bucketing for section live stats (`useLiveStats.ts`) and formerly for snapshots. Move all aggregation math (avg speed, flow, occupancy formula) to the backend so the frontend only renders pre-computed points. Eliminates duplicated `AVG_VEHICLE_LENGTH` constants and occupancy formulas across frontend/backend. The occupancy formula is now copy-pasted 5 times across `simulation.py` (×3) and `views.py` (×2).
- [ ] **Optimistic flow switch rollback** [#15] — `RealtimeProvider.tsx` `setFlow` updates local state immediately before the server confirms via WebSocket. If the send fails silently or the server responds with an error, frontend and backend disagree on the active flow. The `flow_changed` server response is currently ignored. Store the previous flow and revert on error, or defer the local state update until `flow_changed` arrives.
- [ ] **Add type hints to untyped backend functions** [#16] — 5 functions missing return/param annotations: `views.py` (`_get_fiber_ids_or_none`, `_verify_infrastructure_access`), `consumers.py` (`_setup_user`, `_query_initial_incidents`, `_query_initial_fibers`). (`_incidents_cache_key` and `_stats_cache_key` were removed — replaced by typed `build_org_cache_key` in `apps/shared/utils.py`.)
- [ ] **Extract `group_by_org` helper** [#45] — deduplicate the "group items by org" logic used in both broadcast and alerting code across `kafka_bridge.py` and `simulation.py`. Also refactor `broadcast_per_org` to use it internally.
- [ ] **Route SHM broadcasts via `fiber_org_map`** [#46] — infrastructure already has `fiber_id`; eliminate the redundant `infra_org_map` and route SHM through the same `fiber_org_map` as detections/incidents.
- [ ] **Per-user channel permissions** [#47] — allow restricting users to specific WebSocket channels (detections, incidents, SHM, etc.) within their org. Filter at group subscription time in the WebSocket consumer.
- [ ] **Sim stats: `detectionsPerSecond` always 0** [#41] — simulation stats endpoint returns zero for detections per second.
- [ ] **Remove competing Kafka retention policies** [#34] — `das.raw.carros` is 11 GB on disk because `retention.bytes` (10 GB) triggers before `retention.ms` (24h). Remove `retention.bytes` everywhere (broker defaults + per-topic configs in `kafka-setup`) so only 24h time-based retention applies.
- [ ] **Log retention** [#18] — config committed (otelcol-config.yaml filelog receiver) but needs deploy verification on production server
- [ ] **Enable stricter ruff rules** [#19] — add `UP`, `B`, `SIM`, `RUF`, `C4` to both `pyproject.toml` configs. Pipeline: 326 violations (230 auto-fixable, mostly `UP` type hint modernization). Backend: 139 violations (75 are `RUF012` Django model false positives — ignore). Ignore `RUF012` and `RUF002` (French text) in backend config. Run `ruff check --fix` for the bulk, then manual fixes for the rest.
- [ ] **Build per-service PR review checklists** [#29] — document service-specific review rules (backend: flow-aware endpoints, `@clickhouse_fallback`, broadcast helpers, i18n; pipeline: Avro compat, config hot-reload; frontend: TBD). Grows organically as patterns are discovered in reviews.
- [ ] **Consolidate task tracking — TODO.md vs GitHub Issues** [#39] — every task is tracked in both TODO.md and GitHub Issues, creating redundant maintenance and drift risk. Pick one source of truth.
- [ ] **Fix section creation overlay** [#38] — click position on the map doesn't match where the overlay/marker appears, making it hard to precisely select channel ranges for section boundaries.
- [ ] **Rework WebSocket reconnecting banner visual** [#37] — the current reconnecting/disconnected banner is visually intrusive. Redesign to be less obtrusive (subtle top bar or toast) while still clearly communicating connection state.
- [ ] **Show version on BETA tag hover** [#30] — hovering the BETA tag in the UI should display the current version of pipeline, backend, and frontend. Versions injected at build/deploy time from a single source of truth.

## Low Priority — Language Migrations

- [ ] **Rewrite pipeline in Rust** [#20] — migrate `services/pipeline/` (Processor + AI Engine) to Rust for lower latency, smaller images, and stronger type safety. ONNX export for DTAN model, `rdkafka` for Kafka, `ndarray` for signal processing. Phased: Processor first (side-by-side with Python AI Engine), then full AI Engine. See [`TODO/plans/rust-migration.md`](plans/rust-migration.md)
- [ ] **Rewrite backend in Go** [#21] — migrate `services/platform/backend/` (Django) to Go for performance and simpler deployment. Needs investigation and planning.

## Low Priority — Observability Roadmap

- [ ] **Deploy and verify Tempo datasource** [#22] — confirm traces are queryable in Grafana after deploying the updated datasources.yaml
- [ ] **Kafka trace propagation** [#23] — inject/extract W3C trace context in Kafka message headers so traces span producer → consumer across services
- [ ] **Log-trace correlation** [#24] — add `trace_id` and `span_id` fields to structured log output so Grafana can link logs to traces
- [ ] **Structured Django logging** [#25] — replace Django's default text logging with JSON structured output via `python-json-logger` for Loki parsing
- [ ] **Exemplars on histograms** [#26] — attach trace IDs as exemplars to Prometheus histogram metrics (inference latency, processing duration) for trace→metric drill-down

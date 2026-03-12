# Task History

Completed tasks with dates and commit references.

> Tasks completed before 2026-03-08 predate the issue-driven workflow and have no associated GitHub issue.

## 2026-03-05

- **Server security hardening** — SSH key auth, password auth disabled on both servers
  - Copy SSH key to backend server
  - Disable password auth on backend server
  - Copy SSH key to frontend server
  - Disable password auth on frontend server
  - Password exposure mitigated (password auth disabled, exposed password no longer an SSH vector)
  - Commit: `f26cf6e` (infrastructure setup)

- **Verify production secrets** — confirmed all passwords in `/opt/Sequoia/.env` are real generated values (not CHANGE_ME). Manual verification, no commit.

- **Weekly dependency scan** — CI runs `pip-audit` / `npm audit` on `schedule: cron` (Monday 07:00 UTC)
  - Commit: `56d913c`

- **Remove AI-generated tests** — all test suites removed, to be rewritten manually (see [#8] for rebuild)
  - Commit: `b3dc6ef`

- **Infrastructure professionalization** — CLAUDE.md, ARCHITECTURE.md, CONTRIBUTING.md, pre-commit hooks, CI workflow, Makefile, deploy script, ruff/mypy config
  - Commit: `f26cf6e`

## 2026-03-06

- **Grafana observability fixes** — Tempo datasource, ClickHouse dashboard rewrite (speed_hires/count_hires → detection_hires), speed metric name fix, processor up metric fix, alert rule fix
  - Commit: `8f34b75`

- **Container log shipping** — OTel Collector filelog receiver config for Loki
  - Commit: `3844e30`

## 2026-03-07

- **Backup strategy** — `scripts/backup.sh` (nightly cron, 7-day retention), `scripts/restore.sh`, ClickHouse backup disk configured in `infrastructure/clickhouse/config/backup_disk.xml`. Install with `./scripts/backup.sh --install-cron`. *(Completed before issue-driven workflow)*

- **Rollback strategy** — documented in `docs/ROLLBACK.md`. Deploy workflow already has auto-rollback; manual procedure covers git reset, single-service rebuild, DB restore, and migration reversal. *(Completed before issue-driven workflow)*

- **Re-enable frontend typecheck in CI** — re-enabled in `.github/workflows/ci.yml`; `tsc --noEmit` passes clean. *(Completed before issue-driven workflow)*

- **Fix instant incident resolution in simulation** — enforced 2-minute minimum real-time duration for simulated incidents (was as low as 20s after 15x time compression). *(Completed before issue-driven workflow)*

- **Fix incident snapshot data** — backend aggregates detections into 1-second buckets (avg speed, flow, occupancy), serves 120 pre-computed points instead of raw detections. Payload dropped from ~1.2 MB to ~3-5 KB per poll. *(Completed before issue-driven workflow)*
  - Commits: `2664916`, `016bd2c`, `2b1e3a3`

- **Per-service READMEs** — processor, ai_engine, backend, frontend. *(Completed before issue-driven workflow)*

## 2026-03-08

- **IncidentListView sim/live cross-contamination** [#3] — IncidentListView fell back to sim data regardless of active flow. Fixed with flow-aware query param check.
  - Closed by PR #2

- **SHM broadcasts use inline group_send** [#4] — extracted `broadcast_shm` helper into `apps.realtime.broadcast`, used by both `kafka_bridge.py` and `simulation.py`.
  - Closed by PR #2

- **Unify broadcast helpers** [#17] — extracted `broadcast_to_orgs`, `broadcast_per_org`, `broadcast_shm`, `load_fiber_org_map`, `load_infra_org_map` into `apps/realtime/broadcast.py`. Removed ~200 lines of duplication across `kafka_bridge.py` and `simulation.py`. Made `flow` a required keyword-only parameter on all broadcast functions. Fixed stale closure bug in kafka bridge's `broadcast` callback via `nonlocal`. Updated doc references in CLAUDE.md, pr-review-agent.md, PR template, and history.
  - Closed by PR #44

- **IncidentActionView not flow-aware** [#35] — added `FlowAwareMixin` with `initial()` override to reject sim flow with 400. Uses `ParseError` for consistent `{"detail": "..."}` response shape.
  - Closed by PR #48

- **Extract `group_by_org` helper** [#45] — deduplicated "group items by org" logic across kafka_bridge.py and simulation.py.
  - Closed by PR #51

- **Route SHM broadcasts via `fiber_org_map`** [#46] — eliminated redundant `infra_org_map`, route SHM through `fiber_org_map`.
  - Closed by PR #52

- **SectionHistoryView not flow-aware** [#40] — flow-aware section history with resolution tiers and sim buffers.
  - Closed by PR #55

- **Make direction a first-class field everywhere** [#58] — stopped encoding direction in fiber_id strings.
  - Closed by PR #59

- **Consolidate dual Incident type definitions** [#42] — merged Prototype vs canonical Incident types.
  - Closed by PR #65

- **Replace `fiberLineId()` composite keys** [#62] — switched to structured keys.
  - Closed by PR #65

## 2026-03-09

- **Sim/live data flow switching** [#43] — full sim/live toggle across all endpoints and WebSocket channels.
  - Closed by PR #2

- **Frontend: poll section history** [#54] — replaced client-side accumulation with API polling.
  - Closed by PR #69

- **Optimistic flow switch rollback** [#15] — defer flow switch until server confirms, rollback on failure.
  - Closed by PR #71

- **Move CRUD config tables to PostgreSQL** [#33] — sections, danger zones, actors out of ClickHouse into Django models.
  - Closed by PR #73

- **Batch section history endpoint** [#70] — parameterized UNION ALL, validated sectionIds.
  - Closed by PR #75

- **Fix section creation overlay** [#38] — corrected channel number offset in click handler.
  - Closed by PR #76

- **Expand side panel** [#72] — wider default, more readable charts and data tables.
  - Closed by PR #78

- **3D vehicle popups** [#81] — clickable popups with speed-colored info.
  - Closed by PR #82, #83

- **Vehicle popup consolidation** — legend gap fix, smooth open/close tracking, expanded panel close animation.
  - Closed by PR #83

- **Realistic simulation engine** [#10] — physically coherent traffic, location-aware speeds, emergent incidents.
  - Closed by PR #84

- **Replace SQLite with PostgreSQL + Redis** [#67] — zero-to-working `make dev`.
  - Closed by PR #68

- **Drop unused ClickHouse tables and columns** [#64] — removed 24 unused columns from fiber_incidents, 2 from fiber_cables.
  - Closed by PR #96

- **Reject export on simulation flow** [#49]
  - Closed by PR #95

- **Spectral heatmap initial mount race** — resolved RAF/ResizeObserver race in useDebouncedResize.
  - Closed by PR #94

- **ClickHouse migrations on deploy** — hardened migration command and command() helper.
  - Closed by PR #92

- **Incident detection tuning** — tuned for 30x time acceleration.
  - Closed by PR #91

- **Deploy fixes** — seed infrastructure on deploy, NO_PROXY for Docker service names, only restart app services, kafka-setup DNS race, Dockerfile stale schema copy, pyproject.toml in Docker build context.
  - Closed by PRs #85, #86, #87, #88, #89, #90

## 2026-03-10 – 2026-03-11

- **SHM caching** [#93] — client-side caching, React Query, eliminated redundant API calls.
  - Closed by PR #97

- **SHM caching follow-up** — timezone handling, peaks default day, numpy vectorization.
  - Closed by PR #105

- **Consolidate ClickHouse migrations, fix Redis pub/sub event loop** — migration consolidation and async event loop fix.
  - Closed by PR #106

- **ClickHouse ILLEGAL_AGGREGATION on batch-history** [#107] — renamed speed alias to speed_avg.
  - Closed by PR #107

- **Bump GitHub Actions to v6** — Node.js 24 compatibility.
  - Closed by PR #108

- **Remove DEFAULT on Kafka engine column** [#109] — was breaking ClickHouse init.
  - Closed by PR #109

- **Flow and occupancy always zero in live mode** — use float for samples to prevent truncation.
  - Closed by PR #110

- **Warm SHM cache at startup, fix Mapbox zoom expression** [#104 partial] — cache warmup on AppConfig.ready(), fixed zoom expression.
  - Closed by PR #111

## 2026-03-12

- **Install self-hosted GitHub Actions runners** [#5] — prerequisite for automated deploys.
  - Closed manually

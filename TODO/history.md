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

- **SHM broadcasts use inline group_send** [#4] — extracted `_broadcast_shm` helpers in both `kafka_bridge.py` and `simulation.py`.
  - Closed by PR #2

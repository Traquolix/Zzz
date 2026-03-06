# Task History

Completed tasks with dates and commit references.

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

- **Remove AI-generated tests** — all test suites removed, to be rewritten manually
  - Commit: `b3dc6ef`

- **Infrastructure professionalization** — CLAUDE.md, ARCHITECTURE.md, CONTRIBUTING.md, pre-commit hooks, CI workflow, Makefile, deploy script, ruff/mypy config
  - Commit: `f26cf6e`

## 2026-03-06

- **Grafana observability fixes** — Tempo datasource, ClickHouse dashboard rewrite (speed_hires/count_hires → detection_hires), speed metric name fix, processor up metric fix, alert rule fix
  - Commit: `8f34b75`

- **Container log shipping** — OTel Collector filelog receiver config for Loki
  - Commit: `3844e30`

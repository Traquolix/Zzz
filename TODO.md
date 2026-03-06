# SequoIA — Outstanding Tasks

## URGENT — Server Security

- [x] ~~**Change passwords on both servers**~~ — mitigated: password auth disabled on backend, exposed password no longer an SSH vector
- [x] ~~**Copy SSH key to backend server**~~
- [x] ~~**Disable password auth on backend server**~~
- [x] ~~Copy SSH key to frontend server~~
- [x] ~~**Disable password auth on frontend server**~~

## Deployment & Operations

- [ ] **Install self-hosted GitHub Actions runners** — instructions:
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
- [ ] **Rollback strategy** — document manual rollback procedure alongside the deploy workflow's auto-rollback
- [ ] **Backup strategy** — ClickHouse + PostgreSQL backup schedule. At minimum: nightly `pg_dump` and ClickHouse `BACKUP`
- [x] ~~**Verify production secrets**~~ — confirmed: all passwords in `/opt/Sequoia/.env` are real generated values

## Monitoring & Reliability

- [ ] **Log retention** — config committed (otelcol-config.yaml filelog receiver) but needs deploy verification on production server
- [x] ~~Weekly dependency scan~~ — CI runs `pip-audit` / `npm audit` on `schedule: cron` (Monday 07:00 UTC)

## Observability Roadmap

- [ ] **Kafka trace propagation** — inject/extract W3C trace context in Kafka message headers so traces span producer → consumer across services
- [ ] **Log-trace correlation** — add `trace_id` and `span_id` fields to structured log output so Grafana can link logs to traces
- [ ] **Structured Django logging** — replace Django's default text logging with JSON structured output via `python-json-logger` for Loki parsing
- [ ] **Exemplars on histograms** — attach trace IDs as exemplars to Prometheus histogram metrics (inference latency, processing duration) for trace→metric drill-down
- [ ] **Deploy and verify Tempo datasource** — confirm traces are queryable in Grafana after deploying the updated datasources.yaml

## Code Quality

- [ ] **Rewrite tests** — all AI-generated unit tests removed. Write meaningful tests manually for pipeline, backend, and frontend. Once done, re-add `make test` targets to Makefile, test jobs to CI workflow, and `make test` to the validation command in CLAUDE.md.
- [ ] **Per-service READMEs** — processor, ai_engine, backend (frontend has one)

# SequoIA — Outstanding Tasks

## URGENT — Server Security

- [ ] **Change passwords on both servers** — passwords were exposed in a conversation. Do this the moment servers are reachable.
  - Backend: `beaujoin@192.168.99.113` — `passwd`
  - Frontend: `frontend@134.59.98.100` — `passwd`
- [ ] **Copy SSH key to backend server** — `ssh-copy-id beaujoin@192.168.99.113` (blocked: server unreachable)
- [ ] **Disable password auth on backend server** — edit `/etc/ssh/sshd_config`, set `PasswordAuthentication no`, restart sshd
- [x] ~~Copy SSH key to frontend server~~
- [ ] **Disable password auth on frontend server** — do after confirming key auth works

## Deployment & Operations

- [ ] **Install self-hosted GitHub Actions runners** — blocked: servers unreachable. Instructions:
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
- [ ] **Verify production secrets** — confirm `.env` on production has real passwords, not `CHANGE_ME` placeholders

## Monitoring & Reliability

- [ ] **Log retention** — verify logs are shipped to Loki via otel-lgtm. Docker logs vanish on container restart without this.
- [x] ~~Weekly dependency scan~~ — CI runs `pip-audit` / `npm audit` on `schedule: cron` (Monday 07:00 UTC)

## Code Quality

- [ ] **Rewrite tests** — all AI-generated unit tests removed. Write meaningful tests manually for pipeline, backend, and frontend.
- [ ] **Per-service READMEs** — processor, ai_engine, backend (frontend has one)

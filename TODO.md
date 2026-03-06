# SequoIA — Outstanding Tasks

## URGENT — Server Security

- [ ] **Change passwords on both servers** — passwords were exposed in a conversation. Do this the moment servers are reachable.
  - Backend: `beaujoin@192.168.99.113` — `passwd`
  - Frontend: `frontend@134.59.98.100` — `passwd`
- [ ] **Copy SSH key to backend server** — `ssh-copy-id beaujoin@192.168.99.113` (blocked: server unreachable, ask user regularly)
- [ ] **Disable password auth on backend server** — edit `/etc/ssh/sshd_config`, set `PasswordAuthentication no`, restart sshd
- [x] **Copy SSH key to frontend server** — done
- [ ] **Disable password auth on frontend server** — do after confirming key auth works

## Deployment & Operations

- [ ] **Install self-hosted GitHub Actions runner on backend server** (label: `backend`). Blocked: server unreachable.
  ```bash
  # 1. SSH into backend server
  ssh beaujoin@192.168.99.113

  # 2. Create runner directory
  mkdir -p ~/actions-runner && cd ~/actions-runner

  # 3. Download runner
  curl -o actions-runner-linux-x64.tar.gz -L \
    https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64-2.322.0.tar.gz
  tar xzf actions-runner-linux-x64.tar.gz

  # 4. Get token: github.com/Traquolix/Zzz → Settings → Actions → Runners → New self-hosted runner
  #    GitHub shows a one-time token. Paste it below:
  ./config.sh --url https://github.com/Traquolix/Zzz --token <PASTE_TOKEN> --labels backend

  # 5. Install as system service (survives reboots)
  sudo ./svc.sh install
  sudo ./svc.sh start
  sudo ./svc.sh status  # should show "active (running)"
  ```
- [ ] **Install self-hosted GitHub Actions runner on frontend server** (label: `frontend`). Same steps as above:
  ```bash
  ssh frontend@134.59.98.100
  mkdir -p ~/actions-runner && cd ~/actions-runner
  curl -o actions-runner-linux-x64.tar.gz -L \
    https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64-2.322.0.tar.gz
  tar xzf actions-runner-linux-x64.tar.gz
  # Get a NEW token from GitHub (same page, tokens are single-use)
  ./config.sh --url https://github.com/Traquolix/Zzz --token <PASTE_TOKEN> --labels frontend
  sudo ./svc.sh install
  sudo ./svc.sh start
  ```
- [x] **Add `VITE_MAPBOX_TOKEN` as a GitHub Actions secret** — needed for frontend deploy workflow
- [ ] **Rollback strategy** — tag releases with git SHA, document how to roll back (`git reset --hard <sha> && docker compose up -d`). The deploy workflow has auto-rollback, but manual procedure should be documented too.
- [ ] **Database migration safety** — add PR checklist item: "migrations reviewed, no destructive operations (DROP COLUMN, DROP TABLE) without explicit approval". Consider removing auto-migrate from `entrypoint.sh` for destructive migrations.
- [ ] **Deploy failure alerting** — set up Grafana alert or Discord webhook that fires when a Docker service goes unhealthy after deploy
- [ ] **Backup strategy** — decide on ClickHouse + PostgreSQL backup schedule and storage. At minimum: nightly `pg_dump` and ClickHouse `BACKUP` to a second disk or offsite.
- [ ] **Verify production secrets** — confirm `.env` on production server has real passwords, not `CHANGE_ME` placeholders. The entrypoint.sh blocks startup if they're still set, but verify manually.

## Monitoring & Reliability

- [ ] **Log retention** — verify logs are being shipped to Loki via otel-lgtm. Docker logs disappear on container restart without this.
- [ ] **Load/stress testing** — verify pipeline handles sustained 125 Hz × 2800 channels. Test reconnection burst from DAS interrogator.
- [ ] **Nightly dependency scan** — add scheduled GitHub Actions workflow running `pip-audit` / `npm audit` weekly, not just on PRs

## Infrastructure

- [x] **Pin `:latest` Docker images** — `kafka-ui` and `otel-lgtm` in `docker-compose.yml`
- [ ] **Git LFS for model weights** — when adding new models, use `git lfs track "*.pth" "*.pt"`. Current active weights are gitignore-exempted. Legacy weights removed in codebase-consolidation.

## Code Quality

- [ ] **Per-service READMEs** — processor, ai_engine, backend, frontend
- [ ] **Remove unused experiment venvs** — `services/pipeline/experiments/.venv/` and `vehicle_detection_tuning/.venv/`

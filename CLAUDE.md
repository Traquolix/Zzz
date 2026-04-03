# SequoIA — Claude Code Project Instructions

> Domain context (DAS physics, key concepts, data flow, deployment topology):
> see [`docs/DAS-PRIMER.md`](docs/DAS-PRIMER.md)

## Workflow

### Issue-Driven Development

Work is tracked through GitHub issues. Before starting any task:

1. **Find or create the GitHub issue.** One issue per concern. Label it (`bug`, `enhancement`, `refactor`, `tech-debt`, `infrastructure`, `performance`). Use the standard format from `.github/ISSUE_TEMPLATE/`.
2. **`TODO.md` is the sprint board** — it lists only the current sprint priorities. The backlog lives in GitHub Issues. Do not duplicate backlog items in TODO.md.
3. **Branch names reference the issue:** `feat/42-flow-switching`, `fix/15-token-refresh`.

### Task Pattern

1. **Create a branch** from main: `feat/N-description`, `fix/N-description`, `refactor/N-description`, `chore/N-description`, or `perf/N-description` (where N is the issue number)
2. **Write tests first** when adding features or fixing bugs
3. **Implement** the change
4. **Validate**: run `make lint && make typecheck`
5. **Commit** with conventional message: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`. **Never add `Co-Authored-By` trailers** — commits should look like they come from the developer alone. **Never add "Generated with Claude Code" footers** to PR descriptions.
6. **Push**: `git push -u origin <branch>`
7. **Open a PR**: `gh pr create --title "short title" --body "Closes #N\n\n## Summary\n- what changed\n- why"` — the `Closes #N` line is **mandatory** so GitHub auto-closes the issue on merge.
8. **Never merge** — the human reviews and merges PRs
9. **Address PR feedback** — when asked to fix PR comments, read them with
   `gh api repos/Traquolix/Zzz/pulls/<number>/comments` and
   `gh pr view <number> --comments`, then fix, commit, and push

If the user doesn't specify a branch name, ask for one. Never work directly on main.

### PR Hygiene

- **One concern per PR.** If you notice an unrelated issue while working, create a separate issue and branch for it. Never bundle unrelated fixes.
- **Keep PRs reviewable.** If the diff exceeds ~500 lines of logic changes, consider splitting into smaller PRs. Formatting-only changes (reindentation, import reordering) should be a separate commit so reviewers can skip them.
- **Always include `Closes #N`** (or `Fixes #N`) in the PR body so the issue auto-closes on merge. If the PR doesn't fully resolve an issue, use `Relates to #N` instead.
- **No cross-contamination between sim and live paths.** Every REST endpoint and WebSocket handler that can serve both simulation and live data must be flow-aware. Never fall back from one data source to the other without checking the user's active flow.
- **Use existing patterns.** Before writing inline error handling, check if a decorator or helper already exists (e.g., `@clickhouse_fallback`). Before writing inline broadcasts, use the shared broadcast helpers (`broadcast_per_org`, `broadcast_to_orgs`, `broadcast_shm` from `apps.realtime.broadcast`). Consistency matters more than local convenience.

### After Merge — Deploying

Deployment is triggered automatically by merging to main via `.github/workflows/deploy.yml`
(with auto-rollback on health check failure). Manual fallback:

```bash
# Backend server
ssh beaujoin@192.168.99.113
cd /opt/Sequoia && git pull origin main && docker compose up -d

# Frontend server (if frontend changed)
# Build locally, then:
scp -r services/platform/frontend/dist/* frontend@134.59.98.100:/var/www/sequoia/
```

## Validation

**Run before considering any task complete:**

```bash
make lint && make typecheck
```

If any step fails, fix the issue and re-run. Do not report completion until all pass.

### AI Engine Tests

```bash
make test              # Run AI engine test suite (243 tests, ~55s)
```

Tests run in CI on every PR. The suite includes golden snapshot tests that compare
inference output against a saved reference from real DAS data.

**When you update the DTAN model weights, detection thresholds, or preprocessing:**

```bash
make snapshot-confirm  # Re-record golden baselines from current model
```

This regenerates `services/pipeline/tests/ai_engine/fixtures/*.npz`. Review the
changes (detection count, speed range), then commit the updated fixtures alongside
your code change. If you skip this, the snapshot tests will fail in CI.

## Makefile — Always Use It

The Makefile is the single entry point for all dev operations. **Never run `python3`,
`ruff`, `mypy`, or `pip` directly** — always use the Makefile targets, which use
service-local venvs automatically.

| Task | Command |
|------|---------|
| First-time setup (venvs + deps) | `make setup` |
| Start dev servers | `make dev` |
| Lint all code | `make lint` |
| Type-check all code | `make typecheck` |
| Auto-format | `make format` |
| Security scan | `make security` |
| Run tests | `make test` |
| Update AI golden snapshots | `make snapshot-confirm` |
| Run AI benchmarks | `make bench` |
| Save benchmark baseline | `make bench-save` |
| Full CI pipeline | `make ci` |
| Docker stack up/down | `make up` / `make down` |
| Rebuild one service | `make rebuild SERVICE=<name>` |
| View logs | `make logs SERVICE=<name>` |
| Manual backup | `make backup` |
| Restore from backup | `make restore BACKUP=--latest` |

If a venv is missing, run `make setup` first. The `make dev` target auto-creates the
backend venv on first run, but `make lint` and `make typecheck` expect venvs to exist.

## Conventions

### Python
- Formatter/linter: `ruff` only (NOT black). Line length 100.
- Python 3.10 everywhere (pipeline and backend). Must match Docker images.
- Type hints required on all new code.
- Import order: stdlib → third-party → local (enforced by ruff isort).
- Logging: `logging.getLogger(__name__)`. Never `print()`.
- Error handling: raise specific exceptions, never bare `except:`.
- Commit messages: conventional commits (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`).

### TypeScript (frontend)
- Strict TypeScript with ESLint.
- State management: Zustand stores for client state; React Query (`@tanstack/react-query`) for server state (data fetching, caching, background refetch).
- Styling: Tailwind CSS v4.
- Components: shadcn/ui base components.
- i18n: all user-visible strings in `src/i18n/en.json` and `src/i18n/fr.json`.

### Kafka
- All messages use Avro serialization with Schema Registry.
- Avro schemas must be backwards-compatible — add optional fields with defaults, never remove or rename fields.

### Backend
- Django views: always set `permission_classes` (`IsActiveUser`, `IsAdminOrSuperuser`, or `IsSuperuser`).
- All data queries are org-scoped — filter by `request.user.organization`. Never return unscoped data.
- ClickHouse queries: use `apps.shared.clickhouse.query()` — never create clients directly.
- URL routes: add to `apps/api/urls.py`.

### Testing
- Pipeline: `pytest` with `pytest-asyncio`. Fixtures in `tests/conftest.py`. Integration tests in `tests/integration/` (require Docker stack).
- Backend: `pytest-django` with `DJANGO_SETTINGS_MODULE=sequoia.settings.test`. Factory Boy factories in `tests/factories.py`. Key fixtures: `org`, `admin_user`, `authenticated_client`, `mock_clickhouse_query`.
- Frontend: `vitest` with `@testing-library/react`. Test files colocated: `Component.test.tsx` next to `Component.tsx`.

## Prohibitions

1. **Never modify files in `tests/integration/`** — integration tests are the contract.
2. **Never use `eval()`, `pickle.loads()`, `exec()`, or `subprocess(shell=True)`**.
3. **Never hardcode secrets** (passwords, tokens, API keys). Use environment variables.
4. **Never import across service boundaries** — `pipeline/` must not import from `platform/` and vice versa. Within pipeline, `processor/` and `ai_engine/` import from `shared/` and `config/` only, never from each other.
5. **Never add dependencies** without updating `pyproject.toml` (pipeline), `requirements.txt` (backend), or `package.json` (frontend).
6. **Never push directly to main** — always work on feature branches.
7. **Never skip validation** — always run `make lint && make typecheck`.
8. **Never commit `.env` files, secrets, or credentials**.
9. **Never modify model weight files** (`.pth`, `.pt`) — those are training outputs.
10. **Never modify Avro schemas** without considering backwards compatibility.
11. **Never create a Django view without `permission_classes`**.
12. **Never query ClickHouse or PostgreSQL without org-scoping** in the backend.

## Architectural Invariants

1. **One Kafka partition per fiber** — strict message ordering required. The sliding-window buffers in Processor and AI Engine produce wrong results with out-of-order messages.
2. **Single-instance multi-fiber** — one Processor and one AI Engine handle all fibers. The Processor subscribes to `das.raw.*` (topic pattern). The AI Engine dispatches per-fiber batches independently with GPU lock serialization.
3. **Config hot-reload** — `FiberConfigManager` watches `fibers.yaml` for changes. Never cache fiber config in module-level variables.
4. **Multi-tenant backend** — every API query is scoped to `request.user.organization`. Superuser admin endpoints are the only exception.
5. **ClickHouse 3-tier storage** — `detection_hires` (48h TTL) → `detection_1m` (90d) → `detection_1h` (forever). Aggregation is handled by ClickHouse materialized views, not Python.
6. **ServiceBase pattern** — all pipeline services inherit from `shared.service_base.ServiceBase`.
7. **Transformer hierarchy** — Consumer → Producer → Transformer → MultiTransformer → BufferedTransformer → RollingBufferedTransformer. Choose the right level for new services.

## PR Reviews

When asked to review a PR, follow the review format and checklist in `tools/prompts/pr-review-agent.md`.
That prompt covers hard rules (blocking), architectural invariants, code quality, and performance concerns
tailored to this project.

## Key Files

| File | Purpose |
|------|---------|
| `Makefile` | All dev operations — lint, typecheck, setup, dev servers, Docker |
| `docker-compose.yml` | Full production stack (Kafka, ClickHouse, PostgreSQL, Redis, services) |
| `docs/DAS-PRIMER.md` | DAS physics, domain concepts, data flow, deployment topology |
| `scripts/server-setup.sh` | Bootstrap a new server (Docker, GPU toolkit, GH runner, backups, nginx) |
| `scripts/backup.sh` | Nightly DB backup with cron self-install |
| `scripts/restore.sh` | Restore from backup |
| `tools/scripts/deploy.sh` | Manual deploy script (SSH-based) |
| `docs/ROLLBACK.md` | Rollback procedures |
| `TODO.md` | Current sprint priorities |

# SequoIA — Claude Code Project Instructions

## What This Project Is

SequoIA is a real-time traffic monitoring system built for the city of Nice (France) and IMREDD (university research lab). It uses **Distributed Acoustic Sensing (DAS)** — fiber optic cables buried under roads — to detect and count vehicles, estimate their speed, and classify them as cars or trucks. The goal is to replace traditional induction loop detectors (which are expensive and require road closures to install) with passive fiber sensing that covers kilometers of road with a single installation.

## How DAS Works — The Physics

A DAS **interrogator** (hardware unit, ASN OptoDAS) sends laser pulses into a standard telecom fiber optic cable. When a vehicle drives over the cable, the vibration slightly changes the backscattered light. The interrogator measures these changes at every point along the fiber, producing a 2D matrix:

- **Channels** (spatial axis): Each channel is a measurement point along the fiber, spaced ~5 meters apart. A 14km fiber = ~2800 channels. A channel is NOT a frequency — it's a physical location on the road.
- **Time** (temporal axis): The interrogator samples all channels simultaneously at 125 Hz (125 times per second).

So the raw data is: `[channels × time]` matrices arriving at 125 Hz. Each matrix row is the strain-rate signal at one point on the road. When a vehicle passes, it creates a characteristic V-shaped pattern in the space-time matrix (the "waterfall" visualization) — the slope of the V encodes the vehicle's speed.

## Key Domain Concepts

- **Fiber**: A physical fiber optic cable installation. Named by location: "carros" (D6202 road), "mathis" (Route de Turin), "promenade" (Promenade des Anglais). Each fiber has its own Kafka input topic (`das.raw.<fiber>`), its own Processor instance, and its own AI Engine instance.

- **Section**: A contiguous range of channels on a fiber that corresponds to a road segment where detection is performed. Not the entire fiber is useful — only portions that run parallel to roads. Each section is defined by a channel range (e.g., channels 1200-1716) in `fibers.yaml`. Each section gets its own speed estimation.

- **Detection**: A vehicle detection event produced by the AI engine. Contains: timestamp, estimated speed (km/h), direction (positive = one way, negative = other), vehicle type (car/truck), section ID, fiber ID.

- **DTAN** (Diffeomorphic Temporal Alignment Network): The deep learning model used for speed estimation. It learns to temporally align signal pairs from different channel positions — the amount of time-shift needed to align them encodes the vehicle speed. This is more robust than traditional cross-correlation because it handles non-linear signal distortions.

- **GLRT** (Generalized Likelihood Ratio Test): Statistical method used to count vehicles. After DTAN estimates the speed field, GLRT identifies individual peaks corresponding to separate vehicles.

- **Waterfall**: The 2D visualization of DAS data (channels × time). Called "waterfall" because time flows downward. Vehicle passages appear as diagonal lines — steeper = slower vehicle.

## Data Flow

```
DAS Interrogator (125 Hz, ~2800 channels)
    → Kafka (das.raw.<fiber>)
    → Processor: bandpass filter, temporal decimation (125→10.4 Hz),
      spatial decimation (keep every 3rd channel), common mode removal
    → Kafka (das.processed)
    → AI Engine: DTAN speed estimation, GLRT peak counting,
      car/truck classification
    → Kafka (das.detections) + ClickHouse (storage)
    → Django Backend: Kafka bridge → Redis → WebSocket
    → React Frontend: live map, waterfall, stats
```

## Deployment

Two servers at IMREDD (Université Côte d'Azur):
- **Backend server** (`beaujoin@192.168.99.113`): All Docker services (Kafka, ClickHouse, Processor, AI Engine, Django, Grafana). Has an NVIDIA RTX 4000 Ada GPU for ML inference. Code at `/opt/Sequoia`.
- **Frontend server** (`frontend@134.59.98.100`): nginx serving the React static build at `/var/www/sequoia/`.

The DAS interrogator sits in a telco cabinet on the road and pushes raw data directly to Kafka over the university network.

To set up a new server from scratch: `./scripts/server-setup.sh --role <backend|frontend>` (see script for options).

## Workflow

### Issue-Driven Development

Work is tracked through GitHub issues. Before starting any task:

1. **Find or create the GitHub issue.** One issue per concern. Label it (`bug`, `enhancement`, `refactor`, `tech-debt`, `infrastructure`). Use the standard format from `.github/ISSUE_TEMPLATE/` — every issue has four sections: **Problem**, **Proposed Solution**, **Files Involved**, **Acceptance Criteria**.
2. **`TODO.md` is for multi-issue epics and roadmap items** (e.g., "Realistic simulation engine" spanning multiple PRs). Single-task work items are GitHub issues, not TODO entries.
3. **Branch names reference the issue:** `feat/42-flow-switching`, `fix/15-token-refresh`.

### Task Pattern

1. **Create a branch** from main: `feat/N-description`, `fix/N-description`, `refactor/N-description`, or `perf/N-description` (where N is the issue number)
2. **Write tests first** when adding features or fixing bugs
3. **Implement** the change
4. **Validate**: run `make lint && make typecheck`
5. **Commit** with conventional message: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`
6. **Push**: `git push -u origin <branch>`
7. **Open a PR**: `gh pr create --title "short title" --body "Closes #N\n\n## Summary\n- what changed\n- why"`
8. **Never merge** — the human reviews and merges PRs
9. **Address PR feedback** — when asked to fix PR comments, read them with
   `gh api repos/Traquolix/Sequoia/pulls/<number>/comments` and
   `gh pr view <number> --comments`, then fix, commit, and push

If the user doesn't specify a branch name, ask for one. Never work directly on main.

### PR Hygiene

- **One concern per PR.** If you notice an unrelated issue while working, create a separate issue and branch for it. Never bundle unrelated fixes.
- **Keep PRs reviewable.** If the diff exceeds ~500 lines of logic changes, consider splitting into smaller PRs. Formatting-only changes (reindentation, import reordering) should be a separate commit so reviewers can skip them.
- **No cross-contamination between sim and live paths.** Every REST endpoint and WebSocket handler that can serve both simulation and live data must be flow-aware. Never fall back from one data source to the other without checking the user's active flow.
- **Use existing patterns.** Before writing inline error handling, check if a decorator or helper already exists (e.g., `@clickhouse_fallback`). Before writing inline broadcasts, use the shared broadcast helpers (`broadcast_per_org`, `broadcast_to_orgs`, `broadcast_shm` from `apps.realtime.broadcast`). Consistency matters more than local convenience.

### After Merge — Deploying

Deployment is manual until GitHub Actions runners are installed. After merging a PR:

```bash
# Backend server
ssh beaujoin@192.168.99.113
cd /opt/Sequoia && git pull origin main && docker compose up -d

# Frontend server (if frontend changed)
# Build locally, then:
scp -r services/platform/frontend/dist/* frontend@134.59.98.100:/var/www/sequoia/
```

Once GH runners are installed, merging to main triggers automatic deployment via
`.github/workflows/deploy.yml` (with auto-rollback on health check failure).

## Validation

**Run before considering any task complete:**

```bash
make lint && make typecheck
```

If any step fails, fix the issue and re-run. Do not report completion until all pass.

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
2. **Per-fiber service instances** — each Processor and AI Engine runs for one fiber only (configured via `FIBER_ID` env var). Scaling = more instances for more fibers.
3. **Config hot-reload** — `FiberConfigManager` watches `fibers.yaml` for changes. Never cache fiber config in module-level variables.
4. **Multi-tenant backend** — every API query is scoped to `request.user.organization`. Superuser admin endpoints are the only exception.
5. **ClickHouse 3-tier storage** — `detection_hires` (48h TTL) → `detection_1m` (90d) → `detection_1h` (forever). Aggregation is handled by ClickHouse materialized views, not Python.
6. **ServiceBase pattern** — all pipeline services inherit from `shared.service_base.ServiceBase`.
7. **Transformer hierarchy** — Consumer → Producer → Transformer → MultiTransformer → BufferedTransformer → RollingBufferedTransformer. Choose the right level for new services.

## PR Reviews

When asked to review a PR, follow the review format and checklist in `tools/prompts/pr-review-agent.md`.
That prompt covers hard rules (blocking), architectural invariants, code quality, and performance concerns
tailored to this project.

## Outstanding Tasks

Consult `TODO.md` at the start of each session for pending infrastructure, security, and cleanup tasks.

## Key Files

| File | Purpose |
|------|---------|
| `Makefile` | All dev operations — lint, typecheck, setup, dev servers, Docker |
| `docker-compose.yml` | Full production stack (Kafka, ClickHouse, PostgreSQL, Redis, services) |
| `scripts/server-setup.sh` | Bootstrap a new server (Docker, GPU toolkit, GH runner, backups, nginx) |
| `scripts/backup.sh` | Nightly DB backup with cron self-install |
| `scripts/restore.sh` | Restore from backup |
| `tools/scripts/deploy.sh` | Manual deploy script (SSH-based) |
| `docs/ROLLBACK.md` | Rollback procedures |
| `TODO.md` | Outstanding tasks |
| `TODO/plans/` | Detailed implementation plans |

# Contributing to SequoIA

## Branch Strategy

- `main` is protected — no direct pushes.
- All work on feature branches:
  - `feat/description` — new features
  - `fix/description` — bug fixes
  - `refactor/description` — code restructuring
  - `chore/description` — tooling, CI, dependencies
  - `docs/description` — documentation only
- Every branch corresponds to a GitHub issue.
- PRs require passing CI before merge.

## Commit Messages

Use conventional commits:

```
feat: add vehicle counting per section
fix: correct DTAN alignment window size
refactor: extract speed estimator from ai_engine main
chore: pin kafka-ui Docker image version
docs: add per-service README
test: add integration test for DLQ flow
```

Format: `<type>: <short description>`

- `feat:` — new feature visible to users or pipeline behavior change
- `fix:` — bug fix
- `refactor:` — code change that doesn't change behavior
- `chore:` — tooling, CI, dependencies, config
- `docs:` — documentation only
- `test:` — adding or modifying tests

## Development Workflow

### 1. Create an issue
Describe what you're building or fixing. Include acceptance criteria.

### 2. Create a branch
```bash
git checkout -b feat/my-feature main
```

### 3. Make changes
Follow the conventions in `CLAUDE.md`.

### 4. Validate
```bash
make lint && make typecheck && make test
```

### 5. Commit
```bash
git add <specific files>
git commit -m "feat: description of change"
```

### 6. Push and create PR
```bash
git push -u origin feat/my-feature
gh pr create --title "feat: description" --body "Closes #123"
```

## How to Add a New Pipeline Service

1. Create directory under `services/pipeline/<service_name>/`
2. Inherit from appropriate base class in `shared/` (Consumer, Producer, Transformer, etc.)
3. Add Avro schema in `<service_name>/schema/`
4. Add entry in `docker-compose.yml`
5. Add unit tests in `services/pipeline/tests/test_<service_name>.py`
6. Update `ARCHITECTURE.md` with new data flow

## How to Add a New Backend App

1. Create app under `services/platform/backend/apps/<app_name>/`
2. Add to `INSTALLED_APPS` in `sequoia/settings/base.py`
3. Add URL routes in `sequoia/urls.py`
4. Add tests in `services/platform/backend/tests/test_<app_name>.py`
5. Run migrations: `python manage.py makemigrations <app_name>`

## Running Tests

```bash
make test                # All unit tests (fast)
make test-pipeline       # Pipeline only
make test-backend        # Backend only
make test-frontend       # Frontend only
make test-integration    # Integration tests (requires Docker stack)
```

## Code Review Checklist

- [ ] CI passes (lint, typecheck, tests, security)
- [ ] No new secrets in code or config
- [ ] Integration tests not modified
- [ ] Dependencies updated in lock files
- [ ] Architecture docs updated if data flow changed

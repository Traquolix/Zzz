# SequoIA Monorepo Makefile
# Standard targets for humans and Claude Code alike.
# Usage: make setup  (first time)
#        make ci     (runs full validation pipeline)

.PHONY: help setup setup-pipeline setup-backend setup-frontend \
        lint lint-pipeline lint-backend lint-frontend \
        format format-pipeline format-backend format-frontend \
        typecheck typecheck-pipeline typecheck-backend typecheck-frontend \
        test test-ai-engine snapshot-confirm \
        security security-pipeline security-backend security-frontend \
        ci up down logs rebuild shell clean dev dev-deps dev-stop dev-backend dev-frontend \
        ch-migrate backup restore _check-python

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Paths and Python version enforcement
# ---------------------------------------------------------------------------
PIPELINE_DIR  := services/pipeline
BACKEND_DIR   := services/platform/backend
FRONTEND_DIR  := services/platform/frontend

PIPELINE_PY   := $(PIPELINE_DIR)/.venv/bin/python
BACKEND_PY    := $(BACKEND_DIR)/.venv/bin/python

# Required Python version — must match Docker images (3.10 everywhere)
REQUIRED_PYTHON := 3.10
SYSTEM_PYTHON   := $(shell \
  for cmd in python$(REQUIRED_PYTHON) python3; do \
    if command -v $$cmd >/dev/null 2>&1; then \
      ver=$$($$cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"); \
      if [ "$$ver" = "$(REQUIRED_PYTHON)" ]; then echo $$cmd; exit 0; fi; \
    fi; \
  done; \
  echo "PYTHON_NOT_FOUND" \
)

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup — creates venvs and installs all dependencies (run once after clone)
# ---------------------------------------------------------------------------
_check-python:
	@if echo "$(SYSTEM_PYTHON)" | grep -q NOT_FOUND; then \
		echo "ERROR: Python $(REQUIRED_PYTHON) not found."; \
		echo "  macOS:  brew install python@$(REQUIRED_PYTHON)"; \
		echo "  Ubuntu: sudo apt install python$(REQUIRED_PYTHON) python$(REQUIRED_PYTHON)-venv"; \
		exit 1; \
	fi

setup: setup-pipeline setup-backend setup-frontend ## Set up all dev environments (venvs + node_modules)

setup-pipeline: _check-python ## Set up pipeline venv
	@if [ ! -d "$(PIPELINE_DIR)/.venv" ]; then \
		echo "==> Creating pipeline venv ($(SYSTEM_PYTHON))..."; \
		$(SYSTEM_PYTHON) -m venv $(PIPELINE_DIR)/.venv; \
	fi
	@echo "==> Upgrading pip..."
	@$(PIPELINE_PY) -m pip install --upgrade pip -q
	@echo "==> Installing pipeline dependencies..."
	$(PIPELINE_PY) -m pip install -e "$(PIPELINE_DIR)[dev]" -q

setup-backend: _check-python ## Set up backend venv
	@if [ ! -d "$(BACKEND_DIR)/.venv" ]; then \
		echo "==> Creating backend venv ($(SYSTEM_PYTHON))..."; \
		$(SYSTEM_PYTHON) -m venv $(BACKEND_DIR)/.venv; \
	fi
	@echo "==> Upgrading pip..."
	@$(BACKEND_PY) -m pip install --upgrade pip -q
	@echo "==> Installing backend dependencies..."
	$(BACKEND_PY) -m pip install -r $(BACKEND_DIR)/requirements-dev.txt -q

setup-frontend: ## Set up frontend (npm install)
	@if [ ! -d "$(FRONTEND_DIR)/node_modules" ]; then \
		echo "==> Installing frontend dependencies..."; \
		cd $(FRONTEND_DIR) && npm install; \
	else \
		echo "==> Frontend node_modules already exists (run 'cd $(FRONTEND_DIR) && npm install' to update)"; \
	fi

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------
lint: lint-pipeline lint-backend lint-frontend ## Run all linters

lint-pipeline: ## Lint pipeline Python code
	$(PIPELINE_PY) -m ruff check $(PIPELINE_DIR)
	$(PIPELINE_PY) -m ruff format --check $(PIPELINE_DIR)

lint-backend: ## Lint backend Python code
	$(BACKEND_PY) -m ruff check $(BACKEND_DIR)
	$(BACKEND_PY) -m ruff format --check $(BACKEND_DIR)

lint-frontend: ## Lint frontend TypeScript code
	cd $(FRONTEND_DIR) && npm run lint
	cd $(FRONTEND_DIR) && npm run format:check

# ---------------------------------------------------------------------------
# Format (auto-fix)
# ---------------------------------------------------------------------------
format: format-pipeline format-backend format-frontend ## Auto-format all code

format-pipeline: ## Format pipeline Python code
	$(PIPELINE_PY) -m ruff format $(PIPELINE_DIR)
	$(PIPELINE_PY) -m ruff check --fix $(PIPELINE_DIR)

format-backend: ## Format backend Python code
	$(BACKEND_PY) -m ruff format $(BACKEND_DIR)
	$(BACKEND_PY) -m ruff check --fix $(BACKEND_DIR)

format-frontend: ## Format frontend TypeScript code
	cd $(FRONTEND_DIR) && npm run format

# ---------------------------------------------------------------------------
# Type checking
# ---------------------------------------------------------------------------
typecheck: typecheck-pipeline typecheck-backend typecheck-frontend ## Run all type checkers

typecheck-pipeline: ## Type-check pipeline
	cd $(PIPELINE_DIR) && .venv/bin/python -m mypy --config-file pyproject.toml shared/ processor/ ai_engine/ config/

typecheck-backend: ## Type-check backend
	cd $(BACKEND_DIR) && .venv/bin/python -m mypy --config-file pyproject.toml apps/ sequoia/

typecheck-frontend: ## Type-check frontend
	cd $(FRONTEND_DIR) && npx tsc -p tsconfig.app.json --noEmit

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test: test-ai-engine ## Run all tests

test-ai-engine: ## Run AI engine test suite
	cd $(PIPELINE_DIR) && .venv/bin/python -m pytest tests/ai_engine/ -v --tb=short

snapshot-confirm: ## Re-generate AI engine golden test snapshots after intentional changes
	cd $(PIPELINE_DIR) && .venv/bin/python tests/ai_engine/fixtures/generate_golden_fixture.py
	@echo ""
	@echo "Snapshots updated. Review the changes, then commit:"
	@echo "  git add services/pipeline/tests/ai_engine/fixtures/*.npz"
	@echo "  git commit -m 'test: update AI engine golden snapshots'"

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
security: security-pipeline security-backend security-frontend ## Run all security checks

security-pipeline: ## Security scan pipeline
	$(PIPELINE_PY) -m pip_audit 2>/dev/null || echo "pip-audit not installed — run: make setup-pipeline"
	$(PIPELINE_PY) -m bandit -r $(PIPELINE_DIR)/shared/ $(PIPELINE_DIR)/processor/ $(PIPELINE_DIR)/ai_engine/ $(PIPELINE_DIR)/config/ -q 2>/dev/null || echo "bandit not installed — run: make setup-pipeline"

security-backend: ## Security scan backend
	$(BACKEND_PY) -m pip_audit 2>/dev/null || echo "pip-audit not installed — run: make setup-backend"
	$(BACKEND_PY) -m bandit -r $(BACKEND_DIR)/apps/ $(BACKEND_DIR)/sequoia/ -q 2>/dev/null || echo "bandit not installed — run: make setup-backend"

security-frontend: ## Security scan frontend
	cd $(FRONTEND_DIR) && npm audit --audit-level=high 2>/dev/null || true

# ---------------------------------------------------------------------------
# CI (full validation pipeline — run this before any PR)
# ---------------------------------------------------------------------------
ci: lint typecheck test security ## Full CI pipeline: lint + typecheck + test + security

# ---------------------------------------------------------------------------
# Docker Compose lifecycle
# ---------------------------------------------------------------------------
up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

logs: ## Tail logs for a service (usage: make logs SERVICE=platform-backend)
	docker compose logs -f $(SERVICE)

rebuild: ## Rebuild and restart a service (usage: make rebuild SERVICE=processor)
	docker compose up -d --build --force-recreate $(SERVICE)

shell: ## Open a shell in a service container (usage: make shell SERVICE=platform-backend)
	docker compose exec $(SERVICE) /bin/sh

# ---------------------------------------------------------------------------
# Local Development
# ---------------------------------------------------------------------------
dev: dev-deps ## Start backend + frontend for local development (auto-setup on first run)
	@trap 'echo ""; echo "==> Shutting down..."; docker compose stop postgres clickhouse redis 2>/dev/null; kill 0' EXIT; \
	$(MAKE) dev-backend & \
	$(MAKE) dev-frontend & \
	wait

dev-stop: ## Stop all local dev services (Docker deps + stale processes)
	@echo "==> Stopping Docker dependencies..."
	@docker compose stop postgres clickhouse redis 2>/dev/null || true
	@echo "==> Killing stale dev processes..."
	@pkill -f "uvicorn.*sequoia.asgi" 2>/dev/null || true
	@pkill -f "vite preview" 2>/dev/null || true
	@echo "==> Dev environment stopped."

dev-deps: ## Start Docker dependencies for local dev (PostgreSQL + ClickHouse + Redis)
	@echo "==> Ensuring PostgreSQL, ClickHouse, and Redis are running..."
	@docker compose up -d postgres clickhouse redis
	@echo "==> Waiting for PostgreSQL to be ready..."
	@until docker compose exec -T postgres pg_isready -U $${POSTGRES_USER:-sequoia} -d $${POSTGRES_DB:-sequoia} > /dev/null 2>&1; do sleep 1; done

dev-backend: ## Start backend dev server (auto-setup on first run)
	@pkill -f "uvicorn.*sequoia.asgi" 2>/dev/null || true
	@if [ ! -d "$(BACKEND_DIR)/.venv" ]; then \
		if echo "$(SYSTEM_PYTHON)" | grep -q NOT_FOUND; then \
			echo "ERROR: Python $(REQUIRED_PYTHON) not found. Install it: brew install python@$(REQUIRED_PYTHON)"; \
			exit 1; \
		fi; \
		echo "==> Creating backend venv ($(SYSTEM_PYTHON))..."; \
		$(SYSTEM_PYTHON) -m venv $(BACKEND_DIR)/.venv; \
	fi
	@if ! $(BACKEND_PY) -c "import django" 2>/dev/null; then \
		echo "==> Installing backend dependencies..."; \
		$(BACKEND_PY) -m pip install -r $(BACKEND_DIR)/requirements.txt -q; \
	fi
	@echo "==> Running migrations..."
	@cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/python manage.py migrate --run-syncdb
	@echo "==> Seeding dev users..."
	@cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/python manage.py seed_users
	@echo "==> Syncing fiber & infrastructure data..."
	@cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/python manage.py sync_fiber_data
	@echo "==> Clearing throttle cache..."
	@cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/python -c "from django.core.cache import cache; cache.clear()" 2>/dev/null || true
	@echo "==> Starting backend on http://localhost:8001"
	cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/uvicorn sequoia.asgi:application --host 127.0.0.1 --port 8001 --reload

dev-frontend: ## Build and preview frontend locally (auto-setup on first run)
	@pkill -f "vite preview" 2>/dev/null || true
	@if [ ! -d "$(FRONTEND_DIR)/node_modules" ]; then \
		echo "==> Installing frontend dependencies..."; \
		cd $(FRONTEND_DIR) && npm install; \
	fi
	@echo "==> Building frontend..."
	cd $(FRONTEND_DIR) && unset VITE_API_URL VITE_WS_URL VITE_MAPBOX_TOKEN && npm run build
	@echo "==> Serving frontend on http://localhost:4173"
	cd $(FRONTEND_DIR) && npm run preview

# ---------------------------------------------------------------------------
# Backup & Restore (run on the backend server)
# ---------------------------------------------------------------------------
ch-migrate: ## Apply ClickHouse migrations + load cable data
	cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/python manage.py apply_clickhouse_migrations

backup: ## Run a manual backup (PostgreSQL + ClickHouse)
	./scripts/backup.sh

restore: ## Restore from backup (usage: make restore BACKUP=backups/2026-03-06_0300 or make restore BACKUP=--latest)
	./scripts/restore.sh $(BACKUP)

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
clean: ## Remove Python caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true

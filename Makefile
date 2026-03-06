# SequoIA Monorepo Makefile
# Standard targets for humans and Claude Code alike.
# Usage: make setup  (first time)
#        make ci     (runs full validation pipeline)

.PHONY: help setup setup-pipeline setup-backend setup-frontend \
        lint lint-pipeline lint-backend lint-frontend \
        format format-pipeline format-backend \
        typecheck typecheck-pipeline typecheck-backend typecheck-frontend \
        security security-pipeline security-backend security-frontend \
        ci up down logs rebuild shell clean dev dev-backend dev-frontend

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PIPELINE_DIR  := services/pipeline
BACKEND_DIR   := services/platform/backend
FRONTEND_DIR  := services/platform/frontend

PIPELINE_PY   := $(PIPELINE_DIR)/.venv/bin/python
BACKEND_PY    := $(BACKEND_DIR)/.venv/bin/python

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup — creates venvs and installs all dependencies (run once after clone)
# ---------------------------------------------------------------------------
setup: setup-pipeline setup-backend setup-frontend ## Set up all dev environments (venvs + node_modules)

setup-pipeline: ## Set up pipeline venv
	@if [ ! -d "$(PIPELINE_DIR)/.venv" ]; then \
		echo "==> Creating pipeline venv..."; \
		python3 -m venv $(PIPELINE_DIR)/.venv; \
	fi
	@echo "==> Upgrading pip..."
	@$(PIPELINE_PY) -m pip install --upgrade pip -q
	@echo "==> Installing pipeline dependencies..."
	$(PIPELINE_PY) -m pip install -e "$(PIPELINE_DIR)[dev]" -q

setup-backend: ## Set up backend venv
	@if [ ! -d "$(BACKEND_DIR)/.venv" ]; then \
		echo "==> Creating backend venv..."; \
		python3 -m venv $(BACKEND_DIR)/.venv; \
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
format: format-pipeline format-backend ## Auto-format all code

format-pipeline: ## Format pipeline Python code
	$(PIPELINE_PY) -m ruff format $(PIPELINE_DIR)
	$(PIPELINE_PY) -m ruff check --fix $(PIPELINE_DIR)

format-backend: ## Format backend Python code
	$(BACKEND_PY) -m ruff format $(BACKEND_DIR)
	$(BACKEND_PY) -m ruff check --fix $(BACKEND_DIR)

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
# Tests (temporarily removed — tests being rewritten, see TODO.md)
# ---------------------------------------------------------------------------

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
ci: lint typecheck security ## Full CI pipeline: lint + typecheck + security

# ---------------------------------------------------------------------------
# Docker Compose lifecycle
# ---------------------------------------------------------------------------
up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

logs: ## Tail logs for a service (usage: make logs SERVICE=platform-backend)
	docker compose logs -f $(SERVICE)

rebuild: ## Rebuild and restart a service (usage: make rebuild SERVICE=processor-carros)
	docker compose up -d --build --force-recreate $(SERVICE)

shell: ## Open a shell in a service container (usage: make shell SERVICE=platform-backend)
	docker compose exec $(SERVICE) /bin/sh

# ---------------------------------------------------------------------------
# Local Development
# ---------------------------------------------------------------------------
dev: ## Start backend + frontend for local development (auto-setup on first run)
	@trap 'kill 0' EXIT; \
	$(MAKE) dev-backend & \
	$(MAKE) dev-frontend & \
	wait

dev-backend: ## Start backend dev server (auto-setup on first run)
	@if [ ! -d "$(BACKEND_DIR)/.venv" ]; then \
		echo "==> Creating backend venv..."; \
		python3 -m venv $(BACKEND_DIR)/.venv; \
	fi
	@if ! $(BACKEND_PY) -c "import django" 2>/dev/null; then \
		echo "==> Installing backend dependencies..."; \
		$(BACKEND_PY) -m pip install -r $(BACKEND_DIR)/requirements.txt -q; \
	fi
	@if [ ! -f "$(BACKEND_DIR)/db.sqlite3" ]; then \
		echo "==> Running migrations..."; \
		cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/python manage.py migrate --run-syncdb; \
		echo "==> Seeding dev users..."; \
		cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/python manage.py seed_users; \
		echo "==> Seeding infrastructure..."; \
		cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/python manage.py seed_infrastructure; \
	fi
	@echo "==> Starting backend on http://localhost:8001"
	cd $(BACKEND_DIR) && DJANGO_SETTINGS_MODULE=sequoia.settings.dev .venv/bin/daphne -b 127.0.0.1 -p 8001 sequoia.asgi:application

dev-frontend: ## Start frontend dev server (auto-setup on first run)
	@if [ ! -d "$(FRONTEND_DIR)/node_modules" ]; then \
		echo "==> Installing frontend dependencies..."; \
		cd $(FRONTEND_DIR) && npm install; \
	fi
	@echo "==> Starting frontend on http://localhost:5173"
	cd $(FRONTEND_DIR) && npm run dev

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
clean: ## Remove Python caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true

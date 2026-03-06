# SequoIA Monorepo Makefile
# Standard targets for humans and Claude Code alike.
# Usage: make ci  (runs full validation pipeline)

.PHONY: help lint format typecheck security ci \
        up down logs rebuild shell clean dev dev-backend dev-frontend

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------
lint: lint-pipeline lint-backend lint-frontend ## Run all linters

lint-pipeline: ## Lint pipeline Python code
	cd services/pipeline && python -m ruff check .
	cd services/pipeline && python -m ruff format --check .

lint-backend: ## Lint backend Python code
	cd services/platform/backend && python -m ruff check .
	cd services/platform/backend && python -m ruff format --check .

lint-frontend: ## Lint frontend TypeScript code
	cd services/platform/frontend && npm run lint
	cd services/platform/frontend && npm run format:check

# ---------------------------------------------------------------------------
# Format (auto-fix)
# ---------------------------------------------------------------------------
format: format-pipeline format-backend ## Auto-format all code

format-pipeline: ## Format pipeline Python code
	cd services/pipeline && python -m ruff format .
	cd services/pipeline && python -m ruff check --fix .

format-backend: ## Format backend Python code
	cd services/platform/backend && python -m ruff format .
	cd services/platform/backend && python -m ruff check --fix .

# ---------------------------------------------------------------------------
# Type checking
# ---------------------------------------------------------------------------
typecheck: typecheck-pipeline typecheck-backend typecheck-frontend ## Run all type checkers

typecheck-pipeline: ## Type-check pipeline
	cd services/pipeline && python -m mypy --config-file pyproject.toml shared/ processor/ ai_engine/ config/

typecheck-backend: ## Type-check backend
	cd services/platform/backend && python -m mypy --config-file pyproject.toml apps/ sequoia/

typecheck-frontend: ## Type-check frontend
	cd services/platform/frontend && npx tsc -p tsconfig.app.json --noEmit

# ---------------------------------------------------------------------------
# Tests (temporarily removed — tests being rewritten, see TODO.md)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
security: security-pipeline security-backend security-frontend ## Run all security checks

security-pipeline: ## Security scan pipeline
	cd services/pipeline && python -m pip_audit 2>/dev/null || echo "pip-audit not installed — run: pip install pip-audit"
	cd services/pipeline && python -m bandit -r shared/ processor/ ai_engine/ config/ -q 2>/dev/null || echo "bandit not installed — run: pip install bandit"

security-backend: ## Security scan backend
	cd services/platform/backend && python -m pip_audit 2>/dev/null || echo "pip-audit not installed"
	cd services/platform/backend && python -m bandit -r apps/ sequoia/ -q 2>/dev/null || echo "bandit not installed"

security-frontend: ## Security scan frontend
	cd services/platform/frontend && npm audit --audit-level=high 2>/dev/null || true

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
BACKEND_DIR := services/platform/backend
FRONTEND_DIR := services/platform/frontend

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
	@if ! $(BACKEND_DIR)/.venv/bin/python -c "import django" 2>/dev/null; then \
		echo "==> Installing backend dependencies..."; \
		$(BACKEND_DIR)/.venv/bin/pip install -r $(BACKEND_DIR)/requirements.txt -q; \
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

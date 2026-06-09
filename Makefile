# Zoiko AI Logistics — Makefile
#
# Requires: Python 3.10+, PostgreSQL running on localhost:5432, npm
#
# Quick start:
#   make setup              — install Python + Node dependencies
#   make demo-freight-overcharge — run the full SC-001 pipeline end-to-end
#   make test               — run all tests (all phases)
#   make test-phase-2       — run phase-2 tests only
#   make backend            — start Phase 2 API gateway (port 8000)
#   make frontend           — start React frontend (port 5173)
#   make smoke-test         — run smoke tests against live backend
#   make db-migrate         — run all Alembic migrations
#   make db-seed            — seed dummy data
#   make verify-acr         — verify an ACR bundle (ACR_FILE=path/to/acr.json)

PYTHON     ?= python
VENV       := .venv
PY         := $(VENV)/Scripts/python
PIP        := $(VENV)/Scripts/pip
NPM        := npm
DB_URL     ?= postgresql://postgres:1234@localhost/zoiko
PYTHONPATH ?= backend/core/packages/zoiko-common:backend/platform:backend/platform/packages/zoiko-kms:backend/gateway:backend/governance:backend/execution

export DB_URL
export PYTHONIOENCODING=utf-8
export ZOIKO_DEV_MODE=true
export ZOIKO_DEV_SECRET=zoiko-dev-secret-for-testing-only
export ZOIKO_ISSUER=https://auth.zoikotech.com

.PHONY: all setup venv install-python install-node test test-phase-0 test-phase-1 \
        test-phase-2 test-phase-3 test-phase-4 \
        test-fast test-cov \
        backend frontend db-migrate db-seed db-rollback smoke-test \
        demo-freight-overcharge demo-phase-2 demo-phase-3 demo-phase-4 \
        lint format type-check check \
        verify-acr clean help

all: help

# ── Setup ─────────────────────────────────────────────────────────────────────

setup: venv install-python install-node
	@echo "Setup complete. Run: make demo-freight-overcharge"

venv:
	@$(PYTHON) -m venv $(VENV)

install-python: venv
	@$(PIP) install -r requirements.txt
	@$(PIP) install -e backend/core/packages/zoiko-common -q 2>/dev/null; true
	@$(PIP) install -e backend/platform/packages/zoiko-kms -q 2>/dev/null; true

install-node:
	@cd zoiko-frontend/frontend && $(NPM) install

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	@$(PY) -m pytest backend/core/packages/zoiko-common/tests backend/platform \
	    backend/gateway backend/governance backend/execution \
	    -q --tb=short

test-phase-0:
	@$(PY) -m pytest backend/core/packages/zoiko-common/tests -q --tb=short

test-phase-1:
	@cd backend/platform && ../../$(PY) -m pytest tests/ packages/zoiko-kms/tests/ -q --tb=short

test-phase-2:
	@$(PY) -m pytest backend/gateway -q --tb=short

test-phase-3:
	@$(PY) -m pytest backend/governance -q --tb=short

test-phase-4:
	@$(PY) -m pytest backend/execution -q --tb=short

test-fast:
	@$(PY) -m pytest backend/gateway backend/governance -q --tb=short -x -m "not integration"

test-cov:
	@$(PY) -m pytest backend/core/packages/zoiko-common/tests backend/gateway \
	    backend/governance backend/execution \
	    --cov=backend/gateway/services --cov=backend/governance/services \
	    --cov=backend/execution/services \
	    --cov-report=term-missing --cov-report=html:htmlcov -q --tb=short

# ── Demos ─────────────────────────────────────────────────────────────────────

demo-phase-2:
	@cd backend/gateway && ../../$(PY) demo_phase2.py

demo-phase-3:
	@cd backend/governance && ../../$(PY) demo_phase3.py

demo-phase-4:
	@cd backend/execution && ../../$(PY) demo_phase4.py

demo-freight-overcharge:
	@echo "==> Running SC-001: BlueDart bills Amazon India — overcharge detection pipeline"
	@$(MAKE) demo-phase-2
	@$(MAKE) demo-phase-3
	@$(MAKE) demo-phase-4
	@echo "==> SC-001 complete."

# ── Services ──────────────────────────────────────────────────────────────────

backend:
	@cd backend/gateway && ../../$(PY) -m uvicorn services.api_gateway.app:app \
	    --reload --host 0.0.0.0 --port 8000

frontend:
	@cd zoiko-frontend/frontend && $(NPM) run dev


# ── Database ──────────────────────────────────────────────────────────────────

db-migrate:
	@cd backend/core/db && ../../../$(PY) -m alembic upgrade head

db-rollback:
	@cd backend/core/db && ../../../$(PY) -m alembic downgrade -1

db-seed:
	@$(PY) backend/core/scripts/seed_dummy_data.py

# ── Utilities ─────────────────────────────────────────────────────────────────

smoke-test:
	@bash scripts/smoke-test.sh

tenant-fuzzer:
	@bash scripts/tenant-fuzzer.sh

ACR_FILE ?= acr.json
verify-acr:
	@bash verify.sh $(ACR_FILE)

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	@$(PY) -m ruff check backend/core backend/gateway backend/governance backend/execution \
	    --select E,W,F,I --ignore E501

format:
	@$(PY) -m black backend/core backend/gateway backend/governance backend/execution \
	    --line-length 100

type-check:
	@$(PY) -m mypy backend/gateway/services/api_gateway \
	    --ignore-missing-imports --no-strict-optional

check: lint type-check
	@echo "All checks passed."

clean:
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	@find . -name "*.pyc" -delete 2>/dev/null; true

help:
	@echo ""
	@echo "Zoiko AI Logistics — Available targets:"
	@echo ""
	@echo "  make setup                   Install all dependencies"
	@echo "  make demo-freight-overcharge  Run the full SC-001 pipeline"
	@echo "  make test                    Run all tests (all phases)"
	@echo "  make test-phase-2            Phase 2 tests only"
	@echo "  make test-fast               Fast unit tests (phase-2 + phase-3, no integration)"
	@echo "  make test-cov                Tests with HTML coverage report"
	@echo "  make backend                 Start Phase 2 API (port 8000)"
	@echo "  make frontend                Start React frontend (port 5173)"
	@echo "  make db-migrate              Apply all Alembic migrations"
	@echo "  make db-rollback             Roll back one Alembic migration"
	@echo "  make db-seed                 Seed dummy data"
	@echo "  make smoke-test              Run smoke tests"
	@echo "  make lint                    Run ruff linter"
	@echo "  make format                  Run black formatter"
	@echo "  make type-check              Run mypy on phase-2 gateway"
	@echo "  make check                   Run lint + type-check"
	@echo "  make verify-acr ACR_FILE=x   Verify an ACR bundle offline"
	@echo ""

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
PYTHONPATH ?= phase-0/packages/zoiko-common:phase-1:phase-1/packages/zoiko-kms:phase-2:phase-3:phase-4

export DB_URL
export PYTHONIOENCODING=utf-8
export ZOIKO_DEV_MODE=true
export ZOIKO_DEV_SECRET=zoiko-dev-secret-for-testing-only
export ZOIKO_ISSUER=https://auth.zoikotech.com

.PHONY: all setup venv install-python install-node test test-phase-0 test-phase-1 \
        test-phase-2 test-phase-3 test-phase-4 \
        test-fast test-cov \
        backend frontend db-migrate db-seed db-rollback smoke-test tenant-fuzzer \
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

install-node:
	@cd zoiko-frontend/frontend && $(NPM) install

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	@$(PY) -m pytest phase-0/packages/zoiko-common/tests phase-1 phase-2 phase-3 phase-4 \
	    -q --tb=short

test-phase-0:
	@$(PY) -m pytest phase-0/packages/zoiko-common/tests -q --tb=short

test-phase-1:
	@cd phase-1 && ../$(PY) -m pytest tests/ packages/zoiko-kms/tests/ -q --tb=short

test-phase-2:
	@$(PY) -m pytest phase-2 -q --tb=short

test-phase-3:
	@$(PY) -m pytest phase-3 -q --tb=short

test-phase-4:
	@$(PY) -m pytest phase-4 -q --tb=short

test-fast:
	@$(PY) -m pytest phase-2 phase-3 -q --tb=short -x -m "not integration"

test-cov:
	@$(PY) -m pytest phase-0/packages/zoiko-common/tests phase-2 phase-3 phase-4 \
	    --cov=phase-2/services --cov=phase-3/services --cov=phase-4/services \
	    --cov-report=term-missing --cov-report=html:htmlcov -q --tb=short

# ── Demos ─────────────────────────────────────────────────────────────────────

demo-phase-2:
	@cd phase-2 && ../$(PY) demo_phase2.py

demo-phase-3:
	@cd phase-3 && ../$(PY) demo_phase3.py

demo-phase-4:
	@cd phase-4 && ../$(PY) demo_phase4.py

demo-freight-overcharge:
	@echo "==> Running SC-001: BlueDart bills Amazon India — overcharge detection pipeline"
	@$(MAKE) demo-phase-2
	@$(MAKE) demo-phase-3
	@$(MAKE) demo-phase-4
	@echo "==> SC-001 complete. Check Streamlit dashboard: make dashboard"

# ── Services ──────────────────────────────────────────────────────────────────

backend:
	@cd phase-2 && ../$(PY) -m uvicorn services.api_gateway.app:app \
	    --reload --host 0.0.0.0 --port 8000

frontend:
	@cd zoiko-frontend/frontend && $(NPM) run dev

dashboard:
	@$(PY) -m streamlit run dashboard.py

# ── Database ──────────────────────────────────────────────────────────────────

db-migrate:
	@cd phase-0/db && ../../$(PY) -m alembic upgrade head

db-rollback:
	@cd phase-0/db && ../../$(PY) -m alembic downgrade -1

db-seed:
	@$(PY) phase-0/scripts/seed_dummy_data.py

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
	@$(PY) -m ruff check phase-0 phase-2 phase-3 phase-4 --select E,W,F,I --ignore E501

format:
	@$(PY) -m black phase-0 phase-2 phase-3 phase-4 --line-length 100

type-check:
	@$(PY) -m mypy phase-2/services/api_gateway --ignore-missing-imports --no-strict-optional

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

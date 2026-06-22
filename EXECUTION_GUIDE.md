# Zoiko AI Logistics — Execution Guide

All commands run from **Windows PowerShell** unless noted.  
Python = `py` (adjust to `python` or `python3` if needed).  
DB password default: `1234`

---

## Driver File Quick Reference

| Service | Driver File | Command |
|---------|------------|---------|
| **Core CLI demo** | `backend/core/scripts/demo_sc001.py` | `py backend/core/scripts/demo_sc001.py` |
| **Platform tests** | `backend/platform/tests/` | `py -m pytest tests/ packages/zoiko-kms/tests/` |
| **Gateway demo** | `backend/gateway/demo_phase2.py` | `py demo_phase2.py` |
| **Gateway smoke test** | `backend/gateway/tests/smoke_test_gateway.py` | `py tests/smoke_test_gateway.py` |
| **Governance demo** | `backend/governance/demo_phase3.py` | `py demo_phase3.py` |
| **Execution demo** | `backend/execution/scripts/demo_phase4.py` | `py scripts/demo_phase4.py` |

---

## One-Time Setup (do this first, only once)

### 1. Install all dependencies

```powershell
# From zoiko-logistics/ root
cd "zoiko-logistics"

# Install combined requirements
pip install -r requirements.txt

# Install local packages (editable — required for imports to work)
pip install -e backend/core/packages/zoiko-common
pip install -e backend/platform/packages/zoiko-kms
```

### 2. Create the PostgreSQL database

```powershell
psql -U postgres -c "CREATE DATABASE zoiko;"
```

### 3. Run migrations (creates all tables)

```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
py -m alembic upgrade head
```

### 4. Seed demo data (SC-001 scenario)

```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
py backend/core/scripts/seed_dummy_data.py
```

---

## backend/core — Crypto Foundation + Dashboard

**What it is:**  
The backbone of everything. Shared crypto library (`zoiko-common`): JCS RFC 8785
canonicalization, Merkle trees, Ed25519 signing. Creates all database tables via Alembic.

### Run tests

```powershell
cd backend\core
py -m pytest packages/zoiko-common/tests -v --tb=short
cd ..\..
```

### Run CI gates (JCS vectors must pass 100%)

```powershell
cd backend\core
py -m pytest packages/zoiko-common/tests -m jcs_vector -v
py -m pytest packages/zoiko-common/tests -m merkle_vector -v
cd ..\..
```

### Run SC-001 live demo (terminal)

```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"
py backend/core/scripts/demo_sc001.py
```

---

## backend/platform — Security Substrate (KMS · OIDC · Kafka · OPA)

**What it is:**  
KMS key hierarchy (Root CA → DEK → Signing), OIDC JWT middleware, Kafka producer/consumer
abstractions (17 topics), and OPA policy scaffold.

### Run tests

```powershell
cd backend\platform
py -m pytest tests/ packages/zoiko-kms/tests/ -v --tb=short
cd ..\..
```

---

## backend/gateway — Service Pipeline (port 8000)

**What it is:**  
API gateway with 283 routes. Ingestion → Validation → Canonical → Case FSM pipeline.

### Run tests

```powershell
cd backend\gateway
py -m pytest --tb=short -q
cd ..\..
```

### Run gateway live demo (requires PostgreSQL + seeded data)

```powershell
cd backend\gateway
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"
py demo_phase2.py
cd ..\..
```

### Start gateway server

```powershell
cd backend\gateway
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:ZOIKO_DEV_MODE = "true"
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8000
```

---

## backend/governance — Evidence · Reasoning · Governance · Token (port 8002)

**What it is:**  
Evidence bundle with Merkle root, deterministic SC-001 confidence scoring (0.96),
SoD-enforced governance approval, signed Governance Token.

### Run tests

```powershell
cd backend\governance
py -m pytest --tb=short -q
cd ..\..
```

### Run governance live demo (requires gateway demo to have run first)

```powershell
cd backend\governance
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"
py demo_phase3.py
cd ..\..
```

---

## backend/execution — Execution Gateway (port 8001)

**What it is:**  
8-gate execution gateway, reconciliation against connector responses, 8-artifact Merkle ACR.

### Run tests

```powershell
cd backend\execution
py -m pytest --tb=short -q
cd ..\..
```

### Run execution demo (requires governance demo to have run first)

```powershell
cd backend\execution
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"
py scripts\demo_phase4.py
cd ..\..
```

---

## Run All Services Together (full test suite)

```powershell
# From zoiko-logistics/ root
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"

Write-Host "=== core ===" -ForegroundColor Cyan
cd backend\core; py -m pytest packages/zoiko-common/tests -q --tb=short; cd ..\..

Write-Host "=== platform ===" -ForegroundColor Cyan
cd backend\platform; py -m pytest tests/ packages/zoiko-kms/tests/ -q --tb=short; cd ..\..

Write-Host "=== gateway ===" -ForegroundColor Cyan
cd backend\gateway; py -m pytest -q --tb=short; cd ..\..

Write-Host "=== governance ===" -ForegroundColor Cyan
cd backend\governance; py -m pytest -q --tb=short; cd ..\..
```

---

## Run Full SC-001 Demo (end-to-end)

```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"

# Gateway: raw invoice → canonical → case PENDING_APPROVAL
cd backend\gateway; py demo_phase2.py; cd ..\..

# Governance: evidence → reasoning → governance → token ACTIVE
cd backend\governance; py demo_phase3.py; cd ..\..

# Execution: 8-gate → reconcile → ACR CLOSED
cd backend\execution; py scripts\demo_phase4.py; cd ..\..
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_URL` | `postgresql://postgres:1234@localhost/zoiko` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379` | Redis for idempotency + token consumed cache |
| `ZOIKO_DEV_SECRET` | `zoiko-dev-secret-for-testing-only` | JWT signing secret (dev only) |
| `ZOIKO_ISSUER` | `https://auth.zoikotech.com` | JWT issuer claim |
| `ZOIKO_DEV_MODE` | `false` | `true` bypasses JWT in gateway & governance (dev only) |
| `OPA_URL` | _(not set)_ | OPA server URL e.g. `http://localhost:8181`. Unset = MockOPAClient |
| `TOKEN_TTL_MINUTES` | `15` | Governance token lifetime in minutes (15-min execution window) |
| `PYTHONIOENCODING` | _(not set)_ | Set to `utf-8` on Windows for emoji/₹ output |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: zoiko_common` | Run `pip install -e backend/core/packages/zoiko-common` |
| `ModuleNotFoundError: zoiko_kms` | Run `pip install -e backend/platform/packages/zoiko-kms` |
| `psycopg2.OperationalError` | Start PostgreSQL; check `DB_URL` env var |
| `UnicodeEncodeError` on Windows | Set `$env:PYTHONIOENCODING = "utf-8"` |
| Integration tests skipped | PostgreSQL not running — skips are expected, not failures |

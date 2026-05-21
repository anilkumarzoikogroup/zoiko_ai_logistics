# Zoiko AI Logistics — Execution Guide (Phase 0–3)

All commands run from **Windows PowerShell** unless noted.  
Python = `py` (adjust to `python` or `python3` if needed).  
DB password default: `1234`

---

## Driver File Quick Reference

| Phase | Driver File | Command |
|-------|------------|---------|
| **Phase 0** | `dashboard.py` (root) | `streamlit run dashboard.py` |
| **Phase 0 CLI** | `phase-0/scripts/demo_sc001.py` | `py phase-0/scripts/demo_sc001.py` |
| **Phase 1** | `phase-1/tests/` | `py -m pytest tests/ packages/zoiko-kms/tests/` |
| **Phase 2** | `phase-2/demo_phase2.py` | `py demo_phase2.py` |
| **Phase 2 API** | `phase-2/smoke_test_gateway.py` | `py smoke_test_gateway.py` |
| **Phase 3** | `phase-3/demo_phase3.py` | `py demo_phase3.py` |

---

## One-Time Setup (do this first, only once)

### 1. Install all dependencies

```powershell
# From zoiko-logistics/ root
cd "zoiko-logistics"

# Install combined requirements
pip install -r requirements.txt

# Install local packages (editable — required for imports to work)
pip install -e phase-0/packages/zoiko-common
pip install -e phase-1/packages/zoiko-kms
```

### 2. Create the PostgreSQL database

```powershell
psql -U postgres -c "CREATE DATABASE zoiko;"
```

### 3. Run migrations (creates all 26 tables)

```powershell
cd phase-0/db
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
py -m alembic -c alembic.ini upgrade head
cd ../..
```

### 4. Seed demo data (SC-001 scenario)

```powershell
cd phase-0
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
py scripts/seed_dummy_data.py
cd ..
```

---

## Phase 0 — Crypto Foundation + Dashboard

> **DRIVER FILE: `phase-0/dashboard.py`**  
> Run: `streamlit run dashboard.py` → opens at http://localhost:8501

**What it is:**  
The backbone of everything. Builds the shared crypto library (`zoiko-common`): JCS RFC 8785
canonicalization, Merkle trees, Ed25519 signing. Also creates all 26 database tables via
Alembic and provides a Streamlit dashboard to browse the system live.

**Deliverables:**  
- `packages/zoiko-common/` — crypto, auth, Kafka, idempotency
- `db/migrations/` — all 26 tables in one Alembic revision
- `dashboard.py` ← **MAIN DRIVER** — Streamlit UI (9 pages)
- `scripts/demo_sc001.py` ← CLI driver — text-based SC-001 walkthrough
- `scripts/seed_dummy_data.py` — DB setup (run once before dashboard)

### Run tests

```powershell
cd phase-0
py -m pytest packages/zoiko-common/tests -v --tb=short
cd ..
```

### Run CI gates (JCS vectors must pass 100%)

```powershell
cd phase-0
py -m pytest packages/zoiko-common/tests -m jcs_vector -v
py -m pytest packages/zoiko-common/tests -m merkle_vector -v
py -m pytest packages/zoiko-common/tests --cov=zoiko_common --cov-fail-under=80
cd ..
```

### Run tenant isolation fuzzer

```powershell
cd phase-0
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
py scripts/tenant_fuzzer.py
cd ..
```

### Run SC-001 live demo (terminal)

```powershell
cd phase-0
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"
py scripts/demo_sc001.py
cd ..
```

### Launch Streamlit dashboard  ← MAIN DRIVER FILE

```powershell
# Run from zoiko-logistics/ root — dashboard.py is now at root level
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
streamlit run dashboard.py
# Opens at http://localhost:8501
```

---

## Phase 1 — Security Substrate (KMS · OIDC · Kafka · OPA)

**What it is:**  
The security and messaging layer that every Phase 2+ service depends on. Builds the
KMS key hierarchy (Root CA → DEK → Signing), OIDC JWT middleware, Kafka producer/consumer
abstractions (17 topics), and OPA policy scaffold.

**Deliverables:**  
- `packages/zoiko-kms/` — 3-tier key hierarchy, local Ed25519 backend, GCP stub
- `middleware/oidc/` — JWT validation, tenant binding, FastAPI Depends helpers
- `middleware/opa/` — fail-closed OPA client and middleware
- `kafka/` — ZoikoProducer, ZoikoConsumer, MockKafkaBroker
- `opa/policies/` — freight_dispute.rego, tenant_isolation.rego
- 54 tests (all green, no DB needed)

### Run tests

```powershell
cd phase-1
py -m pytest tests/ packages/zoiko-kms/tests/ -v --tb=short
cd ..
```

### Run with coverage

```powershell
cd phase-1
py -m pytest tests/ packages/zoiko-kms/tests/ --cov=middleware --cov=kafka --cov=zoiko_kms -v
cd ..
```

---

## Phase 2 — Service Pipeline (Ingestion → Validation → Canonical → Case)

**What it is:**  
First end-to-end service pipeline. Five FastAPI microservices behind an API gateway.
Implements the 5-step ingestion write pattern (JCS → hash → encrypt → DB tx → Kafka)
and the case state machine (OPENED → EVIDENCE_GATHERING → PENDING_APPROVAL).

**Deliverables:**  
- `services/api_gateway/` — FastAPI gateway, 6 routes, JWT + OPA auth
- `services/ingestion_svc/` — 5-step write pattern with domain-tagged SHA-256
- `services/validation_svc/` — contract rate engine, overcharge detection
- `services/canonical_truth/` — authoritative canonical_invoice row
- `services/case_orchestration/` — case FSM with APPEND-ONLY case_events
- 8 unit tests (always pass) + 30 integration tests (skip if no DB)

### Run tests

```powershell
cd phase-2
py -m pytest --tb=short -q
cd ..
```

### Run tests with coverage

```powershell
cd phase-2
py -m pytest --cov=services --cov-report=term-missing -q
cd ..
```

### Run Phase 2 live demo (requires PostgreSQL + seeded data)

```powershell
cd phase-2
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"
py demo_phase2.py
cd ..
```

### Run gateway smoke test (28 checks, no DB needed for auth tests)

```powershell
cd phase-2
$env:PYTHONIOENCODING = "utf-8"
py smoke_test_gateway.py
cd ..
```

---

## Phase 3 — Evidence · Reasoning · Governance · Token

**What it is:**  
The cryptographically intensive phase. Builds the evidence bundle with Merkle root,
deterministic SC-001 confidence scoring (0.96), SoD-enforced governance approval,
and the signed Governance Token that unlocks Phase 4 execution.

**Deliverables:**  
- `services/evidence_svc/` — domain-tagged hash, Merkle root over bundle items
- `services/reasoning_svc/` — SC-001 confidence = 0.96 (fuel 1.00×0.5 + accessorial 0.92×0.5)
- `services/governance_svc/` — SoD enforcement, PENDING_APPROVAL → APPROVED FSM transition
- `services/token_svc/` — tenant_binding hash, signed governance token, 24h TTL
- `services/api_gateway/` — 7 routes (evidence, reasoning, governance, tokens)
- 34 tests (13 unit always pass, 21 integration skip if no DB)

### Run tests

```powershell
cd phase-3
py -m pytest --tb=short -q
cd ..
```

### Run tests with coverage

```powershell
cd phase-3
py -m pytest --cov=services --cov-report=term-missing -q
cd ..
```

### Run Phase 3 live demo (requires Phase 2 demo to have run first)

```powershell
cd phase-3
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"
py demo_phase3.py
cd ..
```

---

## Run All Phases Together (full test suite)

```powershell
# From zoiko-logistics/ root
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"

Write-Host "=== Phase 0 ===" -ForegroundColor Cyan
cd phase-0; py -m pytest packages/zoiko-common/tests -q --tb=short; cd ..

Write-Host "=== Phase 1 ===" -ForegroundColor Cyan
cd phase-1; py -m pytest tests/ packages/zoiko-kms/tests/ -q --tb=short; cd ..

Write-Host "=== Phase 2 ===" -ForegroundColor Cyan
cd phase-2; py -m pytest -q --tb=short; cd ..

Write-Host "=== Phase 3 ===" -ForegroundColor Cyan
cd phase-3; py -m pytest -q --tb=short; cd ..
```

---

## Run Full SC-001 Demo (Phases 2 + 3 end-to-end)

```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"

# Phase 2: raw invoice → canonical → case PENDING_APPROVAL
cd phase-2; py demo_phase2.py; cd ..

# Phase 3: evidence → reasoning → governance → token ACTIVE
cd phase-3; py demo_phase3.py; cd ..
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_URL` | `postgresql://postgres:1234@localhost/zoiko` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379` | Redis for idempotency + token consumed cache |
| `ZOIKO_DEV_SECRET` | `zoiko-dev-secret-for-testing-only` | JWT signing secret (dev only) |
| `ZOIKO_ISSUER` | `https://auth.zoikotech.com` | JWT issuer claim |
| `ZOIKO_DEV_MODE` | `false` | `true` bypasses JWT in Phase 2 & 3 gateways (dev only) |
| `OPA_URL` | _(not set)_ | OPA server URL e.g. `http://localhost:8181`. Unset = MockOPAClient |
| `TENANT_SLUG` | `default` | Tenant slug for KMS key lookup |
| `TOKEN_TTL_MINUTES` | `15` | Governance token lifetime in minutes (15-min execution window) |
| `PYTHONIOENCODING` | _(not set)_ | Set to `utf-8` on Windows for emoji output |

---

## What Each Phase Leaves Behind for the Next

```
Phase 0  →  26 DB tables + zoiko-common crypto + seed data
              ↓
Phase 1  →  KMS keys + OIDC middleware + Kafka + OPA policies
              ↓
Phase 2  →  source_records + canonical_invoices + cases in PENDING_APPROVAL
              ↓
Phase 3  →  evidence_bundles + findings + governance_decisions + governance_tokens (ACTIVE)
              ↓
Phase 4  →  [next] execution_envelopes + reconciliations + ACR (offline verifiable)
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: zoiko_common` | Run `pip install -e phase-0/packages/zoiko-common` |
| `ModuleNotFoundError: zoiko_kms` | Run `pip install -e phase-1/packages/zoiko-kms` |
| `psycopg2.OperationalError` | Start PostgreSQL; check `DB_URL` env var |
| `UnicodeEncodeError` on Windows | Set `$env:PYTHONIOENCODING = "utf-8"` |
| 30 tests skipped in Phase 2/3 | PostgreSQL not running — skips are expected, not failures |
| `ImportError: cannot import name 'StrEnum'` | Python < 3.11 — already fixed in codebase |
| `ArrowInvalid: Could not convert UUID` | Already fixed in `dashboard.py` via `_fix_uuids()` |

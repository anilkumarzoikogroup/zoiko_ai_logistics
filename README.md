# Zoiko AI Logistics — SC-001 Freight Dispute Resolution

A cryptographically auditable freight dispute resolution system.
When a carrier overcharges a shipper, this system detects it, gets two humans to approve a recovery, executes it, and produces an **Action Certification Record (ACR)** that any external auditor can verify offline — zero access to Zoiko systems required.

---

## The SC-001 Scenario

| Field | Value |
|-------|-------|
| Shipper | Amazon India |
| Route | Hyderabad → Warangal |
| Carrier | BlueDart |
| BlueDart billed | **₹12,500** |
| Contract allows | **₹8,000** |
| Overcharge | **₹4,500** (express handling — not in contract) |
| AI Confidence | **96%** |
| Analyst | Ravi (proposes recovery) |
| Manager | Ramu (approves — different person, SoD enforced) |
| Result | ₹4,500 recovered with tamper-proof audit trail |

---

## Phase Status

| Phase | What It Builds | Tests | Status |
|-------|---------------|-------|--------|
| **Phase 0** | Crypto foundation (JCS, Merkle, Ed25519), 26 DB tables, Streamlit dashboard | 86/86 | ✅ DONE |
| **Phase 1** | KMS key hierarchy, OIDC/JWT middleware, Kafka (17 topics), OPA policies | 54/54 | ✅ DONE |
| **Phase 2** | Ingestion → Validation → Canonical Truth → Case Orchestration (5 microservices) · OPA wired · 15-min token TTL | 38/38 | ✅ DONE |
| **Phase 3** | Evidence → Reasoning → Governance → Token (5 microservices) · OPA wired · DEV_MODE · Redis CONSUMED lock | 46/46 | ✅ DONE |
| **Phase 4** | 8-gate Execution Gateway, Connector Hub, Reconciliation, ACR | — | ⏳ NEXT |
| **Phase 5** | React + TypeScript frontend, 30-test hardening, load test, release | — | ⏳ |

---

## Quick Start

### One-time setup
```powershell
# From zoiko-logistics/ root
pip install -r requirements.txt
pip install -e phase-0/packages/zoiko-common
pip install -e phase-1/packages/zoiko-kms

# Create DB and run migrations
psql -U postgres -c "CREATE DATABASE zoiko;"
cd phase-0/db
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
py -m alembic -c alembic.ini upgrade head
cd ../..

# Seed demo data
cd phase-0
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
py scripts/seed_dummy_data.py
cd ..
```

### Launch the dashboard (all phases)
```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
streamlit run dashboard.py
# Opens at http://localhost:8501
```

### Run individual phase demos
```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"

# Phase 2: invoice → ingestion → validation → canonical → case PENDING_APPROVAL
cd phase-2; py demo_phase2.py; cd ..

# Phase 3: evidence → reasoning → governance → token ACTIVE
cd phase-3; py demo_phase3.py; cd ..
```

### Run full test suite
```powershell
cd phase-0; py -m pytest packages/zoiko-common/tests -q --tb=short; cd ..
cd phase-1; py -m pytest tests/ packages/zoiko-kms/tests/ -q --tb=short; cd ..
cd phase-2; py -m pytest -q --tb=short; cd ..
cd phase-3; py -m pytest -q --tb=short; cd ..
```

---

## How It Works — End to End

```
BlueDart Invoice ₹12,500 arrives
         │
         ▼
  Phase 0 — JCS canonicalize + SHA-256 + Ed25519 sign
         │
         ▼
  Phase 1 — JWT identity check + OPA role/SoD policy
         │
         ▼
  Phase 2 — Ingestion → Validation (FAIL, ₹4,500 overcharge)
         │              → Canonical Truth → Case OPENED
         │
         ▼
  Phase 3 — Evidence bundle (BOL + RATE_SHEET + INVOICE, Merkle root)
         │   → Reasoning (confidence = 0.96, deterministic)
         │   → Governance (Ravi proposes, Ramu approves, SoD enforced)
         │   → Token (EXECUTE_CREDIT_MEMO, 24h TTL, tenant-bound)
         │
         ▼
  Phase 4 — 8-gate Execution Gateway
         │   Gate 1: Token signature valid
         │   Gate 2: Token not expired
         │   Gate 3: Tenant binding matches
         │   Gate 4: Scope = EXECUTE
         │   Gate 5: Sanctions clear
         │   Gate 6: FX lock obtained
         │   Gate 7: Connector certified
         │   Gate 8: Idempotency key new
         │   → BlueDart-CONNECTOR issues ₹4,500 credit
         │
         ▼
  ACR issued — 8-artifact Merkle tree, WORM-locked, offline verifiable
```

---

## Individual vs Pipeline

Phases are designed to be **both** — independently testable AND pipeline-connected.

| Use case | How to run |
|----------|-----------|
| Development / debugging | Run each phase independently |
| CI/CD | `pytest` per phase — no DB needed for unit tests |
| Full SC-001 demo | Run Phase 2 demo → Phase 3 demo in sequence |
| Dashboard | All phases shown in one Streamlit app |
| Production | Separate containers communicating via Kafka events |

Phases share **only the PostgreSQL database** — they do not make live API calls to each other.
Phase 3 reads a `case_id` written by Phase 2. Phase 4 will read a `token_id` written by Phase 3.

---

## Dashboard Pages

| Page | Phase | What it shows |
|------|-------|---------------|
| 🏠 Home | 0 | Live metrics, SC-001 summary |
| 📋 All Cases | 0 | All cases, state badges, AI findings |
| ➕ New Case | 0 | Register tenant + submit invoice |
| 👤 Analyst Review | 0 | Human 1 reviews finding, proposes recovery |
| ✅ Manager Approval | 0 | Human 2 approves (SoD enforced) |
| ⚡ Execute Recovery | 0 | 8-gate execution, ACR issued |
| 🔐 Crypto & Audit | 0 | JCS demo, domain hash, Merkle, tamper detection |
| 🗄️ Database | 0 | All 26 tables with row counts |
| 🔑 KMS Keys | 1 | Key hierarchy, live sign/verify, rotation |
| 🎫 OIDC Identity | 1 | Issue/verify JWT tokens, tamper demo |
| 🛡️ OPA Policies | 1 | Policy evaluation, SoD, tenant isolation, fail-closed |
| 📨 Kafka Events | 1 | SC-001 lifecycle events, publish/consume |
| 📥 Ingestion | 2 | 5-step write pattern, outbox, idempotency |
| ✔ Validation | 2 | Contract rate check, overcharge detection |
| 📄 Canonical Truth | 2 | Authoritative canonical_invoice row |
| 🗂 Case Flow | 2 | State machine transitions, APPEND-ONLY audit trail |
| 🔍 Evidence | 3 | Add evidence items, Merkle root update |
| 🧠 Reasoning | 3 | SC-001 confidence 0.96, rule trace, finding + proposal |
| ✅ Governance | 3 | Create approval task, SoD-enforced decision |
| 🎫 Token | 3 | Mint governance token, view active tokens |

---

## The 26 Database Tables

All tables have **RLS ENABLED + FORCED**. Tables marked `*` are APPEND-ONLY (no UPDATE or DELETE).

```
TENANT         → tenants, tenant_keys
INGESTION      → source_records, lineage_records*
VALIDATION     → validation_results
CANONICAL      → canonical_invoices, canonical_shipments, contract_rates
CASE           → cases, case_events*
EVIDENCE       → evidence_bundles, evidence_items*
REASONING      → findings, decision_proposals
GOVERNANCE     → policy_bundles, governance_decisions, approval_tasks
TOKEN          → governance_tokens
EXECUTION      → idempotency_keys, execution_envelopes, connector_responses
RECONCILIATION → reconciliations, outcomes
AUDIT          → action_certification_records
INFRASTRUCTURE → outbox, audit_worm_index*
```

---

## 9 Non-Negotiable Rules

1. **JCS vectors 100% green** — hard CI block before any service code
2. **Hash BEFORE encrypt** — `canonical_hash` computed before KMS encryption
3. **RLS on all tenant tables** — no exceptions, no retrofitting
4. **APPEND-ONLY tables** — never UPDATE/DELETE `lineage_records`, `case_events`, `evidence_items`, `audit_worm_index`
5. **OPA fail-closed** — OPA unreachable → 503, never permit
6. **SoD enforced** — `proposer_sub` must differ from `actor_sub`
7. **8-gate execution** — all gates pass before money moves, token consumed atomically
8. **WORM bucket** — `is_locked=true` is irreversible, 7-year retention
9. **Idempotency + Tenant headers** — required on every state-changing API call

---

## SC-001 Confidence Formula

```
fuel_charge_confidence    = 1.00  (exact contract match: ₹8,000 == ₹8,000)
accessorial_confidence    = 0.92  (surcharge not in contract: ₹0 allowed vs ₹4,500 billed)
combined_confidence       = 0.50 × 1.00 + 0.50 × 0.92 = 0.96
```

This is **deterministic** — any reasoning service anywhere must produce exactly `0.96`.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Services | FastAPI + Python 3.13 |
| Dashboard | Streamlit |
| Messaging | Apache Kafka (MockKafkaBroker in dev, Strimzi on GKE in prod) |
| Database | PostgreSQL 18 |
| Cache | Redis 7 |
| Signing Keys | GCP Cloud KMS HSM (Ed25519) — SOFTWARE backend in dev |
| Policy | OPA (Rego) |
| Crypto | JCS RFC 8785, SHA-256 domain-tagged, Merkle trees |
| CI | pytest + pytest-cov |

---

## Project Structure

```
zoiko-logistics/
├── dashboard.py                   ← Streamlit dashboard (all phases, 20 pages)
├── requirements.txt               ← All dependencies (single file)
├── EXECUTION_GUIDE.md             ← Step-by-step commands per phase
├── CLAUDE.md                      ← AI assistant context and conventions
├── README.md                      ← This file
├── zoiko_phases_story.html        ← Phase-by-phase story document
│
├── phase-0/                       ← Crypto + DB + seed data
│   ├── packages/zoiko-common/     ← JCS, Merkle, Ed25519, Kafka
│   ├── db/migrations/             ← Alembic: all 26 tables
│   └── scripts/                   ← seed_dummy_data.py, demo_sc001.py, tenant_fuzzer.py
│
├── phase-1/                       ← Security substrate
│   ├── packages/zoiko-kms/        ← 3-tier key hierarchy, local Ed25519
│   ├── middleware/oidc/            ← JWT validation, tenant binding
│   ├── middleware/opa/             ← Fail-closed OPA client
│   ├── kafka/                     ← ZoikoProducer, ZoikoConsumer, MockKafkaBroker
│   └── opa/policies/              ← freight_dispute.rego, tenant_isolation.rego
│
├── phase-2/                       ← Service pipeline
│   └── services/
│       ├── api_gateway/           ← FastAPI, JWT + OPA auth, 6 routes
│       ├── ingestion_svc/         ← 5-step write pattern
│       ├── validation_svc/        ← Contract rate engine, overcharge detection
│       ├── canonical_truth/       ← Authoritative canonical_invoice row
│       └── case_orchestration/    ← Case FSM, APPEND-ONLY case_events
│
├── phase-3/                       ← Evidence · Reasoning · Governance · Token
│   ├── services/
│   │   ├── api_gateway/           ← FastAPI, 7 routes, OPA wired, DEV_MODE
│   │   ├── evidence_svc/          ← Domain-tagged hash, Merkle root bundle
│   │   ├── reasoning_svc/         ← SC-001 confidence 0.96 (deterministic)
│   │   ├── governance_svc/        ← SoD enforcement, case FSM APPROVED
│   │   └── token_svc/             ← tenant_binding, signed token, 15-min TTL
│   └── shared/
│       ├── db.py                  ← DB helpers
│       ├── signer.py              ← Ed25519 sign wrapper
│       ├── redis_idem.py          ← Ingestion idempotency cache
│       └── redis_token.py         ← Token CONSUMED lock (Phase 4 reads this)
│
└── phase-4/                       ← (next) 8-gate execution + reconciliation + ACR
```

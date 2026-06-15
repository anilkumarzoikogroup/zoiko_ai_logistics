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
| **Phase 0** | Crypto foundation (JCS, Merkle, Ed25519), 25 DB tables, Streamlit dashboard | 86/86 | ✅ DONE |
| **Phase 1** | KMS key hierarchy, OIDC/JWT middleware, Kafka (17 topics), OPA policies | 54/54 | ✅ DONE |
| **Phase 2** | Ingestion → Validation → Canonical Truth → Case Orchestration (5 microservices) · OPA wired · 24 API routes | 38/38 | ✅ DONE |
| **Phase 3** | Evidence → Reasoning → Governance → Token (5 microservices) · OPA wired · DEV_MODE · Redis CONSUMED lock | 46/46 | ✅ DONE |
| **Phase 4** | 8-gate Execution Gateway, Reconciliation (+ variances), ACR (8-artifact Merkle, WORM index) | unit | ✅ DONE |
| **Phase 5** | React 18 + TypeScript + Vite frontend · fully wired to live backend · real DB data · analyst/manager workflow · PDF parsing · toast notifications · code-split production build (React.lazy + ErrorBoundary) | — | ✅ DONE |
| **Phase 6** | Recovery pipeline — expected recoveries → instruments → tiered matching → ledger closure → write-offs → recovery proofs (acr_ready) | — | ✅ DONE |
| **C07** | Data governance/compliance — legal holds (blocking), retention, crypto-shred, archive/restore (verified)/purge jobs, observability dashboard (admin-only) | — | ✅ DONE |

---

## Quick Start

### One-time setup (run once)
```powershell
# From zoiko-logistics/ root — installs Python deps + frontend npm packages
.\setup.bat
```

### Daily launch — backend + frontend together
```powershell
.\launch.bat
# Checks PostgreSQL, starts backend on port 8000, starts frontend on port 5173
# Opens browser automatically at http://localhost:5173
```

### Manual start (if launch.bat windows are already open)
```powershell
# Terminal 1 — Backend
cd backend\gateway
..\..\venv\Scripts\activate
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:ZOIKO_DEV_MODE = "true"
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd zoiko-frontend\frontend
$env:VITE_USE_MOCK = "false"
npm run dev
# Opens at http://localhost:5173
```

### Frontend environment (.env.local)
```
VITE_USE_MOCK=false
VITE_API_BASE=/api
VITE_DEV_JWT=<see .env.local>
VITE_DEV_TENANT=11111111-1111-1111-1111-111111111111
```
All API calls go through the Vite proxy (`/api` → `localhost:8000`). No CORS issues.

### Run the full SC-001 demo
```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"

# End-to-end: ingestion → validation → canonical → case → evidence → finding → governance → token
cd backend\core; py scripts\demo_sc001.py; cd ..\..
```

### Run full test suite
```powershell
cd backend\core; py -m pytest packages/zoiko-common/tests -q --tb=short; cd ..\..
cd backend\platform; py -m pytest tests/ packages/zoiko-kms/tests/ -q --tb=short; cd ..\..
cd backend\gateway; py -m pytest -q --tb=short; cd ..\..
cd backend\governance; py -m pytest -q --tb=short; cd ..\..
cd backend\execution; py -m pytest -q --tb=short; cd ..\..
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
  Reconciliation — match execution envelope against connector settlement
         │   → reconciliations + outcomes; variances → resolve/waive
         │
         ▼
  ACR issued — 8-artifact Merkle tree, WORM-locked, offline verifiable
         │
         ▼
  Phase 6 — Recovery pipeline
         │   expected_recoveries → recovery_instruments (credit memos, refunds)
         │   → tiered recovery_match → ledger_svc (LEDGER_CLOSED) / write_off_svc
         │   → recovery_proofs rollup (acr_ready)
```

---

## Individual vs Pipeline

Phases are designed to be **both** — independently testable AND pipeline-connected.

| Use case | How to run |
|----------|-----------|
| Development / debugging | Run each phase independently |
| CI/CD | `pytest` per phase — no DB needed for unit tests |
| Full SC-001 demo | Run Phase 2 demo → Phase 3 demo in sequence |
| React UI | `launch.bat` — live backend, real DB data |
| Production | Separate containers communicating via Kafka events |

Phases share **only the PostgreSQL database** — they do not make live API calls to each other.
Phase 3 reads a `case_id` written by Phase 2. Phase 4 will read a `token_id` written by Phase 3.

---

## Backend API Routes (Gateway — port 8000)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/health` | Health check |
| POST | `/cases/submit` | Full pipeline: ingest → validate → canonical → open case → evidence → AI finding |
| GET | `/cases` | List all cases for tenant |
| GET | `/cases/{id}` | Get single case |
| GET | `/cases/{id}/events` | Case audit trail (append-only) |
| POST | `/cases/{id}/propose` | Analyst proposes recovery action |
| POST | `/cases/{id}/decide` | Manager approves/rejects (SoD enforced) |
| GET | `/cases/{id}/validation` | Validation result for case |
| GET | `/cases/{id}/canonical-invoice` | Canonical invoice data |
| GET | `/cases/{id}/finding` | AI reasoning finding |
| GET | `/cases/{id}/proposal` | Recovery proposal |
| GET | `/cases/{id}/acr` | Action Certification Record |
| GET | `/tokens` | List governance tokens |
| GET | `/tokens/{id}` | Get single token |
| POST | `/contract-rates` | Create contract rate |
| GET | `/contract-rates` | List contract rates |
| DELETE | `/contract-rates/{id}` | Delete contract rate |
| POST | `/ingestion/parse-invoice` | Parse PDF/image invoice |
| GET | `/ingestion/source-records` | List source records |
| GET | `/kafka/events` | Recent Kafka events |
| GET | `/stats` | Aggregated pipeline stats |
| GET | `/admin/db-stats` | Live row counts for all 25 DB tables |

All routes require: `Authorization: Bearer <JWT>`, `X-Tenant-ID: <uuid>`, `Idempotency-Key: <unique>` (on mutations).

## Execution Gateway Routes (port 8001)

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/v1/execute` | 8-gate execution check, redeems governance token |
| POST | `/v1/reconcile` | Reconcile execution envelope against connector settlement |
| GET | `/v1/cases/{id}/variances` | Reconciliation variance records |
| PATCH | `/v1/cases/{id}/variances/{vid}` | Resolve/waive a variance |
| POST / GET | `/v1/cases/{id}/acr` | Issue / fetch Action Certification Record |
| POST / GET | `/v1/recovery/expected*` | Expected recoveries — create, list by case, supersede |
| POST / GET | `/v1/recovery/instruments*` | Recovery instruments — create, list by case/counterparty |
| POST | `/v1/recovery/match` | Tiered match of expected recovery against instruments |
| POST / GET | `/v1/recovery/matches*` | List matches, reverse a match |
| POST / GET | `/v1/ledger/entries*` | Ledger entries — post, list, reverse |
| POST | `/v1/recovery/write-offs` | Write-off workflow (PENDING → AUTHORIZED → POSTED) |
| GET | `/v1/recovery/exceptions` | Stuck/aged expected recoveries |
| POST / GET | `/v1/recovery/proofs*` | Recovery proof rollup (`acr_ready` flag) |

## C07 Data Governance Routes (gateway, port 8000, admin-only)

| Method | Route | Description |
|--------|-------|-------------|
| POST / GET | `/v1/legal-holds*` | Place/release/list legal holds — block purge & crypto-shred |
| POST / GET | `/v1/data/retention*` | Retention policies + per-record assignment |
| POST / GET | `/v1/data/archive*` | Archive jobs, integrity verify, restore-from-archive |
| POST / GET | `/v1/data/restore/jobs*` | Restore jobs + 10-check verification + approve-use |
| POST / GET | `/v1/data/purge/jobs*` | Purge jobs — legal-hold aware, approval + evidence |
| POST / GET | `/v1/privacy/crypto-shred*` | Crypto-shred jobs — legal-hold aware, verify |
| GET | `/v1/data/observability/metrics` , `/alerts` | C07 observability dashboard data |

---

## Frontend Pages

| Page | URL | Live Data |
|------|-----|-----------|
| Home / Dashboard | `/` | Cases, tokens, Kafka events, carrier breakdown |
| All Cases | `/cases` | Full case list from DB (paginated) |
| New Case | `/cases/new` | Submits to `/cases/submit` → real pipeline |
| Case Detail | `/cases/:id` | Single case, events, finding, proposal |
| Analyst Review | `/analyst` | Propose recovery action (role: analyst/admin) |
| Manager Approval | `/manager` | Approve/reject (SoD enforced, role: manager/admin) |
| Execute Recovery | `/execute` | 8-gate execution + governance tokens (role: manager/admin) |
| Recovery Pipeline | `/recovery` | Phase 6 — expected recoveries, instruments, matches, proofs |
| Reconciliation | `/reconciliation` | Envelope reconciliation + case variances (role: manager/admin) |
| Rate Control | `/rate-control` | Contract rates (live CRUD) |
| Carriers / Connectors | `/carriers`, `/connectors` | Carrier & connector management |
| Audit & ACR / ACR Verifier | `/crypto`, `/verifier` | Cryptographic audit trail + offline ACR verification |
| Performance / Analytics | `/performance`, `/analytics` | Carrier spend, overcharge trends |
| Audit Conditions | `/audit-conditions` | Carrier overcharge breakdown |
| Alerts | `/alerts` | Real-time Kafka event stream |
| Database | `/database` | Live row counts (role: admin) |
| Data Governance (C07) | `/governance/data`, `/holds`, `/retention`, `/crypto-shred`, `/restore`, `/archive`, `/purge` | Legal holds, retention, crypto-shred, archive/restore/purge jobs (role: admin) |
| Settings / Users / Tenants | `/settings`, `/users`, `/tenants` | Account, user & tenant management |

---

## The Database — 31 Alembic Migrations

All tenant-scoped tables have **RLS ENABLED + FORCED**. Tables marked `*` are APPEND-ONLY (no UPDATE or DELETE).

```
TENANT         → tenants, tenant_keys
INGESTION      → source_records, lineage_records*
VALIDATION     → validation_results
CANONICAL      → canonical_invoices, canonical_shipments, contract_rates
CASE           → cases, case_events*, case_candidates, external_responses
EVIDENCE       → evidence_bundles, evidence_items*
REASONING      → findings, decision_proposals
GOVERNANCE     → policy_bundles, governance_decisions, approval_tasks
TOKEN          → governance_tokens
EXECUTION      → idempotency_keys, execution_envelopes, connector_responses
RECONCILIATION → reconciliations, outcomes, variances
RECOVERY (Phase 6) → expected_recoveries, recovery_instruments, recovery_matches,
                      ledger_entries, write_offs, recovery_proofs
AUDIT          → action_certification_records, audit_worm_index*
COMPLIANCE (C07) → legal_holds, retention_policies, archive_jobs, restore_jobs,
                    purge_jobs, crypto_shred_jobs
INFRASTRUCTURE → outbox
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
| **Frontend** | React 18 + TypeScript + Vite + TailwindCSS + shadcn/ui |
| **State / Data** | TanStack Query v5 · Zustand · Axios |
| **Charts** | Recharts · lucide-react icons |
| **API Services** | FastAPI + Python 3.10+ |
| **Dashboard** | Streamlit |
| **Messaging** | Apache Kafka (MockKafkaBroker in dev, Strimzi on GKE in prod) |
| **Database** | PostgreSQL |
| **Cache** | Redis 7 |
| **Signing Keys** | GCP Cloud KMS HSM (Ed25519) — SOFTWARE backend in dev |
| **Policy** | OPA (Rego) |
| **Crypto** | JCS RFC 8785, SHA-256 domain-tagged, Merkle trees |
| **CI** | pytest + pytest-cov · TypeScript tsc |

---

## Project Structure

```
zoiko-logistics/
├── requirements.txt               ← All Python dependencies (single file)
├── launch.bat                     ← One-click start: PostgreSQL check → backend → frontend
├── setup.bat                      ← One-time setup (venv + pip + npm install)
├── EXECUTION_GUIDE.md             ← Step-by-step commands per service
├── CLAUDE.md                      ← AI assistant context and conventions
├── alembic.ini                    ← Points to backend/core/db/migrations
│
├── backend/
│   ├── core/                      ← Crypto + DB schema
│   │   ├── packages/zoiko-common/ ← JCS, Merkle, Ed25519, Kafka, rate-limit middleware
│   │   ├── db/migrations/         ← Alembic: 31 migration versions (0001–0031)
│   │   └── scripts/                ← demo_sc001.py, tenant_fuzzer.py
│   │
│   ├── platform/                  ← Security substrate
│   │   ├── packages/zoiko-kms/    ← 3-tier key hierarchy, local Ed25519
│   │   ├── middleware/oidc/        ← JWT validation, tenant binding
│   │   ├── middleware/opa/         ← Fail-closed OPA client
│   │   ├── kafka/                 ← ZoikoProducer, ZoikoConsumer, MockKafkaBroker
│   │   └── opa/policies/          ← freight_dispute.rego, tenant_isolation.rego
│   │
│   ├── gateway/                   ← Service pipeline + C07 compliance (port 8000)
│   │   └── services/
│   │       ├── api_gateway/       ← FastAPI, /v1/ prefix, JWT + OPA auth, routers/
│   │       ├── ingestion_svc/     ← 5-step write pattern, EDI/CSV file adapter
│   │       ├── validation_svc/    ← Contract rate engine, overcharge detection
│   │       ├── canonical_truth/   ← Authoritative canonical_invoice row
│   │       ├── case_orchestration/ ← Case FSM, APPEND-ONLY case_events
│   │       ├── legal_hold_svc/    ← Blocking holds (purge & crypto-shred check this)
│   │       ├── retention_svc/     ← Retention policies + assignment
│   │       ├── archive_svc/       ← Archive jobs + integrity verify
│   │       ├── restore_svc/       ← Restore + 10-check verification workflow
│   │       ├── purge_svc/         ← Purge jobs (legal-hold aware)
│   │       ├── crypto_shred_svc/  ← Tenant key destruction (legal-hold aware)
│   │       └── observability_svc/ ← C07 observability dashboard data
│   │
│   ├── governance/                ← Evidence · Reasoning · Governance · Token (port 8002)
│   │   └── services/
│   │       ├── evidence_svc/      ← Domain-tagged hash, growing Merkle bundle
│   │       ├── reasoning_svc/     ← SC-001 confidence 0.96 (deterministic)
│   │       ├── governance_svc/    ← SoD enforcement, case FSM APPROVED
│   │       └── token_svc/         ← tenant_binding, signed token, 15-min TTL
│   │
│   ├── execution/                 ← 8-gate execution + reconciliation + recovery + ACR (port 8001)
│   │   └── services/
│   │       ├── execution_gateway/ ← 8-gate check
│   │       ├── reconciliation_svc/← Settlement match + variances
│   │       ├── audit_acr_svc/     ← 8-artifact Merkle ACR + WORM index
│   │       └── recovery/          ← Phase 6: expected_recovery, instrument, match,
│   │                                  ledger, write_off, recovery_proof, exceptions svcs
│   │
│   └── api/                       ← Frontend-facing reverse proxy (optional, port 8080)
│
└── zoiko-frontend/frontend/       ← React + TypeScript frontend
    ├── src/features/              ← dashboard, cases, governance, recovery, reconciliation,
    │                                  compliance (C07), analytics, audit — code-split (React.lazy)
    ├── src/api/zoiko.ts           ← API service layer (mock/live switch)
    ├── src/api/client.ts          ← Axios instances (gateway + execution gateway), idempotency key
    ├── vite.config.ts             ← Dev proxy: /api → :8000, /api4 → :8001
    └── .env.local                 ← VITE_USE_MOCK=false · VITE_API_BASE=/api
```

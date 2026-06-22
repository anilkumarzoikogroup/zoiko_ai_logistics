# Zoiko AI Logistics — Technical Project Document

**Version:** 1.0  
**Date:** June 2026  
**System:** Freight Overcharge Detection & Cryptographic Recovery Pipeline

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture — How Phases Connect](#2-architecture--how-phases-connect)
3. [Phase 0 — Cryptographic Foundation & Database](#3-phase-0--cryptographic-foundation--database)
4. [Phase 1 — Key Management, Identity & Messaging](#4-phase-1--key-management-identity--messaging)
5. [Phase 2 — Ingestion, Validation & Case Orchestration](#5-phase-2--ingestion-validation--case-orchestration)
6. [Phase 3 — Evidence, Reasoning & Governance](#6-phase-3--evidence-reasoning--governance)
7. [Phase 4 — Execution Gateway, Reconciliation & Audit ACR](#7-phase-4--execution-gateway-reconciliation--audit-acr)
8. [Phase 5 — React Frontend](#8-phase-5--react-frontend)
9. [Security Model](#9-security-model)
10. [Non-Negotiable Rules](#10-non-negotiable-rules)
11. [SC-001 Reference Scenario](#11-sc-001-reference-scenario)

---

## 1. System Overview

Zoiko AI Logistics detects freight overcharges automatically and recovers money through a **cryptographically auditable pipeline**. Every step — from invoice ingestion to final settlement — produces an immutable, offline-verifiable audit record.

**Reference scenario (SC-001):**
> BlueDart bills Amazon India ₹12,500. The contract allows ₹8,000. Zoiko detects the ₹4,500 overcharge, routes it through two human approvals (Analyst → Manager), and executes the recovery. The entire chain is locked into a cryptographic Action Certification Record (ACR) that can be verified without network access.

### Build Status

| Phase | Tests | Description |
|-------|-------|-------------|
| Phase 0 | 86/86 ✅ | Crypto primitives + 25-table DB schema + Streamlit dashboard |
| Phase 1 | 54/54 ✅ | KMS key hierarchy + OIDC/JWT + Kafka (17 topics) + OPA policies |
| Phase 2 | 38/38 ✅ | Ingestion → Validation → Canonical Truth → Case Orchestration |
| Phase 3 | 46/46 ✅ | Evidence → Reasoning → Governance → Token issuance |
| Phase 4 | Unit ✅ | 8-gate Execution Gateway → Reconciliation → WORM ACR |
| Phase 5 | — | React 18 + TypeScript + Vite frontend fully wired to live backend |

---

## 2. Architecture — How Phases Connect

Phases share a **single PostgreSQL database**. They do not make live API calls to each other in production — they communicate via Kafka events. In development, a `MockKafkaBroker` runs in-process.

```
Invoice PDF / JSON
        │
        ▼
  Phase 2 — API Gateway (port 8000)
    Ingest → Validate → Canonical → Case (PENDING_APPROVAL)
        │ writes → cases table
        ▼
  Phase 3 — Evidence & Reasoning (port 8002)
    Evidence Bundle → AI Finding → SoD Approval → Token (ACTIVE)
        │ writes → evidence_bundles, findings, governance_tokens
        ▼
  Phase 4 — Execution Gateway (port 8001)
    8-gate check → Reconciliation → ACR (CLOSED)
        │ writes → execution_envelopes, reconciliations, action_certification_records
        ▼
  Offline ACR Verification (zero network, Ed25519 + Merkle)

  Phase 5 — React Frontend (port 5173)
    → Vite proxy → Phase 2 API Gateway (port 8000)
```

### Case FSM States

```
NEW → EVIDENCE_PENDING → FINDING_GENERATED → APPROVAL_PENDING
    → EXECUTION_READY → DISPATCHED → OUTCOME_RECORDED → CLOSED
    → ABORTED  (from any state)
```

---

## 3. Phase 0 — Cryptographic Foundation & Database

### Purpose
Provides the shared cryptographic primitives and database schema used by all subsequent phases.

### Key Components

#### 3.1 JCS Canonicalization (`crypto/jcs.py`)
Implements **RFC 8785 JSON Canonicalization Scheme**. Produces deterministic UTF-8 bytes from any JSON-compatible Python dict.

- Keys sorted by Unicode code point
- Numbers serialized per ECMAScript spec
- Output is byte-for-byte identical across all languages and platforms
- Used before every hash operation — guarantees the same input always produces the same hash

```python
from zoiko_common.crypto.jcs import canonicalize
canonical_bytes = canonicalize({"amount": 12500, "carrier": "BlueDart"})
```

#### 3.2 Ed25519 Signing (`crypto/signing.py`)
Implements **COSE_Sign1 (RFC 9052)** signed envelopes using Ed25519.

- `LocalEd25519Backend` — for development and testing
- GCP KMS backend — for production
- `SignedEnvelope` — payload + Ed25519 signature + key ID (kid)
- `verify_envelope()` — fully offline verification (no network calls required)
- Used by: Evidence items, Governance tokens, ACR signing

#### 3.3 Merkle Tree (`crypto/merkle.py`)
Domain-tagged Merkle trees used for bundling multiple artifacts into a single root hash.

| Domain Tag | Used For |
|------------|----------|
| `zoiko/v1/source-record` | Ingestion records |
| `zoiko/v1/evidence-item` | Evidence bundle items |
| `zoiko/v1/acr` | 8-artifact ACR package |

#### 3.4 Domain-Tagged SHA-256 Hashes

Every hash uses a unique binary prefix to prevent cross-type hash collision:

| Tag | Applied To |
|-----|-----------|
| `zoiko.ingestion.invoice.v1:` | Source records |
| `zoiko.canonical.invoice.v1:` | Canonical invoice rows |
| `zoiko.evidence.item.v1:` | Evidence items |
| `zoiko.finding.v1:` | AI/rule finding |
| `zoiko.proposal.v1:` | Recovery proposals |
| `zoiko.governance.decision.v1:` | Approval decisions |
| `zoiko.token.v1:` | Governance tokens |

#### 3.5 Database Schema (25 Tables)
Managed by Alembic migrations in `phase-0/db/migrations/`.

**Core tables:**
- `tenants` — multi-tenant isolation
- `users` — role-based access (analyst / manager / admin)
- `source_records` — raw ingested invoices (encrypted)
- `canonical_invoices` — authoritative truth rows
- `cases` — overcharge cases with FSM state
- `case_events` — append-only FSM audit trail
- `contract_rates` — carrier contract rate table
- `evidence_bundles` + `evidence_items` — Merkle-backed evidence (append-only)
- `findings` — AI reasoning output
- `governance_tasks` + `governance_tokens` — SoD approval workflow
- `execution_envelopes` — execution records
- `reconciliations` — settlement match records
- `action_certification_records` — WORM-locked ACR
- `audit_worm_index` — immutable write-once index
- `lineage_records` — hash chain lineage (append-only)
- `outbox` — transactional Kafka outbox

**Append-only tables (never UPDATE/DELETE):**
`lineage_records`, `case_events`, `evidence_items`, `audit_worm_index`

#### 3.6 Observability & Error Types
- `zoiko_common.observability.logging` — structured JSON logging with tenant/trace context
- `ZoikoError` hierarchy: `GateFailureError`, `SoDViolationError`, `TokenConsumedError`, etc.
- `zoiko_common.middleware.rate_limit` — rate limiting middleware

---

## 4. Phase 1 — Key Management, Identity & Messaging

### Purpose
Provides the security infrastructure: cryptographic key hierarchy, JWT identity, policy enforcement (OPA), and Kafka messaging backbone.

### Key Components

#### 4.1 KMS Key Hierarchy (`packages/zoiko-kms/`)
Three-tier key hierarchy:

```
Root Key (KEK)
    └── Tenant Key (DEK-wrapping key, per tenant)
            └── Data Encryption Key (DEK, per record)
```

- `LocalEd25519Backend` for development; GCP KMS for production
- `hierarchy.py` — manages key derivation and rotation
- `local_backend.py` — in-memory key store for tests

#### 4.2 OIDC / JWT Middleware (`middleware/oidc/`)
- `TokenVerifier` — verifies HS256 (dev) or RS256 (prod) JWTs
- `ZoikoClaims` — parsed claims: `sub`, `tenant_id`, `roles`, `exp`
- `ZOIKO_DEV_MODE=true` bypasses signature verification; reads tenant from `X-Tenant-ID` header
- `make_dev_token()` — issues signed dev tokens for local testing
- Token TTL: **24 hours** (configurable via `JWT_TTL_SECONDS`)

#### 4.3 OPA Authorization (`middleware/opa/`)
RBAC + tenant isolation policy at `opa/policies/zoiko/freight/allow.rego`.

- `OPAClient` — real HTTP client, **fail-closed**: returns 503 if OPA is unreachable
- `MockOPAClient` — always allows; used when `OPA_URL` is not set
- Policy checks: role membership, tenant binding, action authorization
- Called on every authenticated request after JWT verification

| `OPA_URL` set | `ZOIKO_DEV_MODE` | Client used | Effect |
|---------------|-----------------|-------------|--------|
| No | Any | MockOPAClient | allow=True |
| Yes | No | OPAClient | Real fail-closed OPA |

#### 4.4 Kafka Messaging (`kafka/`)
**17 canonical topics** (registered in `producer.py`):

```
invoice.received      invoice.validated     invoice.canonical
case.opened           case.updated          case.closed
evidence.bundled      finding.created       proposal.created
decision.made         token.issued          token.consumed
execution.started     execution.completed
reconciliation.done   acr.issued            audit.locked
```

Plus 6 retry topics + 6 dead-letter topics = **31 total registered topics**.

**KafkaEventEnvelope fields:**
- `event_id` — UUID4, globally unique
- `tenant_id` — for RLS enforcement at consumer
- `aggregate_id` / `aggregate_type` — domain entity reference
- `payload_hash` — SHA-256 of JCS-canonicalized payload (tamper detection)
- `signature` — optional Ed25519 (for high-value events)
- `traceparent` / `correlation_id` — distributed tracing

**Outbox pattern:** Messages are written to the `outbox` DB table in the same transaction as the business data. The `OutboxRelay` polls the outbox every 500ms and publishes to Kafka. This guarantees exactly-once delivery even if the process crashes.

**MockKafkaBroker:** In-process broker for dev/test — no Kafka installation required.

---

## 5. Phase 2 — Ingestion, Validation & Case Orchestration

### Purpose
The public-facing API layer. Accepts invoices, validates them against contracts, stores the canonical truth, and opens overcharge cases.

**API Gateway:** FastAPI on port 8000, 24 routes, `/v1/` prefix.

### Key Components

#### 5.1 Ingestion Service (`services/ingestion_svc/`)
**5-step write pattern:**

1. **JCS canonicalize** — deterministic bytes from invoice dict
2. **Domain-tagged SHA-256** — `zoiko.ingestion.invoice.v1:` + canonical bytes
3. **AES-256-GCM encrypt** — via KMS DEK (key per record)
4. **Atomic DB write** — `source_records` + `lineage_records` + `outbox` in one transaction
5. **Redis idempotency** — key stored *after* commit (crash-safe; DB is authoritative)

Fast-path deduplication: Redis check before DB query.

#### 5.2 Validation Service (`services/validation_svc/`)
Detects overcharges by comparing invoice amount against contract rates.

**Lane lookup (2-tier):**
1. SHA-256(`zoiko/v1/lane:` + origin + `|` + destination) — exact route match
2. Carrier ID fallback — carrier-wide rate

Produces `ValidationResult` rows with overcharge amount and rule trace.

#### 5.3 Canonical Truth Service (`services/canonical_truth/`)
Writes the authoritative invoice row after validation. The canonical invoice is the single source of truth for all downstream phases.

- Domain-tagged hash: `zoiko.canonical.invoice.v1:`
- Row is immutable once written

#### 5.4 Case Orchestration (`services/case_orchestration/`)
Opens a `Case` in the database when an overcharge is confirmed. Manages the FSM transitions.

- `ConflictError` raised on duplicate case open (idempotent)
- Publishes `case.opened` to Kafka

#### 5.5 Auth Endpoints (public, no JWT required)
| Endpoint | Description |
|----------|-------------|
| `POST /v1/auth/login` | Email + password → JWT (set as HttpOnly cookie) |
| `POST /v1/auth/org-signup` | Create tenant + admin user → JWT cookie |
| `POST /v1/auth/google/callback` | Exchange Google OAuth code → JWT cookie |
| `POST /v1/auth/google/complete-signup` | New Google user + org name → JWT cookie |
| `GET /v1/auth/me` | Session restore from cookie (no X-Tenant-ID needed) |
| `POST /v1/auth/signout` | Delete auth cookie server-side |

**Cookie security:** JWT stored as `HttpOnly, SameSite=Strict` cookie. `Secure=True` in production (`ZOIKO_ENV=production`). Token never appears in response body or JavaScript-accessible storage.

#### 5.6 Core API Routes (require JWT + X-Tenant-ID)
| Route | Description |
|-------|-------------|
| `POST /v1/cases/submit` | Full pipeline: ingest → validate → canonical → case → evidence → finding |
| `GET /v1/cases` | All cases for tenant |
| `GET /v1/cases/{id}` | Single case detail |
| `POST /v1/cases/{id}/propose` | Analyst proposes recovery |
| `POST /v1/cases/{id}/decide` | Manager approves/rejects (SoD enforced) |
| `GET /v1/cases/{id}/acr` | Fetch completed ACR |
| `POST /v1/contract-rates` | Create contract rate |
| `GET /v1/stats` | Dashboard stats |
| `GET /v1/health` | Health check |

**Required headers on every authenticated request:**
```
Authorization: Bearer <JWT>   (or HttpOnly cookie)
X-Tenant-ID: <tenant-uuid>
Idempotency-Key: <uuid>       (mutations only)
```

---

## 6. Phase 3 — Evidence, Reasoning & Governance

### Purpose
Bundles evidence, runs AI-assisted reasoning to compute confidence, routes through SoD governance workflow, and issues a cryptographic governance token authorizing execution.

**API Gateway:** FastAPI on port 8002, 7 routes.

### Key Components

#### 6.1 Evidence Service (`services/evidence_svc/`)
Builds an **append-only, Merkle-backed evidence bundle** for each case.

Per item added:
1. Domain-tagged SHA-256 of content bytes
2. Ed25519 sign the item hash
3. Upsert `evidence_bundles` row for `(tenant_id, case_id)`
4. INSERT `evidence_items` (audit trail, never updated)
5. Recompute Merkle root across all items, UPDATE bundle root
6. Publish `evidence.bundled` to Kafka

Merkle domain tag: `zoiko/v1/evidence-item`

#### 6.2 Reasoning Service (`services/reasoning_svc/`)
**7-step agent runtime** — fully deterministic, replayable for audit:

| Step | Action |
|------|--------|
| 1 | Read evidence bundle (verify exists) |
| 2 | Read contract rates |
| 3 | Read case metadata |
| 4 | Rule: `fuel_charge` (confidence 1.00, weight 0.50) |
| 5 | Rule: `accessorial` (confidence 0.92, weight 0.50) |
| 6 | Compute SC-001 confidence score = **0.96** (deterministic, never changes) |
| 7 | Optional: GROQ AI risk_level + explanation (supplementary only) |

All 7 steps recorded in `reasoning_trace` for audit replay.

**SC-001 Confidence Formula (immutable):**
```python
SC001_CONFIDENCE = 0.50 × 1.00 + 0.50 × 0.92 = 0.96
```

#### 6.3 Governance Service (`services/governance_svc/`)
Routes the finding through a **two-person Separation of Duties (SoD)** approval workflow.

**SoD Rule (hard-enforced before any DB write):**
```python
if actor_sub == task["proposer_sub"]:
    raise SoDViolationError("proposer cannot be the same as approver")
```

Workflow:
1. Analyst calls `create_task` → case moves to `APPROVAL_PENDING`
2. Manager calls `decide` (approve/reject) — must be a different user
3. On approval → publishes `decision.made` to Kafka

#### 6.4 Token Service (`services/token_svc/`)
Issues a **cryptographically-bound governance token** authorizing Phase 4 execution.

Token properties:
- Bound to: `tenant_id`, `case_id`, `decision_id`, `proposer_sub`
- TTL: **15 minutes** (configurable via `TOKEN_TTL_MINUTES`)
- Signed with Ed25519
- Status transitions: `ACTIVE` → `CONSUMED` (irreversible)

**Redis CONSUMED lock (`phase-3/shared/redis_token.py`):**
```python
mark_consumed(token_id) → bool   # SET NX — True = first claim, False = duplicate
get_status(token_id)    → str    # 'CONSUMED' or None
```
Phase 4 must call `mark_consumed()` BEFORE issuing any credit. Gracefully degrades if Redis is unavailable — DB `status=CONSUMED` is authoritative.

---

## 7. Phase 4 — Execution Gateway, Reconciliation & Audit ACR

### Purpose
Redeems the governance token through an 8-gate safety check, executes the credit/debit, matches the settlement, and produces the final WORM-locked Action Certification Record.

**API Gateway:** FastAPI on port 8001.

### Key Components

#### 7.1 Execution Gateway (`services/execution_gateway/`)
**8 gates — all must pass before any money moves:**

| Gate | Check |
|------|-------|
| 1 | Token Ed25519 signature valid |
| 2 | Token not expired (`expires_at > now`) |
| 3 | Token not consumed (Redis SET NX + DB check) |
| 4 | Tenant binding correct (SHA-256 of `tenant_id + decision_id`) |
| 5 | Scope authorized (`EXECUTE_CREDIT_MEMO` or `EXECUTE_DEBIT_NOTE`) |
| 6 | Sanctions screening (stub; real integration in production) |
| 7 | FX rate lock within ±5% tolerance (stub) |
| 8 | Carrier connector certified and ACTIVE (stub) |

On **pass**: dispatch, mark token CONSUMED, write `execution_envelopes`, publish `execution.started`.  
On **fail**: raise `GateFailureError` with gate number and reason — zero state changes.

#### 7.2 Reconciliation Service (`services/reconciliation_svc/`)
Matches the execution result against the carrier's connector response.

- Reads `connector_responses` table for settlement confirmation
- Writes `reconciliations` rows with match/mismatch status
- Writes `outcomes` — final financial settlement record
- Publishes `reconciliation.done` to Kafka

#### 7.3 Audit ACR Service (`services/audit_acr_svc/`)
Produces the **Action Certification Record** — an offline-verifiable, WORM-locked artifact.

**8-artifact Merkle tree:**

| Artifact | Source |
|----------|--------|
| 1 | `source_record_hash` — canonical invoice SHA-256 |
| 2 | `canonical_invoice_hash` — truth row SHA-256 |
| 3 | `evidence_bundle_hash` — Merkle root of evidence items |
| 4 | `finding_hash` — reasoning output SHA-256 |
| 5 | `proposal_hash` — recovery proposal SHA-256 |
| 6 | `governance_decision_hash` — approval decision SHA-256 |
| 7 | `token_hash` — governance token SHA-256 |
| 8 | `envelope_hash` — execution envelope SHA-256 |

**ACR package (`acr_verify_<case_id>.json`):**
```json
{
  "acr_id": "...",
  "case_id": "...",
  "merkle_root": "...",
  "artifacts": [...],
  "public_keys": {...},
  "issued_at": "...",
  "acr_signature": "...",
  "acr_kid": "..."
}
```

**WORM lock:** `is_locked=TRUE` in `action_certification_records` is irreversible. The ACR relay uploads to Cloud Storage and writes to `audit_worm_index` (append-only). Once locked, no modification is possible at the DB or application layer.

**Offline verification:** Any party with the ACR package and the carrier's public key can verify the entire chain without network access.

---

## 8. Phase 5 — React Frontend

### Purpose
Full-featured dashboard for analysts, managers, and admins to manage cases, review governance, monitor Kafka events, and verify ACRs.

**Tech stack:** React 18, TypeScript, Vite, Redux Toolkit, Axios, Tailwind CSS.  
**Dev port:** 5173. All API calls proxy through Vite to backend on port 8000.

### Key Files

| File | Purpose |
|------|---------|
| `src/api/client.ts` | Axios instances with HttpOnly cookie auth + X-Tenant-ID header |
| `src/api/zoiko.ts` | Typed API service layer (USE_MOCK gate on every method) |
| `src/store/authSlice.ts` | Redux auth state (JWT in HttpOnly cookie only — not in localStorage) |
| `src/App.tsx` | Routes + session hydration from cookie on mount |
| `src/auth/Login.tsx` | Login + registration + Google OAuth |
| `src/auth/GoogleCallback.tsx` | Google OAuth code exchange (useRef guard prevents StrictMode double-fire) |
| `vite.config.ts` | Dev proxy: `/api → http://localhost:8000` |

### Auth Security Model
- JWT stored exclusively in **HttpOnly, SameSite=Strict cookie** (not localStorage, not sessionStorage)
- JavaScript cannot read the token — XSS cannot steal it
- Non-sensitive display fields (tenant, role, name, email) stored in localStorage for page-reload hydration
- On logout: `POST /v1/auth/signout` tells backend to delete the cookie; Redux + localStorage cleared client-side
- On page reload with cleared localStorage: `GET /v1/auth/me` restores session from cookie

### Environment Variables (`.env.local`)
```
VITE_USE_MOCK=false                # false = live backend
VITE_API_BASE=/api                 # routes through Vite proxy
VITE_DEV_JWT=<HS256 token>         # dev-only: bypasses cookie auth
VITE_DEV_TENANT=<tenant-uuid>      # dev-only: tenant header
```

### Role-Based Access
| Role | Permissions |
|------|-------------|
| `analyst` | Submit cases, create proposals |
| `manager` | Approve/reject proposals (SoD: cannot be the same as proposer) |
| `admin` | All of the above + user management, tenant management |

### Feature Pages
| Route | Feature |
|-------|---------|
| `/` | Dashboard with live stats |
| `/cases` | Case list with status filters |
| `/cases/:id` | Case detail with full audit trail |
| `/analyst` | Analyst review queue |
| `/manager` | Manager approval queue |
| `/execute` | Execution gateway trigger |
| `/crypto` | ACR viewer and Merkle verifier |
| `/alerts` | Live Kafka event stream |
| `/database` | Live DB row counts (admin only) |
| `/users` | User management (admin only) |

---

## 9. Security Model

### Authentication
- JWT issued as HttpOnly cookie (never in response body post-implementation)
- `ZOIKO_DEV_MODE=true` bypasses JWT signature check in development
- Google SSO supported via OAuth 2.0 Authorization Code flow
- Google SSO users have `password_hash=''` — cannot use email/password login

### Authorization
- OPA fail-closed: 503 if OPA server unreachable — never silently permits
- RBAC enforced: analyst ≠ manager ≠ admin privileges
- SoD hard-enforced: proposer cannot approve their own proposal
- Row-Level Security (RLS) on every tenant-scoped table

### Data Integrity
- JCS canonicalization ensures deterministic hashing
- Domain-tagged hashes prevent cross-type forgery
- Ed25519 signatures on tokens and evidence items
- Merkle roots on evidence bundles and ACR artifacts
- WORM-locked ACR — irreversible once issued

### Transport
- HTTPS required in production (`ZOIKO_ENV=production`)
- HSTS, X-Frame-Options, CSP, and other security headers injected by `SecurityHeadersMiddleware`
- CORS restricted to registered origins (`ZOIKO_CORS_ORIGINS`)

---

## 10. Non-Negotiable Rules

| # | Rule |
|---|------|
| 1 | JCS vectors 100% green — hard CI block |
| 2 | Hash BEFORE encrypt |
| 3 | RLS on every tenant-scoped table |
| 4 | `lineage_records`, `case_events`, `evidence_items`, `audit_worm_index` — APPEND-ONLY, never UPDATE/DELETE |
| 5 | OPA fail-closed — 503 on unavailability, never permit |
| 6 | SoD enforced: proposer ≠ approver |
| 7 | 8-gate execution — all gates must pass before money moves |
| 8 | WORM bucket — `is_locked=true` is irreversible |
| 9 | `Idempotency-Key` + `X-Tenant-ID` on every mutating API call |

---

## 11. SC-001 Reference Scenario

**Full end-to-end flow for BlueDart / Amazon India:**

```
1. INGEST
   POST /v1/cases/submit
   { carrier: "BlueDart", amount: 12500, route: "DEL→BOM" }
   → JCS → SHA-256 → AES-256-GCM encrypt → source_records

2. VALIDATE
   Contract rate lookup → ₹8,000 allowed
   Overcharge detected: ₹4,500
   → validation_results row written

3. CANONICAL TRUTH
   Authoritative invoice row written
   → canonical_invoices

4. CASE OPEN
   case.status = FINDING_GENERATED
   confidence = 0.96 (SC-001 deterministic)
   → cases table

5. EVIDENCE BUNDLE
   Invoice bytes + validation result → Merkle bundle
   Ed25519 signed per item
   → evidence_bundles, evidence_items

6. REASONING
   7-step agent runtime → SC-001 confidence 0.96
   GROQ AI explanation (supplementary)
   → findings

7. GOVERNANCE — ANALYST
   POST /v1/cases/{id}/propose  (role=analyst)
   Recovery proposal: ₹4,500 debit note to BlueDart
   → governance_tasks (PROPOSAL_CREATED)

8. GOVERNANCE — MANAGER
   POST /v1/cases/{id}/decide  (role=manager, actor ≠ proposer)
   decision = APPROVED
   → governance_tokens (ACTIVE, 15-min TTL)

9. EXECUTION GATEWAY
   POST /v1/execute  { token_id: ... }
   8 gates checked → all pass
   Token marked CONSUMED (Redis + DB)
   Credit memo issued to BlueDart
   → execution_envelopes

10. RECONCILIATION
    Settlement matched against connector response
    → reconciliations, outcomes

11. ACR ISSUED
    8-artifact Merkle tree computed
    Ed25519 signed
    WORM locked (is_locked=TRUE, irreversible)
    → action_certification_records, audit_worm_index

12. CASE CLOSED
    case.status = CLOSED
    ACR package available for offline verification
    ₹4,500 recovered.
```

---

## Appendix — Running the System

### One-click start
```powershell
.\launch.bat
```

### Backend only (Phase 2)
```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:ZOIKO_DEV_MODE = "true"
$env:PYTHONIOENCODING = "utf-8"
cd phase-2
python -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8000
```

### Frontend only
```powershell
cd zoiko-frontend\frontend
npm run dev   # http://localhost:5173
```

### Run all tests
```powershell
cd phase-0; py -m pytest packages/zoiko-common/tests -q --tb=short; cd ..
cd phase-1; py -m pytest tests/ packages/zoiko-kms/tests/ -q --tb=short; cd ..
cd phase-2; py -m pytest -q --tb=short; cd ..
cd phase-3; py -m pytest -q --tb=short; cd ..
```

### Full pipeline demo
```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
cd phase-2; py demo_phase2.py; cd ..   # produces case in PENDING_APPROVAL
cd phase-3; py demo_phase3.py; cd ..   # produces ACTIVE governance token
cd backend\execution; py scripts\demo_phase4.py; cd ..\..   # executes, reconciles, locks ACR
```

### Production environment variables
```
ZOIKO_ENV=production          # enables Secure cookie, HTTPS enforcement
DB_URL=<neon-or-postgres-url>
ZOIKO_DEV_SECRET=<long-random-secret>
GOOGLE_CLIENT_ID=<gcp-oauth-client-id>
GOOGLE_CLIENT_SECRET=<gcp-oauth-secret>
OPA_URL=http://opa:8181
KAFKA_BOOTSTRAP=<broker:9092>
ZOIKO_CORS_ORIGINS=https://yourdomain.com
JWT_TTL_SECONDS=86400
TOKEN_TTL_MINUTES=15
```

---

*Document generated from live codebase — June 2026*

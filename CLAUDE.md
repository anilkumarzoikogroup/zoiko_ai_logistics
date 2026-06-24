# Zoiko AI Logistics — CLAUDE.md

Project context for Claude Code. Read this before making any changes.

---

## What This System Does

Zoiko detects freight overcharges automatically and recovers money through a cryptographically auditable pipeline. The SC-001 scenario: **BlueDart bills Amazon India ₹12,500, contract allows ₹8,000 — ₹4,500 overcharge caught, two humans approve, money recovered, audit record locked.**

---

## Phase Build Status

| Phase | Built | Tests | What it is |
|-------|-------|-------|-----------|
| Phase 0 | ✅ | 86/86 | JCS + SHA-256 + Ed25519 + 25 DB tables + Streamlit dashboard |
| Phase 1 | ✅ | 54/54 | KMS key hierarchy + OIDC/JWT + Kafka (17 topics) + OPA policies |
| Phase 2 | ✅ | 38/38 | Ingestion → Validation → Canonical Truth → Case Orchestration · OPA fail-closed · 24 API routes · /v1/ prefix |
| Phase 3 | ✅ | 46/46 | Evidence → Reasoning → Governance → Token · OPA wired · DEV_MODE · Redis CONSUMED lock |
| Phase 4 | ✅ | unit  | 8-gate Execution Gateway → Reconciliation → ACR · WORM index · CLOSED case state |
| Phase 5 | ✅ | — | React 18 + TypeScript + Vite frontend · /v1/ API prefix · fully wired to live backend |
| Phase 6 | ✅ | — | Recovery pipeline — expected_recoveries → recovery_instruments → recovery_matches (tiered) → ledger_svc → write_off_svc → recovery_proofs (acr_ready) |
| C07 | ✅ | — | Data governance/compliance — legal holds (blocking), retention, crypto-shred, archive/restore (verified)/purge jobs, observability dashboard (admin-only) |

---

## Architecture — How Phases Connect

Phases share the PostgreSQL database. They do NOT make live API calls to each other.

```
Phase 2 writes → cases (PENDING_APPROVAL)
Phase 3 reads  → case_id, writes evidence_bundles / findings / governance_tokens (ACTIVE)
Phase 4 reads  → token_id, writes execution_envelopes / reconciliations / ACR
Phase 6 reads  → case_id / authorization_decision_id, writes expected_recoveries →
                  recovery_instruments → recovery_matches → ledger_entries → recovery_proofs (acr_ready)
C07     reads  → tenant_id / record refs, writes legal_holds / retention jobs / archive,
                  restore, purge, crypto-shred jobs (legal holds block purge & crypto-shred)
```

Frontend (Phase 5) talks to the Phase 2 API gateway on port 8000 via Vite proxy.
In production each phase is a separate container communicating via Kafka events.
In dev/tests each phase runs in the same Python process using MockKafkaBroker.

---

## File Map — Where Everything Lives

```
zoiko-logistics/
├── requirements.txt                 ← Single combined requirements file
├── docker-compose.yml               ← Full local stack (postgres, redis, kafka, opa, services)
├── launch.bat                       ← One-click: DB check → backend → frontend → browser
├── setup.bat                        ← One-time setup (venv + pip + npm install)
├── EXECUTION_GUIDE.md               ← Step-by-step run commands
├── alembic.ini                      ← Points to backend/alembic/migrations
│
├── backend/
│   ├── core/                        ← Shared crypto, DB migrations, common library
│   │   ├── packages/zoiko-common/zoiko_common/
│   │   │   ├── crypto/jcs.py        ← RFC 8785 JCS canonicalization (CI hard block)
│   │   │   ├── crypto/merkle.py     ← Merkle tree (domain-tagged)
│   │   │   ├── crypto/signing.py    ← Ed25519 wrapper
│   │   │   ├── kafka/schemas.py     ← KafkaEventEnvelope (17-topic registry + envelope format)
│   │   │   ├── errors/exceptions.py ← ZoikoError hierarchy (GateFailureError, SoDViolationError…)
│   │   │   └── observability/logging.py ← JSON structured logging with tenant/trace context
│   │   ├── db/migrations/           ← Alembic: 31 migration versions (0001–0031)
│   │   └── scripts/                 ← demo_sc001.py, tenant_fuzzer.py
│   │
│   ├── platform/                    ← Identity (KMS, OIDC), policy (OPA), events (Kafka)
│   │   ├── packages/zoiko-kms/      ← zoiko_kms: hierarchy.py, local_backend.py
│   │   ├── middleware/oidc/         ← token_verifier.py, claims.py
│   │   ├── middleware/opa/          ← client.py (fail-closed), MockOPAClient
│   │   └── kafka/                   ← producer.py (zoiko.* topics), consumer.py, mock_kafka.py
│   │
│   ├── gateway/                     ← API gateway — ingestion, validation, case FSM (port 8000)
│   │   ├── services/api_gateway/    ← app.py (/v1/ prefix), auth.py, models.py
│   │   │   ├── config.py            ← pydantic-settings BaseSettings
│   │   │   ├── constants.py         ← CaseStatus, GovernanceDecisionType, ChannelType enums
│   │   │   └── routers/             ← identity, connectors, canonical, evidence, approval,
│   │   │                              reasoning, policy, evaluation, reports, c07, observability
│   │   ├── services/ingestion_svc/  ← handler.py (5-step write pattern), file_adapter.py (EDI/CSV)
│   │   ├── services/validation_svc/ ← handler.py (contract rate engine)
│   │   ├── services/canonical_truth/← handler.py (authoritative row)
│   │   ├── services/case_orchestration/ ← handler.py (FSM)
│   │   ├── services/legal_hold_svc/ ← handler.py (blocks purge/crypto-shred while held)
│   │   ├── services/retention_svc/  ← handler.py (retention schedule jobs)
│   │   ├── services/archive_svc/    ← handler.py (archive jobs)
│   │   ├── services/restore_svc/    ← handler.py (restore + 10-check verification)
│   │   ├── services/purge_svc/      ← handler.py (purge jobs, legal-hold aware)
│   │   ├── services/crypto_shred_svc/ ← handler.py (tenant key destruction, legal-hold aware)
│   │   ├── services/observability_svc/ ← handler.py (C07 observability dashboard data)
│   │   ├── shared/db.py             ← DB helpers (q, q1)
│   │   └── paths.py                 ← sys.path bootstrap (import first)
│   │       (no per-service Dockerfile — built from root Dockerfile/Dockerfile.backend, working_dir=/app/backend/gateway)
│   │
│   ├── governance/                  ← Evidence, reasoning, tokens, SoD (port 8002)
│   │   ├── services/evidence_svc/   ← handler.py (growing/append-only Merkle bundle)
│   │   ├── services/reasoning_svc/  ← handler.py (SC-001 confidence 0.96)
│   │   ├── services/governance_svc/ ← handler.py (SoD + case FSM)
│   │   ├── services/token_svc/      ← handler.py (tenant-bound token, 15-min TTL)
│   │   ├── shared/redis_token.py    ← Redis CONSUMED lock (also used by execution)
│   │   └── paths.py                 ← sys.path bootstrap (import first)
│   │       (no per-service Dockerfile — built from root Dockerfile/Dockerfile.backend, dockerCommand cd's into /app/backend/governance)
│   │
│   ├── execution/                   ← 8-gate execution, reconciliation, recovery, ACR (port 8001)
│   │   ├── services/execution_gateway/ ← handler.py (8-gate check), models.py
│   │   ├── services/reconciliation_svc/ ← handler.py (settlement match, case variances)
│   │   ├── services/audit_acr_svc/  ← handler.py (8-artifact Merkle ACR)
│   │   ├── services/recovery/
│   │   │   ├── expected_recovery_svc/  ← handler.py (expected_recoveries CRUD + supersede)
│   │   │   ├── recovery_instrument_svc/← handler.py (instruments — credit memos, refunds…)
│   │   │   ├── recovery_match_svc/     ← handler.py (tiered matching against instruments)
│   │   │   ├── ledger_svc/             ← handler.py (double-entry ledger, LEDGER_CLOSED)
│   │   │   ├── write_off_svc/          ← handler.py (PENDING → AUTHORIZED → POSTED → WRITTEN_OFF)
│   │   │   ├── recovery_proof_svc/     ← handler.py (rollup proof, acr_ready flag)
│   │   │   └── recovery_exceptions_svc/← handler.py (stuck/aged recovery exceptions)
│   │   ├── services/api_gateway/    ← app.py — /v1/execute, /v1/reconcile, /v1/recovery/*, /v1/cases/{id}/acr
│   │   └── paths.py                 ← sys.path bootstrap (import first)
│   │       (no per-service Dockerfile — built from root Dockerfile/Dockerfile.backend, dockerCommand cd's into /app/backend/execution)
│   │
│   └── api/                         ← Frontend-facing reverse proxy (port 8080, optional)
│       └── app.py                   ← Routes /v1/* to gateway/governance/execution
│
└── zoiko-frontend/frontend/
    ├── src/api/client.ts            ← Axios instances (api/api4) · /v1/ API base · auth + idempotency headers
    ├── src/api/zoiko.ts             ← API service layer (USE_MOCK gate on every method)
    ├── src/features/recovery/RecoveryDashboard.tsx     ← Phase 6 recovery pipeline UI
    ├── src/features/reconciliation/ReconciliationPage.tsx ← envelope reconciliation + variances
    ├── src/features/compliance/     ← C07 pages: LegalHolds, DataRetention, CryptoShred,
    │                                   ArchiveJobs, RestoreJobs, PurgeJobs, DataGovernance (admin-only)
    ├── vite.config.ts               ← Dev proxy: /api → :8000, /api4 → :8001
    ├── Dockerfile                   ← Multi-stage: dev + build + nginx prod
    └── .env.local                   ← VITE_USE_MOCK=false · VITE_API_BASE=/api
```

---

## Frontend Environment Variables (.env.local)

```
VITE_USE_MOCK=false
VITE_API_BASE=/api
VITE_DEV_JWT=<HS256 JWT signed with zoiko-dev-secret-for-testing-only>
VITE_DEV_TENANT=11111111-1111-1111-1111-111111111111
```

- `VITE_USE_MOCK=false` — all API calls hit the real backend (never use mock fixtures)
- `VITE_API_BASE=/api` — routes through the Vite proxy (avoids CORS, same-origin)
- `VITE_DEV_JWT` — injected as `Authorization: Bearer <token>` on every request
- `VITE_DEV_TENANT` — injected as `X-Tenant-ID` on every request

The Vite proxy in `vite.config.ts` rewrites `/api/*` → `http://localhost:8000/*`.

**To switch back to mock mode** (no backend needed):
```
VITE_USE_MOCK=true
```
Then restart `npm run dev`.

---

## Backend Environment Variables (gateway)

```
DB_URL=postgresql://postgres:1234@localhost/zoiko
ZOIKO_DEV_MODE=true        # bypasses JWT verification, auto-resolves tenant from X-Tenant-ID
ZOIKO_DEV_SECRET=zoiko-dev-secret-for-testing-only   # HS256 signing secret
ZOIKO_ISSUER=https://auth.zoikotech.com
OPA_URL=                   # empty = MockOPAClient (allow=True); set to real OPA URL for prod
PYTHONIOENCODING=utf-8     # required on Windows to handle ₹ and → characters
```

---

## Kafka Topics (Phase 1 Registry)

All 17 registered topics. Use ONLY these names in `KafkaMessage(topic=...)`.

```
invoice.received   invoice.validated   invoice.canonical
case.opened        case.updated        case.closed
evidence.bundled   finding.created     proposal.created
decision.made      token.issued        token.consumed
execution.started  execution.completed
reconciliation.done acr.issued         audit.locked
```

Phase 3 mapping:
- evidence_svc  → `evidence.bundled`
- reasoning_svc → `finding.created`
- governance_svc create_task → `case.updated`
- governance_svc decide      → `decision.made`
- token_svc     → `token.issued`

---

## DB Connection

```
DB_URL = postgresql://postgres:1234@localhost/zoiko
```

Set via: `$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"`

The `shared/db.py` in both `backend/gateway` and `backend/governance` defaults to this URL if `DB_URL` env var is unset.

---

## Running Commands

### Start everything (recommended)
```powershell
.\launch.bat
```

### Backend only
```powershell
cd backend\gateway
..\..\venv\Scripts\activate
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:ZOIKO_DEV_MODE = "true"
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8000
```

### Frontend only
```powershell
cd zoiko-frontend\frontend
$env:VITE_USE_MOCK = "false"
npm run dev
# http://localhost:5173
```

### Tests (each service independently)
```powershell
cd backend\core; py -m pytest packages/zoiko-common/tests -q --tb=short; cd ..\..
cd backend\platform; py -m pytest tests/ packages/zoiko-kms/tests/ -q --tb=short; cd ..\..
cd backend\gateway; py -m pytest -q --tb=short; cd ..\..
cd backend\governance; py -m pytest -q --tb=short; cd ..\..
```

### Full pipeline demo
```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"
cd backend\core; py scripts\demo_sc001.py; cd ..\..   # full SC-001 walkthrough across all phases
```

### Check live API
```powershell
curl http://localhost:8000/health
curl http://localhost:8000/docs         # Swagger UI — gateway routes
curl http://localhost:8001/docs         # Swagger UI — execution gateway (recovery/reconciliation/ACR)
curl http://localhost:5173/api/health   # same, through Vite proxy
```

---

## Gateway API Routes (port 8000, /v1/ prefix) — core set

| Route | Notes |
|-------|-------|
| `POST /cases/submit` | Full pipeline in one call: ingest → validate → canonical → case → evidence → finding |
| `GET /cases` | All cases for tenant, sorted by opened_at DESC |
| `GET /cases/{id}` | Single case with carrier/amount/diff/confidence from JOIN |
| `GET /cases/{id}/events` | Append-only case_events audit trail |
| `POST /cases/{id}/propose` | Analyst proposes recovery (requires role=analyst) |
| `POST /cases/{id}/decide` | Manager approves/rejects (SoD: actor ≠ proposer) |
| `GET /cases/{id}/validation` | Overcharge amount and rule trace |
| `GET /cases/{id}/canonical-invoice` | Authoritative invoice row |
| `GET /cases/{id}/finding` | AI confidence score and rule breakdown |
| `GET /cases/{id}/proposal` | Recovery proposal details |
| `GET /cases/{id}/acr` | Action Certification Record (post-Phase 4) |
| `GET /tokens` | Governance tokens for tenant |
| `GET /tokens/{id}` | Single token with status/expiry |
| `POST /contract-rates` | Create a new contract rate |
| `GET /contract-rates` | List all contract rates |
| `DELETE /contract-rates/{id}` | Delete a contract rate |
| `POST /ingestion/parse-invoice` | Upload PDF/image, extract carrier/route/amount |
| `GET /ingestion/source-records` | Raw ingested records |
| `GET /kafka/events` | Last N Kafka events (for Alerts page) |
| `GET /stats` | Aggregated stats: total cases, overcharge sum, by-carrier |
| `GET /admin/db-stats` | Live row counts from pg_stat_user_tables |
| `GET /health` | `{"status":"ok","service":"api-gateway","version":"2.0.0"}` |

Required headers on every request:
- `Authorization: Bearer <JWT>`
- `X-Tenant-ID: <tenant-uuid>`
- `Idempotency-Key: <unique-string>` (mutations only)

---

## Execution Gateway API Routes (port 8001, /v1/ prefix)

| Route | Notes |
|-------|-------|
| `POST /execute` | 8-gate execution check, redeems governance token, writes execution_envelopes |
| `POST /reconcile` | Match an execution envelope against connector_responses → reconciliations |
| `GET /cases/{id}/variances` | Reconciliation variance records for a case |
| `POST /cases/{id}/variances/{vid}/resolve` | Resolve or waive an OPEN variance |
| `POST /cases/{id}/acr` | Issue 8-artifact Merkle ACR (WORM-locked) |
| `POST /recovery/expected` | Create an expected recovery (dedup on `authorization_decision_id`) |
| `GET /recovery/expected:by-case` | Expected recoveries for a case |
| `POST /recovery/expected/{id}/supersede` | Replace an expected recovery (audit-preserving) |
| `POST /recovery/instruments` | Create a recovery instrument (dedup on `external_reference`) |
| `GET /recovery/instruments:by-case` / `:by-counterparty` | List instruments |
| `POST /recovery/match` | Tiered match of an expected recovery against AVAILABLE instruments |
| `GET /recovery/matches:by-case` / `:by-expected` | List matches |
| `POST /recovery/matches/{id}/reverse` | Reverse a recovery match |
| `GET /recovery/exceptions` | Stuck/aged expected recoveries (no match after N days) |
| `POST /recovery/proofs` | Generate recovery proof rollup (sets `acr_ready`) |
| `GET /recovery/proofs:by-case` / `:latest` | Fetch recovery proofs |

---

## C07 Data Governance API Routes (gateway, port 8000, /v1/ prefix, admin-only)

| Route | Notes |
|-------|-------|
| `POST /legal-holds` | Place a legal hold on records — blocks purge & crypto-shred |
| `GET /legal-holds/{id}` / `GET /legal-holds:by-scope` | Fetch/list holds |
| `POST /legal-holds/{id}/release` | Release a hold |
| `POST /data/retention/policies` / `GET /data/retention/policies/{id}` | Retention policy CRUD |
| `POST /data/retention/assign` / `GET /data/retention:by-record` | Assign + look up retention for a record |
| `POST /data/archive/jobs` / `GET /data/archive/jobs/{id}` | Archive job lifecycle |
| `GET /data/archive/{id}/verify` | Verify archive integrity |
| `POST /data/archive/{id}/restore` | Restore from an archive |
| `POST /data/restore/jobs` / `GET /data/restore/jobs/{id}` | Restore job lifecycle |
| `POST /data/restore/jobs/{id}/verify` | Run the 10-check restore verification |
| `GET /data/restore/jobs/{id}/verification` | Fetch verification results |
| `POST /data/restore/jobs/{id}/approve-use` | Approve restored data for use |
| `POST /data/purge/jobs` / `GET /data/purge/jobs/{id}` | Purge job lifecycle — blocked if an active legal hold covers the records |
| `POST /data/purge/jobs/{id}/approve` | Approve a pending purge |
| `GET /data/purge/jobs/{id}/evidence` | Purge evidence record |
| `POST /privacy/crypto-shred` / `GET /privacy/crypto-shred/{id}` | Destroy tenant data-encryption keys — blocked if an active legal hold covers the records |
| `GET /privacy/crypto-shred/{id}/verify` | Verify a crypto-shred completed |
| `GET /data/observability/metrics` / `GET /data/observability/alerts` | C07 observability dashboard data |

---

## Crypto Conventions

### Domain-tagged SHA-256
Every hash uses a unique prefix to prevent cross-type confusion:
```
SHA-256(b"zoiko.ingestion.invoice.v1:"    + canonical_bytes)   → source record
SHA-256(b"zoiko.canonical.invoice.v1:"    + canonical_bytes)   → canonical invoice
SHA-256(b"zoiko.evidence.item.v1:"        + content_bytes)     → evidence item
SHA-256(b"zoiko.finding.v1:"              + jcs_bytes)         → finding
SHA-256(b"zoiko.proposal.v1:"             + jcs_bytes)         → proposal
SHA-256(b"zoiko.governance.decision.v1:"  + jcs_bytes)         → governance decision
SHA-256(b"zoiko.token.v1:"               + jcs_bytes)         → governance token
```

### Merkle domain tags
```
"zoiko/v1/source-record"    ← ingestion
"zoiko/v1/evidence-item"    ← evidence bundle items
"zoiko/v1/acr"              ← Action Certification Record (8 artifacts)
```

### JCS (RFC 8785)
Keys sorted by Unicode code point, no whitespace, UTF-8 bytes.
`canonicalize(dict)` → `bytes` — use `zoiko_common.crypto.jcs.canonicalize`.

### Signing
`sign(tenant_slug, hash_bytes)` → `(signature_bytes, kid)`.
Defined in `backend/governance/shared/signer.py` and `backend/gateway/shared/signer.py`.

---

## SC-001 Confidence Formula

```python
_RULES = {
    "fuel_charge":  {"confidence": 1.00, "weight": 0.50},
    "accessorial":  {"confidence": 0.92, "weight": 0.50},
}
SC001_CONFIDENCE = 0.96  # = 0.50×1.00 + 0.50×0.92 — MUST be exactly this value
```

This is deterministic. Any change to formula or weights is a breaking change.

---

## SoD Rule

```python
if actor_sub == task["proposer_sub"]:
    raise ValueError(
        f"Separation of Duties violation: actor_sub '{actor_sub}' "
        f"cannot be the same as proposer_sub '{task['proposer_sub']}'"
    )
```

This check happens in `GovernanceHandler.decide()` BEFORE any DB write.

---

## Case FSM States

```
NEW → EVIDENCE_PENDING → FINDING_GENERATED → APPROVAL_PENDING
    → EXECUTION_READY → DISPATCHED → OUTCOME_RECORDED → CLOSED
    → ABORTED (from any state)
```

When using `POST /v1/cases/submit`, the case returns as `FINDING_GENERATED` (Phase 2+3 inline).
Phase 4 demo advances it through: `EXECUTION_READY → DISPATCHED → OUTCOME_RECORDED → CLOSED`.

---

## APPEND-ONLY Tables — Never UPDATE or DELETE

```
lineage_records
case_events
evidence_items
audit_worm_index
```

---

## 9 Non-Negotiable Rules

1. JCS vectors 100% green — hard CI block
2. Hash BEFORE encrypt
3. RLS on every tenant-scoped table
4. APPEND-ONLY tables: never UPDATE/DELETE
5. OPA fail-closed — 503 on unavailability, never permit
6. SoD enforced: proposer ≠ approver
7. 8-gate execution — all gates pass before money moves
8. WORM bucket — is_locked=true is irreversible
9. Idempotency-Key + X-Tenant-ID on every mutating API call

---

## Common Mistakes to Avoid

| Mistake | Correct behaviour |
|---------|------------------|
| Using wrong Kafka topic name | Use only names from REGISTERED_TOPICS in backend/platform/kafka/producer.py |
| Passing topic string as broker argument | `EvidenceHandler(DB_URL, broker_object, slug)` — broker is the MockKafkaBroker instance |
| Forgetting `paths.py` import in governance modules | Always `import paths` as the first import |
| Changing SC001_CONFIDENCE | This value is deterministic — never change it |
| Using `psycopg2.extras.register_uuid()` late | Call it before any psycopg2 connection that handles UUIDs |
| UPDATE/DELETE on append-only tables | Only INSERT is permitted |
| Frontend showing 47 mock cases | `VITE_USE_MOCK=false` in .env.local, then restart `npm run dev` + hard refresh browser |
| "Submission failed" in UI | Check backend is running on port 8000: `curl http://localhost:8000/health` |
| Backend not picking up .py changes | Kill Python process and restart uvicorn — `--reload` watches files but can miss them |

---

## OPA Wiring (gateway & governance)

Both gateways call OPA after JWT verification. Behaviour by env:

| `OPA_URL` set? | `ZOIKO_DEV_MODE` | OPA client used | Effect |
|---------------|-----------------|-----------------|--------|
| No (default)  | false           | MockOPAClient   | allow=True — tests pass without an OPA server |
| No            | true            | MockOPAClient   | allow=True — dev dashboard works without OPA |
| Yes           | false           | OPAClient(url)  | Real fail-closed OPA — 503 if unreachable |

To run with real OPA locally:
```powershell
docker run -d -p 8181:8181 openpolicyagent/opa:latest run --server
$env:OPA_URL = "http://localhost:8181"
```

---

## Token TTL

Governance tokens expire in **15 minutes** (configurable via `TOKEN_TTL_MINUTES` env var).
This is the execution window: Phase 4 must redeem the token within 15 minutes of issuance.

```python
TOKEN_TTL_MINUTES = int(os.getenv("TOKEN_TTL_MINUTES", "15"))
expires_at = now + timedelta(minutes=TOKEN_TTL_MINUTES)
```

---

## Redis Token CONSUMED Lock (Phase 3 → Phase 4)

`phase-3/shared/redis_token.py` provides:
```python
mark_consumed(token_id) → bool   # SET NX — True = first claim, False = duplicate
get_status(token_id)    → str    # 'CONSUMED' or None
```

Phase 4 Execution Gateway MUST call `mark_consumed()` BEFORE issuing the credit.
Returns False → duplicate execution blocked immediately (no DB write needed).
Gracefully no-ops if Redis unavailable — DB `status=CONSUMED` update is authoritative.

---

## Phase 4 / Execution Gateway — Key Files

| File | Purpose |
|------|---------|
| `backend/execution/services/execution_gateway/handler.py` | 8-gate check (sig, expiry, consumed, binding, scope, sanctions, FX, connector) |
| `backend/execution/services/reconciliation_svc/handler.py` | Settlement match against connector_responses, writes reconciliations + outcomes + variances |
| `backend/execution/services/audit_acr_svc/handler.py` | 8-artifact Merkle ACR, writes action_certification_records + audit_worm_index |
| `backend/execution/services/recovery/*` | Phase 6 recovery pipeline (see table above) |
| `backend/execution/services/api_gateway/app.py` | FastAPI gateway (port 8001): `/v1/execute`, `/v1/reconcile`, `/v1/recovery/*`, `/v1/cases/{id}/acr` |
| `backend/execution/tests/test_execution_gateway.py` | Gate unit tests (no DB) + integration test (skip if no DB) |
| `backend/execution/tests/test_acr.py` | ACR verify bundle structure tests |

### Running the Execution Gateway API
```powershell
cd backend\execution
..\..\.venv\Scripts\activate
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:ZOIKO_DEV_MODE = "true"
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8001
```

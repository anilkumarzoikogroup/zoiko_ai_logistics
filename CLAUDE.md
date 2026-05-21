# Zoiko AI Logistics — CLAUDE.md

Project context for Claude Code. Read this before making any changes.

---

## What This System Does

Zoiko detects freight overcharges automatically and recovers money through a cryptographically auditable pipeline. The SC-001 scenario: **BlueDart bills Amazon India ₹12,500, contract allows ₹8,000 — ₹4,500 overcharge caught, two humans approve, money recovered, audit record locked.**

---

## Phase Build Status

| Phase | Built | Tests | What it is |
|-------|-------|-------|-----------|
| Phase 0 | ✅ | 86/86 | JCS + SHA-256 + Ed25519 + 26 DB tables + Streamlit dashboard |
| Phase 1 | ✅ | 54/54 | KMS key hierarchy + OIDC/JWT + Kafka (17 topics) + OPA policies |
| Phase 2 | ✅ | 38/38 | Ingestion → Validation → Canonical Truth → Case Orchestration · OPA fail-closed wired · 15-min token TTL |
| Phase 3 | ✅ | 46/46 | Evidence → Reasoning → Governance → Token · OPA wired · DEV_MODE · Redis CONSUMED lock ready |
| Phase 4 | ⏳ next | — | 8-gate Execution Gateway → Connector → Reconciliation → ACR |
| Phase 5 | ⏳ | — | React/TypeScript frontend + hardening + load test |

---

## Architecture — How Phases Connect

Phases share the PostgreSQL database. They do NOT make live API calls to each other.

```
Phase 2 writes → cases (PENDING_APPROVAL)
Phase 3 reads  → case_id, writes evidence_bundles / findings / governance_tokens (ACTIVE)
Phase 4 reads  → token_id, writes execution_envelopes / reconciliations / ACR
```

In production each phase is a separate container communicating via Kafka events.
In dev/tests each phase runs in the same Python process using MockKafkaBroker.

---

## File Map — Where Everything Lives

```
zoiko-logistics/
├── dashboard.py                     ← Streamlit, all phases, 20 pages
├── requirements.txt                 ← Single combined requirements file
├── EXECUTION_GUIDE.md               ← Step-by-step run commands
├── README.md                        ← Project overview
├── CLAUDE.md                        ← This file
├── zoiko_phases_story.html          ← Phase story document
│
├── phase-0/packages/zoiko-common/   ← zoiko_common: jcs.py, merkle.py, signing.py
├── phase-0/db/migrations/           ← Alembic: 0001_p0_all_tables.py (26 tables)
├── phase-0/scripts/                 ← seed_dummy_data.py, demo_sc001.py
│
├── phase-1/packages/zoiko-kms/      ← zoiko_kms: hierarchy.py, local_backend.py
├── phase-1/middleware/oidc/         ← token_verifier.py, claims.py
├── phase-1/middleware/opa/          ← client.py (fail-closed)
├── phase-1/kafka/                   ← producer.py, consumer.py, mock_kafka.py
│
├── phase-2/services/api_gateway/    ← app.py (6 routes), auth.py (OPA wired), models.py
├── phase-2/services/ingestion_svc/  ← handler.py (5-step write pattern)
├── phase-2/services/validation_svc/ ← handler.py (contract rate engine)
├── phase-2/services/canonical_truth/← handler.py (authoritative row)
├── phase-2/services/case_orchestration/ ← handler.py (FSM)
├── phase-2/shared/redis_idem.py     ← Redis idempotency (graceful degradation)
├── phase-2/demo_phase2.py           ← Full Phase 2 end-to-end demo
├── phase-2/smoke_test_gateway.py    ← 28-check API gateway smoke test
│
├── phase-3/services/api_gateway/    ← app.py (7 routes), auth.py (OPA + DEV_MODE), models.py
├── phase-3/services/evidence_svc/   ← handler.py (Merkle bundle)
├── phase-3/services/reasoning_svc/  ← handler.py (SC-001 confidence 0.96)
├── phase-3/services/governance_svc/ ← handler.py (SoD + case FSM)
├── phase-3/services/token_svc/      ← handler.py (tenant-bound token, 15-min TTL)
├── phase-3/shared/db.py             ← DB helpers (get_conn, q, q1)
├── phase-3/shared/signer.py         ← sign() wrapper over zoiko-kms
├── phase-3/shared/redis_idem.py     ← Redis idempotency (graceful degradation)
├── phase-3/shared/redis_token.py    ← Redis CONSUMED lock (Phase 4 uses this)
├── phase-3/demo_phase3.py           ← Full Phase 3 end-to-end demo
└── phase-3/paths.py                 ← sys.path bootstrap for Phase 3
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

## DB Password and Connection

```
DB_URL = postgresql://postgres:1234@localhost/zoiko
```

Set via: `$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"`

---

## Running Commands

### Tests (each phase independently)
```powershell
cd phase-0; py -m pytest packages/zoiko-common/tests -q --tb=short; cd ..
cd phase-1; py -m pytest tests/ packages/zoiko-kms/tests/ -q --tb=short; cd ..
cd phase-2; py -m pytest -q --tb=short; cd ..
cd phase-3; py -m pytest -q --tb=short; cd ..
```

### Full pipeline demo
```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:PYTHONIOENCODING = "utf-8"
cd phase-2; py demo_phase2.py; cd ..   # produces a case in PENDING_APPROVAL
cd phase-3; py demo_phase3.py; cd ..   # consumes that case, produces ACTIVE token
```

### Dashboard
```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
streamlit run dashboard.py
```

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
Defined in `phase-3/shared/signer.py` and `phase-2/shared/signer.py`.

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
OPENED → EVIDENCE_GATHERING → UNDER_REVIEW → PENDING_APPROVAL → APPROVED → EXECUTED → RECONCILED → CLOSED
                                                                          ↘ REJECTED (from any state)
```

Phase 3 `governance_svc` transitions `PENDING_APPROVAL → APPROVED` (or `REJECTED`).

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
| Using wrong Kafka topic name | Use only names from REGISTERED_TOPICS in phase-1/kafka/producer.py |
| Passing topic string as broker argument | `EvidenceHandler(DB_URL, broker_object, slug)` — broker is the MockKafkaBroker instance |
| Forgetting `paths.py` import in phase-3 modules | Always `import paths` as the first import |
| Changing SC001_CONFIDENCE | This value is deterministic — never change it |
| Using `psycopg2.extras.register_uuid()` late | Call it before any psycopg2 connection that handles UUIDs |
| UPDATE/DELETE on append-only tables | Only INSERT is permitted |

---

## OPA Wiring (Phase 2 & 3)

Both gateways now call OPA after JWT verification. Behaviour by env:

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

## What Phase 4 Will Need

- `execution_envelopes` table (already in schema)
- `connector_responses` table (already in schema)
- `reconciliations` + `outcomes` tables (already in schema)
- `action_certification_records` + `audit_worm_index` tables (already in schema)
- Read `governance_tokens` where `status='ACTIVE'` and `expires_at > now` — written by Phase 3
- Call `phase-3/shared/redis_token.mark_consumed(token_id)` as Gate 8 pre-check
- 8-gate check logic (token sig, expiry, tenant_binding, scope, sanctions, FX, connector, idempotency)
- `token.consumed` Kafka event after execution
- Merkle tree over 8 artifacts → ACR row → `audit_worm_index` row (APPEND-ONLY)

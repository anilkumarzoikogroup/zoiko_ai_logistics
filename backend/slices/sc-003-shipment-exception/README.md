# SC-003 — Shipment Exception / SLA Penalty

**Status: FULLY BUILT.** Gateway spine (port 8020), execution spine (port 8021), Alembic migration 0005, and three React frontend pages are all complete and wired to the main frontend.

---

## What This Slice Does

A carrier misses a contracted SLA (late delivery, missed pickup window, etc.).  
The contract specifies a penalty the carrier owes back.  
Zoiko detects the breach automatically, runs the 8-step cryptographic pipeline, and issues an SLA credit.

**Example:** BlueDart commits to delivering by 14:00. Package arrives at 20:00. Six-hour breach at ₹500/hour = ₹3,000 penalty, capped at ₹50,000 contract maximum. Two humans approve. Credit issued. ACR locked.

---

## Confidence Formula (deterministic — never change)

```python
RULES = {
    "delivery_window_breach": {"confidence": 1.00, "weight": 0.60},
    "sla_clause_applicable":  {"confidence": 0.88, "weight": 0.40},
}
SC003_CONFIDENCE = 0.9520  # = 1.00×0.60 + 0.88×0.40
```

---

## Breach & Penalty Computation

```python
sla_breach_hours   = max(0, (actual_delivery - committed_eta).total_seconds() / 3600)
sla_penalty_amount = min(penalty_cap, sla_breach_hours * penalty_rate_per_hour)
```

---

## Ports

| Service | Port |
|---------|------|
| SC-003 Gateway (ingestion → governance) | **8020** |
| SC-003 Execution (8-gate → reconciliation → ACR) | **8021** |

---

## File Map

```
spine/
├── gateway/                            ← port 8020
│   ├── paths.py                        ← sys.path bootstrap; falls back to SC-002's core_lib/platform_lib
│   ├── shared/
│   │   ├── db.py                       ← psycopg2 connection pool (Windows-safe keepalives)
│   │   ├── signer.py                   ← Ed25519 via LocalKMSBackend
│   │   └── redis_idem.py               ← idempotency key store (graceful fallback)
│   └── services/
│       ├── ingestion_svc/
│       │   ├── handler.py              ← ingest_exception() — 8-step write pattern
│       │   ├── models.py               ← ShipmentExceptionInput, IngestResult, ChannelEnum…
│       │   └── dedup.py                ← compute_dedup_key, check_deduplication, write_dedup_index
│       ├── canonical_truth/
│       │   ├── handler.py              ← canonicalize_shipment_exception()
│       │   └── models.py               ← CanonicalShipmentExceptionResult (field: penalty_amount)
│       ├── case_orchestration/
│       │   ├── handler.py              ← open_case() SHIPMENT_EXCEPTION branch, transition_state()
│       │   └── models.py               ← CaseResult
│       ├── evidence_svc/
│       │   ├── handler.py              ← build_bundle() — 5 artifact types, Merkle root
│       │   └── models.py               ← EvidenceItemResult, EvidenceBundleResult
│       ├── reasoning_svc/
│       │   ├── handler.py              ← generate_finding() — SC003_CONFIDENCE = 0.9520
│       │   └── rules.py                ← RULES dict + SC003_CONFIDENCE constant
│       ├── governance_svc/
│       │   ├── handler.py              ← propose(), decide() — SoD enforced before any DB write
│       │   └── models.py               ← GovernanceTaskResult
│       ├── token_svc/
│       │   └── handler.py              ← 15-min TTL token, advances case to EXECUTION_READY
│       └── api_gateway/
│           ├── app.py                  ← FastAPI port 8020, 9 routes
│           ├── auth.py                 ← JWT + OPA dependency
│           ├── models.py               ← ShipmentExceptionSubmitRequest, UIProposalRequest…
│           └── routes_logic.py         ← submit_exception(), ui_list_exceptions(), run_evidence_and_reasoning_exception()
│
└── execution/                          ← port 8021
    ├── paths.py                        ← sys.path bootstrap; falls back to SC-002's core_lib/platform_lib
    ├── shared/
    │   ├── db.py
    │   ├── signer.py
    │   └── redis_token.py              ← mark_consumed() / get_status() Redis NX lock
    └── services/
        ├── execution_gateway/
        │   └── handler.py              ← ExecutionGatewayHandler.execute() — 8 gates
        ├── reconciliation_svc/
        │   └── handler.py              ← ReconciliationHandler — "Commitment Match" strategy
        ├── audit_acr_svc/
        │   └── handler.py              ← AuditACRHandler — 8-artifact Merkle ACR, WORM lock
        └── api_gateway/
            ├── app.py                  ← FastAPI port 8021, 7 routes
            ├── auth.py
            └── models.py               ← ExecuteRequest, ReconcileRequest, IssueACRRequest…
```

---

## Database Changes (migration 0005)

**Files:**
- `backend/alembic/migrations/versions/0005_sc003_shipment_events.py`
- `backend/alembic/migrations/versions/sc003_shipment_events.sql`

**New columns on `cases`:**

| Column | Type | Notes |
|--------|------|-------|
| `shipment_reference` | TEXT | carrier AWB / tracking number |
| `committed_eta` | TIMESTAMPTZ | SLA-promised delivery time |
| `actual_delivery` | TIMESTAMPTZ | actual carrier-reported delivery |
| `sla_breach_hours` | NUMERIC(10,4) | computed breach duration |
| `sla_penalty_amount` | NUMERIC(18,4) | computed penalty (capped) |

**New table `shipment_events`** — append-only carrier event stream (NEVER UPDATE or DELETE):

```sql
CREATE TABLE shipment_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id),
    case_id          UUID NOT NULL REFERENCES cases(id),
    event_type       TEXT NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL,
    location         TEXT,
    carrier_id       TEXT,
    raw_payload      JSONB,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

**Updated DB constraints:**
- `cases_case_type_check` — extended to include `SHIPMENT_EXCEPTION`
- `chk_cases_subject` — extended with SHIPMENT_EXCEPTION branch (allows `invoice_id=NULL`, `claim_id=NULL`)
- Partial unique index `uq_cases_tenant_shipment` on `(tenant_id, shipment_reference) WHERE sla_breach_hours IS NOT NULL`

Apply: `alembic upgrade head`

---

## Gateway API Routes (port 8020, `/v1/` prefix)

| Method | Route | What it does |
|--------|-------|-------------|
| GET  | `/health` | `{"status":"ok","service":"sc003-gateway"}` |
| POST | `/shipment-exceptions/submit` | Full pipeline: ingest → canonical → case → evidence + reasoning (background thread) |
| GET  | `/shipment-exceptions` | Paginated list (`state`, `page`, `page_size` params) |
| GET  | `/shipment-exceptions/{id}` | Single exception with breach/penalty/confidence |
| GET  | `/shipment-exceptions/{id}/finding` | AI confidence + rule trace |
| GET  | `/shipment-exceptions/{id}/events` | Case FSM audit trail (append-only) |
| GET  | `/shipment-exceptions/{id}/shipment-events` | Carrier event stream |
| POST | `/shipment-exceptions/{id}/propose` | Analyst proposes SLA credit |
| POST | `/shipment-exceptions/{id}/decide` | Manager approves/rejects (SoD enforced) |

---

## Execution Gateway API Routes (port 8021, `/v1/` prefix)

| Method | Route | What it does |
|--------|-------|-------------|
| GET  | `/health` | `{"status":"ok","service":"sc003-execution"}` |
| POST | `/execute` | 8-gate check → action `ISSUE_SLA_CREDIT` → write execution_envelopes |
| POST | `/reconcile` | Commitment Match: committed_eta vs actual_delivery → reconciliations |
| GET  | `/cases/{id}/variances` | Reconciliation variance records |
| POST | `/cases/{id}/variances/{vid}/resolve` | Resolve or waive OPEN variance |
| POST | `/cases/{id}/acr` | Issue 8-artifact Merkle ACR (WORM-locked, irreversible) |
| GET  | `/cases/{id}/acr` | Fetch ACR record |

---

## Frontend Pages (React 18 + TypeScript)

| File | Route | Purpose |
|------|-------|---------|
| `src/features/exceptions/Exceptions.tsx` | `/exceptions` | List with state filter tabs, breach badge, penalty amount |
| `src/features/exceptions/NewException.tsx` | `/exceptions/new` | Form with live breach hours + penalty amount preview |
| `src/features/exceptions/ExceptionDetail.tsx` | `/exceptions/:id` | 4 KPI tiles · event timeline · Agent Authority Zone · Governed Execution Zone · ACR viewer |

**API clients wired in `client.ts`:**
```typescript
apiException  → Vite proxy /excapi  → port 8020 (gateway)
apiException4 → Vite proxy /excapi4 → port 8021 (execution)
```

**Env vars in `.env.local`:**
```
VITE_API_EXC_BASE=/excapi
VITE_API_EXC4_BASE=/excapi4
```

**Sidebar nav:** OPERATIONS group → "Shipment Exceptions" + "Report Exception"

---

## 5 Evidence Artifact Types

| # | Artifact type | Content |
|---|--------------|---------|
| 1 | `source_record` | SHA-256 of raw ingestion payload |
| 2 | `canonical_shipment_exception` | canonical_hash from canonical_shipment_exceptions |
| 3 | `sla_contract_clause` | SLA terms (rate, cap, currency) |
| 4 | `breach_calculation` | breach_hours, penalty_amount |
| 5 | `rule_trace` | confidence, rule weights |

---

## Running Locally

### Apply migration first
```powershell
alembic upgrade head
```

### Gateway (port 8020)
```powershell
cd backend\slices\sc-003-shipment-exception\spine\gateway
..\..\..\..\venv\Scripts\activate
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:ZOIKO_DEV_MODE = "true"
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8020
```

### Execution (port 8021)
```powershell
cd backend\slices\sc-003-shipment-exception\spine\execution
..\..\..\..\venv\Scripts\activate
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:ZOIKO_DEV_MODE = "true"
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn services.api_gateway.app:app --reload --host 0.0.0.0 --port 8021
```

### Verify
```powershell
curl http://localhost:8020/health
curl http://localhost:8020/docs    # Swagger UI — all 9 gateway routes
curl http://localhost:8021/health
curl http://localhost:8021/docs    # Swagger UI — all 7 execution routes
```

---

## Append-Only Tables

`shipment_events` is append-only — only INSERT is permitted.  
Global append-only constraint also applies: `lineage_records`, `case_events`, `evidence_items`, `audit_worm_index`.

---

## SoD Rule

```python
if actor_sub == task["proposer_sub"]:
    raise ValueError(
        f"Separation of Duties violation: actor_sub '{actor_sub}' "
        f"cannot be the same as proposer_sub '{task['proposer_sub']}'"
    )
```

This check fires in `GovernanceHandler.decide()` BEFORE any DB write.

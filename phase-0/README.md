# Zoiko AI Logistics — SC-001 Freight Dispute Resolution

A cryptographically auditable freight dispute resolution system.
When a carrier overcharges a shipper, this system detects it, gets two humans to approve a recovery, executes it, and produces an **Action Certification Record (ACR)** that any external auditor can verify offline — zero access to Zoiko systems required.

---

## The SC-001 Scenario

| Field | Value |
|-------|-------|
| Route | Dallas (DAL) → Atlanta (ATL) |
| Carrier | DHL |
| DHL Billed | **$220.00** (fuel $120 + accessorial $100) |
| Contract Allows | **$120.00** (fuel only) |
| Overcharge | **$100.00** (accessorial — not authorized) |
| AI Confidence | **96%** |
| Result | $100 recovered with tamper-proof audit trail |

---

## Quick Start

### 1. Install dependencies
```bash
py -3.13 -m pip install -e "packages/zoiko-common[dev]"
py -3.13 -m pip install streamlit psycopg2-binary
```

### 2. Start PostgreSQL and set up the database
```bash
# Create the database
psql -U postgres -c "CREATE DATABASE zoiko;"

# Run migrations (creates all 26 tables)
cd db
set DB_URL=postgresql://postgres:zoiko123@localhost/zoiko
py -3.13 -m alembic -c alembic.ini upgrade head

# Seed SC-001 demo data
cd ..
set DB_URL=postgresql://postgres:zoiko123@localhost/zoiko
py -3.13 scripts/seed_dummy_data.py
```

### 3. Launch the dashboard
```bash
set DB_URL=postgresql://postgres:zoiko123@localhost/zoiko
streamlit run dashboard.py
```
Opens at `http://localhost:8501`

### 4. Run CI gates
```bash
# Gate 1: JCS RFC 8785 vectors (hard block)
py -3.13 -m pytest packages/zoiko-common/tests -m jcs_vector -v

# Gate 2: Merkle tree vectors (hard block)
py -3.13 -m pytest packages/zoiko-common/tests -m merkle_vector -v

# Gate 3: Full suite + 80% coverage
py -3.13 -m pytest packages/zoiko-common/tests --cov=zoiko_common --cov-fail-under=80

# Gate 4: Tenant isolation fuzzer
py -3.13 scripts/tenant_fuzzer.py
```

### 5. Run the SC-001 live demo (terminal)
```bash
set PYTHONIOENCODING=utf-8
py -3.13 scripts/demo_sc001.py
```

---

## How the System Works

```
Carrier Invoice Arrives
        │
        ▼
  JCS Canonicalize  ──  RFC 8785, byte-identical on any machine
        │
        ▼
  SHA-256 Hash  ──  domain tag prevents cross-type confusion
        │
        ▼
  Ed25519 Sign  ──  LocalEd25519 (dev) / GCP KMS HSM (prod)
        │
        ▼
  PostgreSQL  ──  source_records + outbox (single transaction)
        │
        ▼
  AI Analysis  ──  confidence=0.96, accessorial=OVERCHARGE
        │
        ▼
  Analyst Signs  ──  Human 1 proposes recovery
        │
        ▼
  Manager Approves  ──  Human 2 signs (SoD enforced: must be different person)
        │
        ▼
  Governance Token  ──  EXECUTE scope, 24h expiry
        │
        ▼
  8-Gate Gateway  ──  all 8 gates PASS → token consumed atomically
        │
        ▼
  Connector  ──  DHL-CONNECTOR issues credit
        │
        ▼
  ACR Issued  ──  8-artifact Merkle tree, WORM-locked, offline verifiable
```

---

## Dashboard Pages

| Page | Purpose |
|------|---------|
| 🏠 Overview | Live metrics, SC-001 story, confidence formula |
| 📋 Case Tracker | All cases, status badges, AI findings, Merkle roots |
| ➕ New Case | Register tenant + submit invoice (full UI workflow) |
| 👤 Analyst Review | Human 1 reviews AI finding and proposes recovery |
| ✅ Manager Approval | Human 2 signs off — SoD violation blocked automatically |
| ⚡ Execute Recovery | 8-gate gateway executes, ACR issued, case closed |
| 🔐 Crypto & Audit | JCS live demo, domain hash, Merkle tree, tamper detection |
| 📖 Phase Roadmap | 6 phases, critical path, 9 key rules |
| 🗄️ Database Explorer | Browse all 26 tables grouped by domain |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Services | FastAPI, Python 3.12+ |
| Dashboard (Phase 0) | Streamlit |
| Frontend (Phase 5) | React + Vite + TypeScript + shadcn/ui |
| Messaging | Apache Kafka (GKE/Strimzi) |
| Database | PostgreSQL 15 (Cloud SQL) |
| Cache | Redis 7 (Memorystore) |
| Signing Keys | GCP Cloud KMS (HSM, Ed25519) |
| Infra | Cloud Run, Terraform, GKE |
| CI | GitHub Actions |
| Policy | OPA (Rego) |

---

## The 26 Database Tables

All tables have **RLS ENABLED + FORCED**. Tables marked APPEND-ONLY never receive UPDATE or DELETE.

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

* = APPEND-ONLY
```

---

## 6 Delivery Phases

| Phase | Timeline | Status | What Gets Built |
|-------|----------|--------|-----------------|
| **P0** | Wk 1-4 | ✅ DONE | Crypto foundation, 26 DB tables, CI pipeline, Streamlit dashboard |
| **P1** | Wk 5-6 | 🔄 NEXT | KMS key hierarchy, OIDC middleware, Kafka on GKE, OPA scaffold |
| **P2** | Wk 7-10 | ⏳ | api-gateway, ingestion, validation, canonical-truth, case-orchestration |
| **P3** | Wk 11-14 | ⏳ | evidence, reasoning, governance, token services |
| **P4** | Wk 15-18 | ⏳ | execution-gateway (8-gate), connector-hub, reconciliation, ACR |
| **P5** | Wk 19-22 | ⏳ | React dashboard, 30-test hardening, load test, release |

---

## Key Rules (Non-Negotiable)

1. **JCS vectors 100% green** before any service code — hard CI block
2. **Hash BEFORE encrypt** — canonical_hash computed before KMS encryption
3. **RLS on all tenant tables** — no exceptions, no retrofitting
4. **APPEND-ONLY tables** — never UPDATE or DELETE lineage_records, case_events, evidence_items, audit_worm_index
5. **OPA fail-closed** — if OPA unreachable → 503, never permit
6. **SoD enforced** — proposer_sub must differ from actor_sub
7. **8-gate execution** — all gates pass before money moves, token consumed atomically
8. **WORM bucket** — is_locked=true is irreversible, 7-year retention
9. **Idempotency + Tenant headers** — required on every state-changing API

---

## Confidence Formula (SC-001)

```
fuel_charge_confidence    = 1.00  (exact contract match: $120 == $120)
accessorial_confidence    = 0.92  (authorized charge lookup: $0 contract vs $100 billed)
combined_confidence       = 0.96  (weighted average per rule_trace)
```

This formula is **deterministic** — any reasoning service must reproduce exactly 0.96.

---

## Environment Setup

| Env | GCP Project | KMS | Kafka | Cloud SQL |
|-----|-------------|-----|-------|-----------|
| dev | zoiko-logistics-dev | SOFTWARE key | local/mock | single zone |
| staging | zoiko-logistics-staging | HSM | Strimzi | HA regional |
| prod | zoiko-logistics-prod | HSM | Strimzi | HA regional |

> **Never use SOFTWARE KMS keys in staging or prod.**
> **WORM bucket retention = 7 years (220903200 seconds), is_locked=true.**

---

## Project Structure

```
zoiko-logistics/
├── packages/zoiko-common/     # Shared crypto, auth, Kafka, idempotency
│   └── zoiko_common/
│       ├── crypto/            # jcs.py, merkle.py, signing.py
│       ├── auth/              # OIDC JWT claims + tenant binding
│       ├── idempotency/       # Redis idempotency store
│       └── kafka/             # Topic registry (17 topics)
├── services/                  # 14 FastAPI microservices (Phase 2+)
├── db/
│   └── migrations/versions/   # 0001_p0_all_25_tables.py
├── kafka/schemas/topics.yaml  # 17 Strimzi KafkaTopic definitions
├── terraform/environments/    # dev / staging / prod
├── opa/policies/              # Rego policy bundles (Phase 1)
├── scripts/
│   ├── demo_sc001.py          # Live 8-step SC-001 demo
│   ├── seed_dummy_data.py     # Seed all 26 tables with SC-001 data
│   └── tenant_fuzzer.py       # CI gate: tenant isolation checks
├── dashboard.py               # Streamlit Phase 0 dashboard
├── .github/workflows/ci.yml   # CI pipeline (5 gates)
├── CLAUDE.md                  # Full project guide for Claude Code
└── README.md                  # This file
```

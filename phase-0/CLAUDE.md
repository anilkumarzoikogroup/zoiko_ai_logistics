# Zoiko AI Logistics — SC-001 Project Guide

## What This Project Is

A cryptographically auditable freight dispute resolution system.
When a carrier overcharges a shipper, this system detects it, gets two humans to approve
a recovery, executes it, and produces an Action Certification Record (ACR) that any
external auditor can verify offline — zero access to Zoiko systems required.

**SC-001 scenario:** Dallas→Atlanta shipment. DHL bills $220. Contract allows $120.
Overcharge = $100. This system recovers that $100 with a tamper-proof audit trail.

---

## Tech Stack

| Layer        | Technology                        |
|--------------|-----------------------------------|
| API services | FastAPI, Python 3.12+             |
| Frontend     | React + Vite + TypeScript + shadcn/ui |
| Messaging    | Apache Kafka (GKE/Strimzi)        |
| Database     | PostgreSQL 15 (Cloud SQL)         |
| Cache        | Redis 7 (Memorystore)             |
| Signing keys | GCP Cloud KMS (HSM, Ed25519)      |
| Infra        | Cloud Run, Terraform, GKE         |
| CI           | GitHub Actions                    |
| Policy       | OPA (Rego)                        |

---

## Monorepo Layout

```
zoiko-logistics/
├── packages/
│   └── zoiko-common/          # Shared crypto, auth, Kafka, idempotency
│       └── zoiko_common/
│           ├── crypto/
│           │   ├── jcs.py     # RFC 8785 JCS canonicalization (CI hard gate)
│           │   ├── merkle.py  # Domain-separated Merkle tree
│           │   └── signing.py # Ed25519 / GCP KMS signing
│           ├── auth/          # OIDC JWT claims + tenant binding
│           ├── idempotency/   # Redis idempotency store
│           ├── kafka/         # Topic registry (17 topics)
│           └── observability/ # structlog + OTel
├── services/                  # 14 FastAPI microservices (Phase 2+)
├── frontend/                  # React dashboard (Phase 5)
├── db/
│   ├── alembic.ini
│   └── migrations/
│       └── versions/
│           └── 0001_p0_all_25_tables.py   # ALL 25 tables in one migration
├── terraform/
│   └── environments/
│       ├── dev/main.tf        # GCP dev: VPC, KMS, Cloud SQL, Redis
│       ├── staging/main.tf
│       └── prod/main.tf
├── kafka/
│   └── schemas/topics.yaml    # All 17 Strimzi KafkaTopic definitions
├── opa/policies/              # Rego policy bundles (Phase 1)
├── scripts/
│   ├── tenant_fuzzer.py       # CI gate: tenant isolation checks
│   └── demo_sc001.py          # Live SC-001 end-to-end demo
└── .github/workflows/ci.yml   # CI pipeline
```

---

## How to Run Everything

### Install
```bash
# From zoiko-logistics/ directory
py -3.13 -m pip install -e "packages/zoiko-common[dev]"
```

### Run CI gates (must all pass before any service code)
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

### Run the SC-001 live demo
```bash
set PYTHONIOENCODING=utf-8
py -3.13 scripts/demo_sc001.py
```

### Apply database migrations (PostgreSQL must be running)
```bash
cd db
set DB_URL=postgresql://postgres:yourpassword@localhost/zoiko
py -3.13 -m alembic -c alembic.ini upgrade head
```

### Seed dummy data (after migration)
```bash
cd ..   # back to zoiko-logistics/
set DB_URL=postgresql://postgres:zoiko123@localhost/zoiko
py -3.13 scripts/seed_dummy_data.py
```

### Run the Streamlit dashboard (Phase 0 visual UI)
```bash
# From zoiko-logistics/ directory
set DB_URL=postgresql://postgres:zoiko123@localhost/zoiko
streamlit run dashboard.py
```

Dashboard pages:
- 🏠 Overview          — Live metrics, SC-001 story, confidence formula
- 📋 Case Tracker      — All cases with status, AI finding, Merkle root
- ➕ New Case          — Register tenant + submit invoice (end-to-end UI)
- 👤 Analyst Review    — Human 1 signs off on proposal
- ✅ Manager Approval  — Human 2 approves (SoD enforced)
- ⚡ Execute Recovery  — 8-gate gateway runs, ACR issued
- 🔐 Crypto & Audit    — JCS demo, domain hash demo, live tamper detection
- 📖 Phase Roadmap     — All 6 phases, critical path, 9 key rules
- 🗄️ Database Explorer — Browse all 26 tables grouped by domain

---

## 6 Delivery Phases

| Phase | Sprints | What gets built |
|-------|---------|-----------------|
| **P0** (DONE) | S1-S2, Wk 1-4  | zoiko-common crypto, 25 DB tables, CI pipeline |
| **P1**        | S3, Wk 5-6     | KMS key hierarchy, OIDC middleware, Kafka on GKE, OPA scaffold |
| **P2**        | S4-S5, Wk 7-10 | api-gateway, ingestion, validation, canonical-truth, case-orchestration |
| **P3**        | S6-S7, Wk 11-14| evidence, reasoning, governance, token services |
| **P4**        | S8-S10, Wk 15-18| execution-gateway (8-gate), connector-hub, reconciliation, ACR |
| **P5**        | S11-S12, Wk 19-22| React dashboard, 30-test hardening matrix, load test, release |

---

## The 25 Database Tables

All created in migration `0001`. All tenant-scoped tables have RLS ENABLED + FORCED.

```
TENANT:         tenants, tenant_keys
INGESTION:      source_records, lineage_records          (lineage is APPEND-ONLY)
VALIDATION:     validation_results
CANONICAL:      canonical_invoices, canonical_shipments, contract_rates
CASE:           cases, case_events                       (case_events is APPEND-ONLY)
EVIDENCE:       evidence_bundles, evidence_items         (evidence_items is APPEND-ONLY)
REASONING:      findings, decision_proposals
GOVERNANCE:     policy_bundles, governance_decisions, approval_tasks
TOKEN:          governance_tokens
EXECUTION:      idempotency_keys, execution_envelopes, connector_responses
RECONCILIATION: reconciliations, outcomes
AUDIT:          action_certification_records
INFRASTRUCTURE: outbox, audit_worm_index                 (audit_worm_index is APPEND-ONLY)
```

---

## Critical Path

```
JCS correct → Merkle correct → Signing works → Outbox relay → Ingestion hash
→ Evidence bundle → ACR Merkle root → Offline verifier PASS
```

If JCS is wrong, every hash, signature, and Merkle root in the system is wrong.
There is no late-stage recovery. This is why JCS vectors are a hard CI block.

---

## Key Rules (Non-Negotiable)

1. **JCS test vectors must be 100% green before any service code** — hard CI block.
2. **Hash BEFORE encrypt** — canonical_hash is computed before KMS encryption.
3. **RLS on all tenant tables** — no exceptions, no retrofitting.
4. **APPEND-ONLY tables** — lineage_records, case_events, evidence_items, audit_worm_index.
   Never issue UPDATE or DELETE against these.
5. **OPA fail-closed** — if OPA is unreachable → 503. Never permit on unavailability.
6. **SoD** — proposer_sub must differ from actor_sub in approval_tasks.
7. **8-gate execution** — all 8 gates must pass before money moves. Token consumed atomically.
8. **WORM bucket** — is_locked=true is irreversible. Provision staging first.
9. **Every state-changing API requires** — Idempotency-Key header + X-Tenant-ID header.

---

## SC-001 Confidence Formula

```
fuel_charge_confidence    = 1.00  (exact contract match: $120 == $120)
accessorial_confidence    = 0.92  (authorized charge lookup)
combined_confidence       = 0.96  (weighted average per rule_trace)
```

This formula is deterministic. Any reasoning service must reproduce exactly 0.96.

---

## Ingestion Write Pattern (exact order, do not change)

```
1. JCS canonicalize the payload
2. SHA-256 hash with domain tag  (BEFORE encryption)
3. AES-256-GCM encrypt via KMS tenant DEK
4. INSERT source_records + INSERT outbox  (single DB transaction)
5. Redis idempotency key stored  (AFTER commit)
```

Step 5 after commit is intentional — crash between 4 and 5 is safe, next attempt
will find the DB record and recover.

---

## Execution Gateway 8 Gates

All must return PASS for a 202 response. Checked in this order:

1. Token signature valid
2. Token not expired
3. Tenant binding hash matches
4. Token scope matches action
5. Sanctions screening CLEAR
6. FX lock obtained
7. Connector certification = CERTIFIED
8. Idempotency key not already COMPLETE

Token marked CONSUMED atomically before dispatch — intentional, no replay possible.

---

## Environment Setup

| Env     | GCP Project              | KMS          | Kafka     | Cloud SQL  |
|---------|--------------------------|--------------|-----------|------------|
| dev     | zoiko-logistics-dev      | SOFTWARE key | local/mock| single zone|
| staging | zoiko-logistics-staging  | HSM          | Strimzi   | HA regional|
| prod    | zoiko-logistics-prod     | HSM          | Strimzi   | HA regional|

**Never use SOFTWARE KMS keys in staging or prod.**
**WORM bucket retention = 7 years (220903200 seconds), is_locked=true.**

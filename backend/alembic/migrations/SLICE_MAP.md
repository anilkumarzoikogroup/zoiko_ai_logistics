# Migration → Slice Map

Alembic's revision chain (`0001`–`0043`) cannot be reordered or renamed without rebuilding
history against a live database — so this file documents the grouping instead of moving
files. It also corrects a framing mistake it's easy to make by skimming filenames: **most
of these migrations are platform spine, not SC-001's migrations.** SC-001 was the first
consumer to exercise them, but the tables themselves (cases, evidence, governance tokens,
execution envelopes, reconciliation, ACR, recovery, C07 data-governance) serve every slice
that follows — exactly the "lift the spine, don't rebuild it" principle from the Engineering
Build Map (§11 Repositioning Board, §18 Doctrine).

Only **0041–0043** are genuinely slice-specific today — the migrations that lifted `cases`
to support a claim as well as an invoice (SC-002).

## Platform spine (shared by every slice, including future SC-003–007)

| Range | What it added | Domain |
|---|---|---|
| `0001` | All 25 foundational tables, RLS | Everything |
| `0002` | Contract rates, lane hash | Commercial Reference Data |
| `0003`–`0004` | FSM constraints, OCC versioning on `cases` | Case Orchestration |
| `0005` | Agentic intelligence fields | Reasoning |
| `0006` | Doc corrections | — |
| `0007`–`0008` | Audit chains, certification | ACR / Audit |
| `0009` | Evidence completeness | Evidence |
| `0010`, `0013`, `0017` | Auth, enterprise auth, user titles | Identity/Access |
| `0011`–`0012` | Findings AI fields | Reasoning |
| `0014` | Execution envelopes v2 | Execution Gateway |
| `0015`–`0016` | Canonical invoice fields (SC-001-shaped today, but the canonical-truth *framework* is shared — see `0019`) | Canonical Truth |
| `0018` | Carriers table | Canonical Truth |
| `0019` | All missing domain tables (identity, ingestion, canonical truth, case mgmt, decision, governance, execution, evaluation) | Everything |
| `0020`–`0022` | Source record tier-0, batch/lineage v2, webhook signing configs | Source Ingestion |
| `0023` | Case lifecycle, decision execution, recovery workflow, ACR closure (Clarification 05) | Case Orchestration / Recovery |
| `0024`–`0025` | Finding hash, canonical shipment uniqueness | Reasoning / Canonical Truth |
| `0026`–`0027` | API keys, notification settings | Identity/Access |
| `0028`–`0029` | Recovery pipeline core schema + dedup indexes (Clarification 06 Slice 1) | Recovery |
| `0030`–`0031` | C07 — residency, retention, legal hold, crypto-shred, archive/restore | Data Governance (cross-cutting, all slices) |
| `0032`–`0035` | Drift fixes to spine tables (dedup index, source record fields, lineage fields) | Source Ingestion / Validation |
| `0036` | Contract rate lineage/versioning, model_calls audit | Commercial Reference Data |
| `0037` | Connector source_type, webhook runs | Connector Hub |
| `0038` | Evidence item signature/kid | Evidence |
| `0039` | Transparency log over ACRs | ACR |
| `0040` | Witness packs | Commercial Reference Data / Evidence |

## SC-002 — Carrier Claim (genuinely slice-specific)

| Migration | What it added |
|---|---|
| `0041_sc002_carrier_claim_lift` | Lifted `cases` to carry either an invoice or a claim: nullable `invoice_id`, new `claim_id` + `case_type` discriminator, `chk_cases_subject` check constraint, `claims.status` lifecycle check |
| `0042_claims_reference_column` | `claims.claim_reference` |
| `0043_claim_lines` | New `claim_lines` table for multi-line claims |

## SC-003 through SC-007 — no migrations yet

Nothing has been built for these slices. When work starts on any of them, the **first**
migration that introduces a genuinely slice-specific table or column should follow this
naming convention so it's identifiable by filename alone, without needing this map:

```
NNNN_sc00X_<short description>.py
```

e.g. `0044_sc003_shipment_events.py`, `0050_sc004_supplier_scores.py`.

Migrations that extend the **shared spine** (even if a particular slice motivated the fix —
like most of `0032`–`0040` above) keep the existing free-form naming with no `sc00X` prefix,
since attributing a spine fix to one slice would misrepresent who it serves. Use the prefix
only when the table/column itself cannot be used by another slice.

# ADR-003: WORM Audit Records for Action Certification

**Status:** Accepted  
**Date:** 2025-01-15  
**Authors:** Zoiko Engineering  

---

## Context

After money moves, we need an immutable record proving:
1. What happened (amount, case, carrier)
2. Who authorised it (analyst + manager identity)
3. That no one altered the record after the fact

Enterprise customers require audit records that cannot be deleted or modified even by database administrators. This is a hard requirement for SOC 2 Type II compliance and carrier dispute resolution proceedings.

## Decision

**ACRs (Action Certification Records) are WORM (Write Once Read Many).**

Two complementary mechanisms:

### 1. Application-layer append-only enforcement

- `audit_worm_index` table: INSERT only, no UPDATE or DELETE code paths anywhere in the codebase
- `action_certification_records.is_locked`: starts `FALSE`, transitions to `TRUE` by the WORM relay after upload to Cloud Storage — this transition is one-way and irreversible
- The application raises `PermissionError` on any attempt to modify a locked record

### 2. Cryptographic integrity (offline verifiable)

- The ACR is a Merkle tree over 8 artifacts:
  1. `source_record_hash` — SHA-256 of canonical invoice bytes
  2. `canonical_invoice_hash`
  3. `evidence_bundle_hash` — Merkle root of evidence items
  4. `finding_hash` — reasoning output hash
  5. `proposal_hash`
  6. `governance_decision_hash`
  7. `token_hash`
  8. `envelope_hash` — execution outcome

- The Merkle root is signed with Ed25519 (tenant-bound key)
- The ACR verify bundle is uploaded to Cloud Storage (WORM bucket — GCS Object Retention Policy)
- Any modification to any of the 8 artifacts changes the Merkle root → breaks the signature

### 3. Offline verifier

- `verify.sh` is included in `acr_verify_<case_id>.zip` for carrier/auditor use
- `src/utils/acrVerifier.ts` provides browser-side Merkle root verification via Web Crypto API

## Append-only tables (never UPDATE or DELETE)

```
lineage_records      — ingestion provenance
case_events          — FSM audit trail
evidence_items       — evidence bundle contents
audit_worm_index     — ACR WORM upload index
```

## Consequences

**Positive:**
- Immutable audit trail satisfies SOC 2 Type II, ISO 27001, and GDPR Article 5(f) requirements
- Carrier disputes can be resolved by presenting the ACR zip — no backend access needed
- Merkle proofs allow selective disclosure (prove one artifact without revealing others)

**Negative:**
- Once `is_locked=TRUE`, correcting an erroneous ACR requires issuing a new ACR with a supersedes link — no in-place correction
- Cloud Storage WORM retention adds cost (minimum 7-year retention for Indian regulatory compliance)

## GCP WORM configuration (production)

```hcl
resource "google_storage_bucket" "acr_worm" {
  name                        = "zoiko-acr-worm-${var.env}"
  retention_policy {
    is_locked        = true
    retention_period = 220752000  # 7 years in seconds
  }
  uniform_bucket_level_access = true
}
```

In dev/test: `is_locked` flag on the DB row simulates WORM semantics; no actual GCS bucket required.

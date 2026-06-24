# SC-002 (Carrier Claim) — Schema Ownership

This is a reference snapshot, not an executable migration. The real, authoritative
migration chain lives at `backend/alembic/migrations/` (one shared chain — see
`SLICE_MAP.md` there for why it can't be split per slice on a live database).

This file lists exactly the tables and columns that exist **only because of SC-002**.
Everything else SC-002's code touches (`cases`, `evidence_bundles`, `findings`,
`governance_tokens`, `execution_envelopes`, `action_certification_records`, `tenants`,
`carriers`, `connectors`, etc.) is shared platform spine used by every slice — see
`backend/alembic/migrations/SLICE_MAP.md` for that side of the picture.

## Tables/columns exclusive to SC-002

### `cases` (shared table — these specific columns are SC-002's lift)
- `invoice_id` made nullable, `+claim_id` (FK → `claims.id`), `+case_type` discriminator
  (default `'INVOICE_OVERCHARGE'`), `chk_cases_subject` check constraint —
  `0041_sc002_carrier_claim_lift.py`

### `claims`
- Table itself first created (generic placeholder) in `0019_domain_tables.py`
- `+source_record_id`, `+carrier_id`, `+claim_hash`, `chk_claims_status` constraint —
  `0041_sc002_carrier_claim_lift.py`
- `+claim_reference` — `0042_claims_reference_column.py`

### `claim_lines`
- Created in `0043_claim_lines.py` — multi-line claim breakdown

## What's deliberately NOT here

`cases`'s base columns (id, tenant_id, state, opened_at, etc.), `evidence_bundles`,
`evidence_items`, `findings`, `decision_proposals`, `governance_tokens`,
`execution_envelopes`, `action_certification_records`, `tenants`, `carriers`,
`connectors`, `model_calls`, the recovery pipeline tables, and the C07 data-governance
tables — all shared, all created once for every slice, none of them SC-002-specific.

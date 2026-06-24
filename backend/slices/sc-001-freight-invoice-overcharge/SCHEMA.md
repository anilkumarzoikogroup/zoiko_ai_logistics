# SC-001 (Freight Invoice Overcharge) — Schema Ownership

This is a reference snapshot, not an executable migration. The real, authoritative
migration chain lives at `backend/alembic/migrations/` (one shared chain — see
`SLICE_MAP.md` there for why it can't be split per slice on a live database).

This file lists exactly the tables and columns that exist **only because of SC-001**.
Everything else SC-001's code touches (`cases`, `evidence_bundles`, `findings`,
`governance_tokens`, `execution_envelopes`, `action_certification_records`, `tenants`,
`carriers`, `connectors`, etc.) is shared platform spine used by every slice — see
`backend/alembic/migrations/SLICE_MAP.md` for that side of the picture.

## Tables exclusive to SC-001

### `canonical_invoices`
- Created in `0001_p0_all_25_tables.py`
- `+predecessor_version_hash` — `0015_canonical_invoice_predecessor_hash.py`
- `+invoice_date`, `+transport_mode`, `+charge_lines` — `0016_canonical_invoice_extended_fields.py`

### `canonical_shipments`
- Created in `0001_p0_all_25_tables.py`
- `+mode`, `+equipment_type` — `0016_canonical_invoice_extended_fields.py`
- Unique constraint on `(invoice_id)` — `0025_canonical_shipments_unique_invoice.py`

### `contract_rates`
- Created in `0001_p0_all_25_tables.py`
- `+lane_hash`, `+base_rate`, `+effective_from`, `+effective_to`,
  `+governing_jurisdiction`, `+payload_hash` — `0002_contract_rates_lane_hash.py`
- `+version`, `+supersedes_id`, `+superseded_at`, `+source_document_id` —
  `0036_contract_rates_lineage_versioning.py`

## Shared-table seed data specific to SC-001

`validation_rule_sets` (a shared table) has one seeded row, `carrier_invoice_validation`
(domain `INVOICE`), inserted by `0020_source_record_tier0.py` and re-affirmed by
`0033_reapply_0020_source_record_fields.py`. SC-002 has no validation step and never
references this rule set — it's effectively SC-001-only data living in a shared table.

## What's deliberately NOT here

`cases`, `evidence_bundles`, `evidence_items`, `findings`, `decision_proposals`,
`governance_tokens`, `execution_envelopes`, `action_certification_records`, `tenants`,
`carriers`, `connectors`, `model_calls`, the recovery pipeline tables (`expected_recoveries`,
`recovery_instruments`, etc.), and the C07 data-governance tables — all shared, all created
once for every slice. SC-001 was simply the first consumer to exercise them.

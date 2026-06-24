# SC-005 — Accessorial Charge Dispute

**Status: scaffolded only.** No backend service exists for this slice yet — there is no
ingestion handler, canonical-truth writer, rule bundle, or route surface for accessorial
disputes anywhere in this codebase. This folder is a placeholder until that work starts.

## What this slice would represent

A carrier bills an accessorial charge (detention, demurrage, residential delivery,
liftgate, etc.) that the contract doesn't support or caps lower than billed. Closely
related to SC-001 (also a billing-line overcharge), but the validation rule set is
accessorial-specific rather than base-rate-specific — distinct enough to warrant its own
rule bundle and confidence formula rather than reusing SC-001's.

## What it would newly exercise (per the Build Map's slice-by-slice rollout, §12)

The first slice to validate against a per-accessorial-type cap table rather than a single
contracted base rate — multiple charge lines per invoice, each checked independently.

## Spine reuse — same doctrine as SC-001/SC-002

Everything reusable stays in the shared services, not here:

- Likely reuses `IngestionHandler.ingest_invoice()` / `CanonicalHandler.canonicalize_invoice()`
  directly (an accessorial dispute is still an invoice), with the contract-rate validation
  step (`ValidationHandler.validate()`) gaining accessorial-aware logic.
- `CaseHandler.open_case()`, `AuditACRHandler._collect_artifacts()`, and the reasoning
  case-metadata reader may not need a new `case_type` branch at all if this stays under
  `INVOICE_OVERCHARGE` — to be decided when this slice is actually built.

## What would be genuinely slice-specific (belongs in this folder, once built)

- `rules.py` — the accessorial-cap rule bundle + its deterministic confidence constant.
- `models.py` — request/response models for per-accessorial-type charge validation, if they
  diverge from SC-001's `models.py`.
- `routes_logic.py` — the FastAPI route handler logic specific to this slice, if any.

## Migration naming

Once this slice's first genuinely-specific table is needed, name its migration per
[`../core/db/migrations/SLICE_MAP.md`](../../core/db/migrations/SLICE_MAP.md)'s
`NNNN_sc005_<description>.py` convention.

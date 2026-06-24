# SC-003 — Shipment Exception / SLA Penalty

**Status: scaffolded only.** No backend service exists for this slice yet — there is no
ingestion handler, canonical-truth writer, rule bundle, or route surface for shipment
exceptions anywhere in this codebase. This folder is a placeholder until that work starts.

## What this slice would represent

A shipment misses a contracted SLA (late delivery, missed pickup window, temperature
excursion, etc.) and the contract specifies a penalty the carrier owes back. Same overcharge
recovery shape as SC-001, but the "overcharge" is a penalty clause violation rather than a
rate mismatch.

## What it would newly exercise (per the Build Map's slice-by-slice rollout, §12)

Following SC-001 (invoice overcharge) and SC-002 (carrier claim), SC-003 would be the first
slice to exercise SLA/contract-clause evaluation against shipment milestone events, rather
than a billed amount against a contracted rate.

## Spine reuse — same doctrine as SC-001/SC-002

Everything reusable stays in the shared services, not here:

- `IngestionHandler` gets a new `ingest_shipment_event()` method (or similar) — mirrors
  `.ingest_invoice()` / `.ingest_claim()` exactly, just a different payload shape.
- `CanonicalHandler` gets `canonicalize_shipment_exception()` — same hash/sign/lineage
  pattern as the other two.
- `CaseHandler.open_case()` is already generic on `case_type` — would add a third branch.
- `AuditACRHandler._collect_artifacts()` and `reasoning_svc`'s case-metadata reader would
  each need a third branch alongside the existing `INVOICE_OVERCHARGE` / `CARRIER_CLAIM` ones.

## What would be genuinely slice-specific (belongs in this folder, once built)

- `rules.py` — the SLA-penalty rule bundle + its deterministic confidence constant.
- `models.py` — request/response models shaped around shipment milestones and SLA terms.
- `ingestion.py` / `canonical.py` / `acr_artifacts.py` — the per-slice bodies, once those
  shared methods grow a shipment-exception branch.
- `routes_logic.py` — the FastAPI route handler logic specific to this slice.

## Migration naming

Once this slice's first genuinely-specific table is needed, name its migration per
[`../core/db/migrations/SLICE_MAP.md`](../../core/db/migrations/SLICE_MAP.md)'s
`NNNN_sc003_<description>.py` convention.

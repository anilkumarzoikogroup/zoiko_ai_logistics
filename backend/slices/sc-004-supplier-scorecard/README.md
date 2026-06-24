# SC-004 — Supplier Performance Scorecard

**Status: scaffolded only.** No backend service exists for this slice yet — there is no
ingestion handler, canonical-truth writer, rule bundle, or route surface for supplier
scorecards anywhere in this codebase. This folder is a placeholder until that work starts.

## What this slice would represent

Aggregated supplier/carrier performance metrics (on-time rate, damage rate, claim
frequency, dispute-resolution turnaround) rolled up into a scorecard that can trigger a
recovery case when performance falls below a contracted threshold — e.g. a volume rebate
clawback or a service-credit claim.

## What it would newly exercise (per the Build Map's slice-by-slice rollout, §12)

The first slice driven by an aggregate/rollup trigger rather than a single transaction
(invoice, claim, shipment event) — the case-opening trigger would be a scheduled
scorecard computation crossing a threshold, not a single ingested record.

## Spine reuse — same doctrine as SC-001/SC-002

Everything reusable stays in the shared services, not here:

- `IngestionHandler` gets an `ingest_scorecard_period()` method (or similar) for the
  aggregated metrics snapshot that triggers the case.
- `CanonicalHandler` gets a `canonicalize_scorecard()` counterpart.
- `CaseHandler.open_case()` would add a fourth `case_type` branch.
- `AuditACRHandler._collect_artifacts()` and the reasoning case-metadata reader would each
  need a fourth branch.

## What would be genuinely slice-specific (belongs in this folder, once built)

- `rules.py` — the scorecard-threshold rule bundle + its deterministic confidence constant.
- `models.py` — request/response models shaped around scorecard periods and metrics.
- `ingestion.py` / `canonical.py` / `acr_artifacts.py` — the per-slice bodies.
- `routes_logic.py` — the FastAPI route handler logic specific to this slice.

## Migration naming

Once this slice's first genuinely-specific table is needed, name its migration per
[`../core/db/migrations/SLICE_MAP.md`](../../core/db/migrations/SLICE_MAP.md)'s
`NNNN_sc004_<description>.py` convention.

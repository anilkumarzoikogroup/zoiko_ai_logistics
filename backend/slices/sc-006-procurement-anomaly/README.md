# SC-006 — Procurement Anomaly Detection

**Status: scaffolded only.** No backend service exists for this slice yet — there is no
ingestion handler, canonical-truth writer, rule bundle, or route surface for procurement
anomalies anywhere in this codebase. This folder is a placeholder until that work starts.

## What this slice would represent

A purchase order or invoice that deviates from expected procurement patterns — price
creep against historical baseline, duplicate payment, split-PO threshold evasion, or an
unapproved vendor — flagged for recovery or correction before payment, rather than after.

## What it would newly exercise (per the Build Map's slice-by-slice rollout, §12)

The first slice driven by statistical/pattern anomaly detection against a historical
baseline rather than a fixed contracted rate or rule threshold — the case-opening trigger
would be a deviation score, not a direct rule violation.

## Spine reuse — same doctrine as SC-001/SC-002

Everything reusable stays in the shared services, not here:

- `IngestionHandler` gets an `ingest_purchase_order()` (or similar) method.
- `CanonicalHandler` gets a `canonicalize_procurement_record()` counterpart.
- `CaseHandler.open_case()` would add another `case_type` branch.
- `AuditACRHandler._collect_artifacts()` and the reasoning case-metadata reader would each
  need a matching branch.

## What would be genuinely slice-specific (belongs in this folder, once built)

- `rules.py` — the anomaly-scoring rule bundle + its deterministic confidence constant.
- `models.py` — request/response models shaped around PO/anomaly data.
- `ingestion.py` / `canonical.py` / `acr_artifacts.py` — the per-slice bodies.
- `routes_logic.py` — the FastAPI route handler logic specific to this slice.

## Migration naming

Once this slice's first genuinely-specific table is needed, name its migration per
[`../core/db/migrations/SLICE_MAP.md`](../../core/db/migrations/SLICE_MAP.md)'s
`NNNN_sc006_<description>.py` convention.

# SC-007 — Inventory Movement Exception

**Status: scaffolded only.** No backend service exists for this slice yet — there is no
ingestion handler, canonical-truth writer, rule bundle, or route surface for inventory
movement exceptions anywhere in this codebase. This folder is a placeholder until that
work starts.

## What this slice would represent

A discrepancy between expected and actual inventory movement at a warehouse or
distribution point — shortage, damage-in-transit, or miscount against the shipping
manifest — that triggers a recovery claim against the carrier or 3PL responsible for that
leg of the movement.

## What it would newly exercise (per the Build Map's slice-by-slice rollout, §12)

The first slice tied to a physical inventory reconciliation event (manifest vs. received
count) rather than a billing document — the source record would originate from a
warehouse management system feed, not an invoice or claim form.

## Spine reuse — same doctrine as SC-001/SC-002

Everything reusable stays in the shared services, not here:

- `IngestionHandler` gets an `ingest_inventory_movement()` (or similar) method.
- `CanonicalHandler` gets a `canonicalize_inventory_exception()` counterpart.
- `CaseHandler.open_case()` would add another `case_type` branch.
- `AuditACRHandler._collect_artifacts()` and the reasoning case-metadata reader would each
  need a matching branch.

## What would be genuinely slice-specific (belongs in this folder, once built)

- `rules.py` — the shortage/damage-threshold rule bundle + its deterministic confidence
  constant.
- `models.py` — request/response models shaped around manifest vs. received-count data.
- `ingestion.py` / `canonical.py` / `acr_artifacts.py` — the per-slice bodies.
- `routes_logic.py` — the FastAPI route handler logic specific to this slice.

## Migration naming

Once this slice's first genuinely-specific table is needed, name its migration per
[`../core/db/migrations/SLICE_MAP.md`](../../core/db/migrations/SLICE_MAP.md)'s
`NNNN_sc007_<description>.py` convention.

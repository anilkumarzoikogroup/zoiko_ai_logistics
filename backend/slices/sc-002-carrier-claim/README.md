# SC-002 — Carrier Claim

**Status: built, live.** Second slice — proves the spine generalizes beyond invoices
(Build Map §12: "claims as first-class objects, not invoice byproducts").

## What actually lives in this folder

Only the parts that are genuinely claim-shaped and don't serve any other slice:

| File | Contents |
|---|---|
| [`claim_rules.py`](claim_rules.py) | `RULES` + `SC002_CONFIDENCE` (= 0.9275, deterministic — liability_acknowledged 0.95×0.55 + amount_within_policy_cap 0.90×0.45). Imported by `backend/governance/services/reasoning_svc/handler.py`. |
| [`claim_models.py`](claim_models.py) | `ClaimLineInput`, `SubmitClaimRequest`, `NegotiateClaimRequest` — re-exported by `backend/gateway/services/api_gateway/models.py` so every existing import elsewhere is unaffected. |
| [`claim_ingestion.py`](claim_ingestion.py) | `ingest_claim()` body — hash-before-encrypt, dedup, sign, lineage. |
| [`claim_canonical.py`](claim_canonical.py) | `canonicalize_claim()` body. |
| [`claim_acr_artifacts.py`](claim_acr_artifacts.py) | ACR artifacts #1/#2 (source-record hash, canonical-claim hash). |
| [`claim_routes_logic.py`](claim_routes_logic.py) | Claims list/detail/lines/negotiate, `run_evidence_and_reasoning_claim()`, the submit/submit-async pipeline runners. |

Files are prefixed `claim_` (not bare `rules.py`/`models.py`/etc.) so this folder and
`sc-001-freight-invoice-overcharge/`'s `invoice_`-prefixed files stay visually distinct
side by side.

## What deliberately stays in the shared services (not duplicated here)

Same reasoning as SC-001's README — these are shared infrastructure, not claim-specific:

- `IngestionHandler.ingest_claim()` (alongside `.ingest_invoice()`) — `backend/gateway/services/ingestion_svc/handler.py`
- `CanonicalHandler.canonicalize_claim()` (alongside `.canonicalize_invoice()`) — `backend/gateway/services/canonical_truth/handler.py`
- `CaseHandler.open_case(claim_id=...)` — generic, shared with SC-001
- The negotiation endpoint, `claim_lines` read/write, and the proposal/decide/tokens/execute/
  variances/acr route handlers in `backend/gateway/services/api_gateway/app.py`
- Tests — `backend/gateway/tests/test_claims_pipeline.py` stays in `backend/gateway/tests/`
  for the same conftest/pytest-config reason as SC-001's test file.

## DB

`claims`, `claim_lines` tables — see
[`../../core/db/migrations/SLICE_MAP.md`](../../core/db/migrations/SLICE_MAP.md) for exactly
which migrations (`0041`–`0043`) are SC-002-specific vs. spine.

## Confidence formula (illustrative bundle, not yet rule-owner-reviewed)

```
SC002_CONFIDENCE = liability_acknowledged(0.95 × 0.55) + amount_within_policy_cap(0.90 × 0.45) = 0.9275
```

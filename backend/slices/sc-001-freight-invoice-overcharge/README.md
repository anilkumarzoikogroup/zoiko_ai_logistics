# SC-001 — Freight Invoice Overcharge

**Status: built, live.** This is the reference slice — the first to exercise the full
platform spine, per the Build Map (§9, §12, §13 acceptance criteria).

## What actually lives in this folder

Only the parts that are genuinely invoice-shaped and don't serve any other slice:

| File | Contents |
|---|---|
| [`invoice_rules.py`](invoice_rules.py) | `RULES` + `SC001_CONFIDENCE` (= 0.96, deterministic — fuel_charge 1.00×0.50 + accessorial 0.92×0.50). Imported by `backend/governance/services/reasoning_svc/handler.py`. |
| [`invoice_models.py`](invoice_models.py) | `InvoiceRequest/Response`, `ValidateRequest/Response`, `CanonicalizeRequest/Response`, `OpenCaseRequest`, `SubmitCaseRequest` — re-exported by `backend/gateway/services/api_gateway/models.py` so every existing import elsewhere is unaffected. |
| [`invoice_ingestion.py`](invoice_ingestion.py) | `ingest_invoice()` body — hash-before-encrypt, dedup, sign, lineage. |
| [`invoice_canonical.py`](invoice_canonical.py) | `canonicalize_invoice()` body. |
| [`invoice_acr_artifacts.py`](invoice_acr_artifacts.py) | ACR artifacts #1/#2 (source-record hash, canonical-invoice hash). |
| [`invoice_routes_logic.py`](invoice_routes_logic.py) | Cases list/detail, validation, canonical-invoice, dispute-letter generator, batch-submit per-file logic, `run_evidence_and_reasoning()`, the submit/submit-async pipeline runners. |
| [`parse_invoice.py`](parse_invoice.py) | The AI/regex invoice-PDF parser behind `POST /ingestion/parse-invoice`. |

Files are prefixed `invoice_` (not bare `rules.py`/`models.py`/etc.) so this folder and
`sc-002-carrier-claim/`'s `claim_`-prefixed files stay visually distinct side by side.

## What deliberately stays in the shared services (not duplicated here)

The methods that *use* invoice data are shared infrastructure with SC-002 (and every
future slice) — splitting them per-slice would mean forking shared DB/hashing/signing
code, which the Build Map explicitly warns against (§11, §18: "platform primitives are
first-class... not invoice services"):

- `IngestionHandler.ingest_invoice()` (alongside `.ingest_claim()`) — `backend/gateway/services/ingestion_svc/handler.py`
- `CanonicalHandler.canonicalize_invoice()` (alongside `.canonicalize_claim()`) — `backend/gateway/services/canonical_truth/handler.py`
- `CaseHandler.open_case()` — generic, takes either `canonical_invoice_id` or `claim_id` — `backend/gateway/services/case_orchestration/handler.py`
- `_read_case_metadata()` — branches on `cases.case_type` — `backend/governance/services/reasoning_svc/tools.py`
- `AuditACRHandler._collect_artifacts()` — branches on `cases.case_type` — `backend/execution/services/audit_acr_svc/handler.py`
- The `/v1/cases/submit`, `/v1/cases/{id}/*` route handlers in `backend/gateway/services/api_gateway/app.py` — these call the shared methods above
- Tests — `backend/gateway/tests/test_api_gateway.py` exercises this slice end-to-end but
  stays in `backend/gateway/tests/` because it's bound to that service's `conftest.py`
  fixtures (`db_url`, `test_tenant`) and `pyproject.toml` pytest config; moving it would
  require duplicating that test infrastructure for no real benefit.

## Confidence formula (must never change)

```
SC001_CONFIDENCE = fuel_charge(1.00 × 0.50) + accessorial(0.92 × 0.50) = 0.96
```

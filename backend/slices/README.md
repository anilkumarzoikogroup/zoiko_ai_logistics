# slices/

This mirrors the `slices/` directory from the Engineering Build Map's Reference
Implementation Repository (§16) — one folder per use case, holding only the parts that are
genuinely specific to that slice (source schema, rule bundle, connector). Everything reusable
(ingestion, canonical truth, evidence, governance, tokens, execution, reconciliation, ACR)
stays in the platform services it already lives in — `backend/gateway`, `backend/governance`,
`backend/execution` — and is *not* duplicated here per-slice.

## Where each slice's code actually lives today

| Slice | Status | Slice folder | What's still in the shared services |
|---|---|---|---|
| SC-001 Freight Invoice Overcharge | Built, live | [`sc-001-freight-invoice-overcharge/`](sc-001-freight-invoice-overcharge/) | `open_case()`, `_read_case_metadata()`, the generic Phase 3-8 route handlers (proposal/decide/tokens/execute/variances/acr), the in-memory job store — shared infra used by both slices |
| SC-002 Carrier Claim | Built, live | [`sc-002-carrier-claim/`](sc-002-carrier-claim/) | same as above |
| SC-003 Shipment Exception / SLA Penalty | Scaffolded only | [`sc-003-shipment-exception/`](sc-003-shipment-exception/) | — |
| SC-004 Supplier Performance Scorecard | Scaffolded only | [`sc-004-supplier-scorecard/`](sc-004-supplier-scorecard/) | — |
| SC-005 Accessorial Charge Dispute | Scaffolded only | [`sc-005-accessorial-dispute/`](sc-005-accessorial-dispute/) | — |
| SC-006 Procurement Anomaly Detection | Scaffolded only | [`sc-006-procurement-anomaly/`](sc-006-procurement-anomaly/) | — |
| SC-007 Inventory Movement Exception | Scaffolded only | [`sc-007-inventory-movement/`](sc-007-inventory-movement/) | — |

SC-001 and SC-002 each hold **only the genuinely slice-specific pieces**, physically relocated
(not just re-exported) from the shared services. Files are prefixed with `invoice_`/`claim_` —
not left as identically-named `rules.py`/`models.py`/etc. in both folders — so the two slices
stay visually distinguishable side by side in an editor or file tree:

| SC-001 file | SC-002 file | Contents |
|---|---|---|
| `invoice_rules.py` | `claim_rules.py` | Deterministic rule bundle + confidence constant (`SC001_CONFIDENCE` / `SC002_CONFIDENCE`) |
| `invoice_models.py` | `claim_models.py` | Request/response Pydantic models whose fields are inherently invoice- or claim-shaped |
| `invoice_ingestion.py` | `claim_ingestion.py` | `ingest_invoice()` / `ingest_claim()` body — hash-before-encrypt, dedup, sign, lineage |
| `invoice_canonical.py` | `claim_canonical.py` | `canonicalize_invoice()` / `canonicalize_claim()` body |
| `invoice_acr_artifacts.py` | `claim_acr_artifacts.py` | ACR artifacts #1/#2 (source-record hash, canonical hash) — artifacts #3-8 are generic on `case_id` and stay in the shared ACR handler |
| `invoice_routes_logic.py` | `claim_routes_logic.py` | Cases/claims list+detail+lines+negotiate, validation, canonical-invoice, dispute-letter generator, batch-submit per-file logic, the submit/submit-async pipeline runners |
| `parse_invoice.py` (SC-001 only) | — | The AI/regex invoice-PDF parser behind `/ingestion/parse-invoice` |

Every original location (`ingestion_svc/handler.py`, `canonical_truth/handler.py`,
`audit_acr_svc/handler.py`, `reasoning_svc/handler.py`, `api_gateway/models.py`,
`api_gateway/app.py`) now holds a thin delegator — the same class/route/decorator, calling
into the slice module via a lazy `importlib.import_module("sc-00X-....invoice_xxx")` /
`(...claim_xxx)` (hyphenated package names aren't valid Python identifiers, so a literal
`import` statement can't reach them; the import machinery resolves the path string
regardless). This keeps every existing caller and test unchanged. Verified by the full
gateway test suite (57 passed, 3 skipped) and live end-to-end smoke tests of both flows —
sync submit, async submit-async/submit-status, and ACR issuance — after each move.

What's deliberately **not** moved: anything that's the same code/table for every slice —
the Phase 3-8 route handlers (proposal, decide, tokens, execute, reconciliation, ACR issuance),
`open_case()`, `_read_case_metadata()`, `extract_contract_rates()` (contract rates apply to any
carrier billing, not just invoices), `send_dispute_letter_email()` (generic SMTP, no
invoice/claim coupling). Forking those per-slice would duplicate DB/hashing/signing code, which
is exactly what the Build Map's "platform primitives are first-class" doctrine (§18) warns
against. See each slice's own README for the full breakdown.

## Convention for filling in a scaffolded slice folder

Per the Build Map's Repositioning Board (§11), only build inside a slice folder what is
genuinely `SC-00X-SPECIFIC` — a source schema, a rule bundle, a connector fixture. If you
find yourself writing something reusable, it belongs in the platform service, not here.

Migration naming for a slice's first genuinely-specific table: see
[`../core/db/migrations/SLICE_MAP.md`](../core/db/migrations/SLICE_MAP.md).

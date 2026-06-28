"""
SC-005 Gateway — FastAPI application for Accessorial Charge Dispute.
Port: 8040

Routes:
  GET  /health
  POST /v1/accessorial-disputes/submit         — full pipeline: ingest→canonical→case→evidence+reasoning
  GET  /v1/accessorial-disputes                — paginated list
  GET  /v1/accessorial-disputes/{id}           — single dispute detail
  GET  /v1/accessorial-disputes/{id}/finding   — AI confidence + rule trace
  GET  /v1/accessorial-disputes/{id}/events    — case FSM audit trail
  POST /v1/accessorial-disputes/{id}/propose   — analyst proposes partial credit
  POST /v1/accessorial-disputes/{id}/decide    — manager approves/rejects (SoD enforced)

All mutating routes require:
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant-uuid>
  Idempotency-Key: <client-uuid>
"""
import os
from dotenv import load_dotenv
import paths  # noqa: F401 — must be first

load_dotenv()

import uuid
import json
import threading
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from services.api_gateway.auth import get_claims
from services.api_gateway.models import (
    SubmitAccessorialRequest,
    UIProposalRequest,
    UIDecideRequest,
)
from services.ingestion_svc.handler import IngestionHandler
from services.canonical_truth.handler import CanonicalHandler
from services.case_orchestration.handler import CaseHandler
from services.evidence_svc.handler import EvidenceHandler
from services.reasoning_svc.handler import ReasoningHandler
from services.governance_svc.handler import GovernanceHandler
from shared.db import DB_URL, q, q1
from middleware.oidc.claims import ZoikoClaims

_DB_URL     = os.getenv("DB_URL", DB_URL)
TENANT_SLUG = os.getenv("TENANT_SLUG", "default")


def _make_broker():
    from kafka.mock_kafka import MockKafkaBroker
    return MockKafkaBroker()


broker = _make_broker()

app = FastAPI(
    title="Zoiko SC-005 — Accessorial Charge Dispute",
    version="1.0.0",
    description="Accessorial charge dispute detection and partial credit recovery pipeline",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_v1 = APIRouter()


# ── Serialisation helper ───────────────────────────────────────────────────────

def _row(r: dict) -> dict:
    """Serialize a DB row — convert UUID and datetime to str."""
    out = {}
    for k, v in r.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, memoryview):
            out[k] = bytes(v).hex()
        else:
            out[k] = v
    return out


# ── Background worker ──────────────────────────────────────────────────────────

def _run_evidence_and_reasoning(
    tenant_id: str,
    case_id: str,
    canonical_invoice_id: str,
    charge_lines: list,
):
    """Bundle evidence and generate finding in a background thread."""
    try:
        ev = EvidenceHandler(_DB_URL, broker, TENANT_SLUG)
        bundle_result = ev.bundle(
            tenant_id=tenant_id,
            case_id=case_id,
            canonical_invoice_id=canonical_invoice_id,
            charge_lines=charge_lines,
        )
        rh = ReasoningHandler(_DB_URL, broker, TENANT_SLUG)
        rh.reason(
            tenant_id=tenant_id,
            case_id=case_id,
            bundle_id=bundle_result["bundle_id"],
            charge_lines=charge_lines,
        )
    except Exception:
        pass  # background failures are non-fatal; finding will be absent until retried


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
@app.get("/v1/health", tags=["system"], include_in_schema=False)
def health():
    return {"status": "ok", "service": "sc005-gateway", "version": "1.0.0"}


# ── Submit ─────────────────────────────────────────────────────────────────────

@_v1.post("/accessorial-disputes/submit", status_code=201, tags=["disputes"])
def submit_dispute(
    request: Request,
    body: SubmitAccessorialRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Full pipeline in one call:
      ingest → canonical → case → evidence + reasoning (background thread)

    If no charge line exceeds its contracted cap (dispute_total == 0),
    returns 200 with breach_detected=false and no case is opened.
    """
    tenant_id = str(claims.tenant_id)

    charge_lines_raw = [cl.model_dump() for cl in body.charge_lines]

    try:
        # Step 1 — Ingestion
        ingest_result = IngestionHandler(_DB_URL).ingest(
            tenant_id=tenant_id,
            carrier_id=body.carrier_id,
            invoice_reference=body.invoice_reference,
            invoice_date=body.invoice_date,
            charge_lines=charge_lines_raw,
            currency=body.currency,
        )

        dispute_total = ingest_result["dispute_total"]

        if dispute_total == 0:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=200,
                content={
                    "breach_detected": False,
                    "message": "No accessorial charges exceed contracted caps",
                },
            )

        # Step 2 — Canonical truth
        canonical_result = CanonicalHandler(_DB_URL).canonicalize(
            tenant_id=tenant_id,
            source_record_id=ingest_result["source_record_id"],
            carrier_id=body.carrier_id,
            invoice_reference=body.invoice_reference,
            invoice_date=body.invoice_date,
            charge_lines=charge_lines_raw,
            currency=body.currency,
            dispute_total=dispute_total,
        )

        # Step 3 — Open case
        case_result = CaseHandler(_DB_URL).open_case(
            tenant_id=tenant_id,
            canonical_invoice_id=canonical_result["canonical_invoice_id"],
            carrier_id=body.carrier_id,
            dispute_total=dispute_total,
            currency=body.currency,
        )

        case_id = case_result["case_id"]
        canonical_invoice_id = canonical_result["canonical_invoice_id"]

        # Step 3b — Persist individual charge lines to accessorial_charges.
        # The reconciliation_svc reads from this table for PARTIAL_ACCEPTANCE calculation.
        # Only write on first submission (is_new=True) to avoid duplicate charge rows.
        if case_result.get("is_new", True):
            _now = datetime.now(timezone.utc)
            for cl in charge_lines_raw:
                q(
                    """
                    INSERT INTO accessorial_charges
                        (id, tenant_id, case_id, invoice_id, charge_type,
                         billed_amount, contracted_cap, tariff_id, tariff_version,
                         currency, created_at)
                    VALUES
                        (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s,
                         %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        tenant_id,
                        case_id,
                        canonical_invoice_id,
                        cl["charge_type"],
                        cl["billed_amount"],
                        cl["contracted_cap"],
                        cl.get("tariff_id"),
                        cl.get("tariff_version"),
                        body.currency,
                        _now,
                    ),
                    _DB_URL,
                )

        # Steps 4+5 — Evidence + Reasoning in background
        t = threading.Thread(
            target=_run_evidence_and_reasoning,
            args=(tenant_id, case_id, canonical_invoice_id, charge_lines_raw),
            daemon=True,
        )
        t.start()

        # Wait briefly to capture finding_id if evidence+reasoning completes quickly
        t.join(timeout=2.0)

        # Try to fetch finding_id (may not be present yet if background is slow)
        finding_row = q1(
            "SELECT id, confidence FROM findings WHERE case_id = %s::uuid LIMIT 1",
            (case_id,),
            _DB_URL,
        )

        disputed_lines = [
            cl for cl in charge_lines_raw
            if float(cl.get("billed_amount", 0)) > float(cl.get("contracted_cap", 0))
        ]

        return {
            "case_id":           case_id,
            "state":             case_result["state"],
            "dispute_total":     dispute_total,
            "confidence":        finding_row["confidence"] if finding_row else None,
            "finding_id":        str(finding_row["id"]) if finding_row else None,
            "disputed_lines":    disputed_lines,
            "carrier_id":        body.carrier_id,
            "invoice_reference": body.invoice_reference,
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── List ───────────────────────────────────────────────────────────────────────

@_v1.get("/accessorial-disputes", tags=["disputes"])
def list_disputes(
    state: str | None = None,
    page: int = 1,
    page_size: int = 50,
    claims: ZoikoClaims = Depends(get_claims),
):
    """Paginated list of accessorial dispute cases for the tenant."""
    tenant_id = str(claims.tenant_id)
    offset    = (page - 1) * page_size

    base_sql = """
        SELECT
            c.id            AS case_id,
            ci.carrier_id,
            ci.invoice_number    AS invoice_reference,
            ci.total_amount AS dispute_total,
            ci.currency,
            c.state,
            c.opened_at,
            f.id            AS finding_id,
            f.confidence
        FROM cases c
        JOIN canonical_invoices ci
            ON ci.id = c.invoice_id
        LEFT JOIN findings f
            ON f.case_id = c.id
        WHERE c.tenant_id = %s::uuid
          AND c.case_type  = 'ACCESSORIAL_DISPUTE'
    """
    params: list = [tenant_id]

    if state:
        base_sql += " AND c.state = %s"
        params.append(state)

    base_sql += " ORDER BY c.opened_at DESC LIMIT %s OFFSET %s"
    params += [page_size, offset]

    rows = q(base_sql, params, _DB_URL)
    return [_row(r) for r in rows]


# ── Detail ─────────────────────────────────────────────────────────────────────

@_v1.get("/accessorial-disputes/{case_id}", tags=["disputes"])
def get_dispute(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """Full detail for a single accessorial dispute case."""
    tenant_id = str(claims.tenant_id)

    row = q1(
        """
        SELECT
            c.id            AS case_id,
            c.state         AS case_state,
            c.opened_at,
            ci.carrier_id,
            ci.invoice_number    AS invoice_reference,
            ci.total_amount AS dispute_total,
            ci.currency,
            f.id            AS finding_id,
            f.confidence,
            gt.id           AS task_id,
            gt.status       AS task_status,
            gto.id          AS token_id
        FROM cases c
        JOIN canonical_invoices ci
            ON ci.id = c.invoice_id
        LEFT JOIN findings f
            ON f.case_id = c.id
        LEFT JOIN governance_tasks gt
            ON gt.case_id = c.id
           AND gt.tenant_id = c.tenant_id
           AND gt.created_at = (
               SELECT MAX(gt2.created_at)
               FROM governance_tasks gt2
               WHERE gt2.case_id = c.id AND gt2.tenant_id = c.tenant_id
           )
        LEFT JOIN governance_tokens gto
            ON gto.case_id = c.id
           AND gto.tenant_id = c.tenant_id
           AND gto.issued_at = (
               SELECT MAX(gto2.issued_at)
               FROM governance_tokens gto2
               WHERE gto2.case_id = c.id AND gto2.tenant_id = c.tenant_id
           )
        WHERE c.id = %s::uuid
          AND c.tenant_id = %s::uuid
          AND c.case_type = 'ACCESSORIAL_DISPUTE'
        """,
        (case_id, tenant_id),
        _DB_URL,
    )

    if not row:
        raise HTTPException(status_code=404, detail=f"Dispute {case_id} not found")

    result = _row(row)

    # Charge lines from accessorial_charges (tariff-validated, includes computed dispute_amount)
    charge_rows = q(
        """SELECT charge_type, billed_amount::float, contracted_cap::float,
                  dispute_amount::float, tariff_id, tariff_version, currency
           FROM accessorial_charges
           WHERE case_id = %s::uuid AND tenant_id = %s::uuid
           ORDER BY created_at""",
        (case_id, tenant_id),
        _DB_URL,
    )
    result["charge_lines"] = [
        {**_row(cr), "status": "DISPUTED" if float(cr.get("dispute_amount") or 0) > 0 else "WITHIN_CAP"}
        for cr in charge_rows
    ]

    # Reconciliation amounts for 3-way bar (OUTCOME_RECORDED / CLOSED)
    recon_row = q1(
        """SELECT summary FROM reconciliations
           WHERE case_id = %s::uuid AND tenant_id = %s::uuid
           ORDER BY created_at DESC LIMIT 1""",
        (case_id, tenant_id),
        _DB_URL,
    )
    if recon_row:
        summary = recon_row["summary"] if isinstance(recon_row["summary"], dict) else json.loads(recon_row["summary"])
        result["accepted_amount"]    = summary.get("accepted_amount",    0)
        result["disputed_amount"]    = summary.get("disputed_amount",    0)
        result["written_off_amount"] = summary.get("written_off_amount", 0)

    # proposer_sub for SoD display in APPROVAL_PENDING step
    task_ext = q1(
        "SELECT proposer_sub FROM governance_tasks WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 1",
        (case_id, tenant_id),
        _DB_URL,
    )
    if task_ext:
        result["proposer_sub"] = task_ext["proposer_sub"]

    # acr_id for CLOSED state confirmation chip
    acr_row = q1(
        "SELECT id::text AS acr_id FROM action_certification_records WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY issued_at DESC LIMIT 1",
        (case_id, tenant_id),
        _DB_URL,
    )
    if acr_row:
        result["acr_id"] = acr_row["acr_id"]

    return result


# ── Finding ────────────────────────────────────────────────────────────────────

@_v1.get("/accessorial-disputes/{case_id}/finding", tags=["disputes"])
def get_finding(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """AI confidence score and rule trace for a dispute."""
    tenant_id = str(claims.tenant_id)

    row = q1(
        """
        SELECT
            f.id         AS finding_id,
            f.confidence,
            f.rule_trace,
            f.created_at
        FROM findings f
        JOIN cases c ON c.id = f.case_id
        WHERE f.case_id   = %s::uuid
          AND c.tenant_id = %s::uuid
          AND c.case_type = 'ACCESSORIAL_DISPUTE'
        ORDER BY f.created_at DESC
        LIMIT 1
        """,
        (case_id, tenant_id),
        _DB_URL,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Finding not yet available for dispute {case_id}",
        )

    return _row(row)


# ── Events ─────────────────────────────────────────────────────────────────────

@_v1.get("/accessorial-disputes/{case_id}/events", tags=["disputes"])
def get_events(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """Append-only case FSM audit trail for a dispute."""
    tenant_id = str(claims.tenant_id)

    # Verify case belongs to tenant and is of the right type
    case_row = q1(
        "SELECT id FROM cases WHERE id = %s::uuid AND tenant_id = %s::uuid AND case_type = 'ACCESSORIAL_DISPUTE'",
        (case_id, tenant_id),
        _DB_URL,
    )
    if not case_row:
        raise HTTPException(status_code=404, detail=f"Dispute {case_id} not found")

    rows = q(
        """
        SELECT id, event_type, from_state, to_state, actor_sub, payload, occurred_at
        FROM case_events
        WHERE case_id = %s::uuid
          AND tenant_id = %s::uuid
        ORDER BY occurred_at ASC
        """,
        (case_id, tenant_id),
        _DB_URL,
    )
    return [_row(r) for r in rows]


# ── Propose ────────────────────────────────────────────────────────────────────

@_v1.post("/accessorial-disputes/{case_id}/propose", status_code=201, tags=["governance"])
def propose(
    case_id: str,
    body: UIProposalRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    """Analyst proposes a partial credit for the accessorial dispute.
    Advances the case to APPROVAL_PENDING. Requires finding_id, amount, currency."""
    tenant_id = str(claims.tenant_id)
    actor_sub = getattr(body, "actor_sub", None) or claims.sub

    try:
        return GovernanceHandler(_DB_URL, broker, TENANT_SLUG).propose(
            tenant_id=tenant_id,
            case_id=case_id,
            finding_id=body.finding_id,
            amount=body.amount,
            currency=body.currency,
            actor_sub=actor_sub,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Decide ─────────────────────────────────────────────────────────────────────

@_v1.post("/accessorial-disputes/{case_id}/decide", tags=["governance"])
def decide(
    case_id: str,
    body: UIDecideRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    """Manager approves or rejects the partial credit proposal.
    SoD enforced: actor cannot be the same as the proposer."""
    if body.decision not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=422, detail="decision must be APPROVE or REJECT")

    tenant_id = str(claims.tenant_id)
    actor_sub = getattr(body, "actor_sub", None) or claims.sub

    try:
        return GovernanceHandler(_DB_URL, broker, TENANT_SLUG).decide(
            tenant_id=tenant_id,
            case_id=case_id,
            task_id=body.task_id,
            actor_sub=actor_sub,
            decision=body.decision,
            note=body.note or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Mount router ───────────────────────────────────────────────────────────────
app.include_router(_v1, prefix="/v1")

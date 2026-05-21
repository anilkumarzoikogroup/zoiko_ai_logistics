"""
API Gateway — FastAPI application for Phase 2.

Routes:
  GET  /health
  POST /invoices                          (ingest)
  POST /invoices/{source_record_id}/validate
  POST /invoices/{source_record_id}/canonicalize
  POST /cases                             (open case)
  PATCH /cases/{case_id}/state            (transition)

All mutating routes require:
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant-uuid>
  Idempotency-Key: <client-uuid>   (POST /invoices only)
"""
import os
import paths  # noqa: F401 — must be first

from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File

from services.api_gateway.auth   import get_claims
import re as _re, uuid, hashlib, json
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from services.api_gateway.models import (
    InvoiceRequest, InvoiceResponse,
    ValidateRequest, ValidateResponse,
    CanonicalizeRequest, CanonicalizeResponse,
    OpenCaseRequest, OpenCaseResponse,
    TransitionRequest, TransitionResponse,
    HealthResponse,
    SubmitCaseRequest, UIProposalRequest, UIDecideRequest,
    ContractRateRequest,
)
from shared.db import q, q1
from zoiko_common.crypto.jcs import canonicalize as _jcs
from services.ingestion_svc.handler    import IngestionHandler
from services.ingestion_svc.models     import InvoiceInput
from services.validation_svc.handler  import ValidationHandler
from services.canonical_truth.handler import CanonicalHandler
from services.case_orchestration.handler import CaseHandler
from middleware.oidc.claims import ZoikoClaims

DB_URL      = os.getenv("DB_URL",      "postgresql://postgres:1234@localhost/zoiko")
TENANT_SLUG = os.getenv("TENANT_SLUG", "default")

# Dev: in-memory mock; prod: swap for a real kafka-python KafkaProducer
from kafka.mock_kafka import MockKafkaBroker as _MockBroker
_BROKER = _MockBroker()

app = FastAPI(title="Zoiko Logistics API Gateway", version="2.0.0")


# ── Singleton handlers ────────────────────────────────────────────────────────

_ingestion  = IngestionHandler(DB_URL, _BROKER, TENANT_SLUG)
_validation = ValidationHandler(DB_URL, _BROKER, TENANT_SLUG)
_canonical  = CanonicalHandler(DB_URL, _BROKER, TENANT_SLUG)
_cases      = CaseHandler(DB_URL, _BROKER)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health():
    return HealthResponse(status="ok", service="api-gateway", version="2.0.0")


# ── Ingestion ─────────────────────────────────────────────────────────────────

@app.post("/invoices", response_model=InvoiceResponse, status_code=201, tags=["invoices"])
def ingest_invoice(
    body: InvoiceRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    invoice = InvoiceInput(
        carrier_id        = body.carrier_id,
        invoice_number    = body.invoice_number,
        total_amount      = body.total_amount,
        currency          = body.currency,
        route_origin      = body.route_origin,
        route_destination = body.route_destination,
        weight_lbs        = body.weight_lbs,
    )
    result = _ingestion.ingest_invoice(
        tenant_id       = str(claims.tenant_id),
        invoice         = invoice,
        idempotency_key = idempotency_key,
    )
    return InvoiceResponse(
        source_record_id = str(result.source_record_id),
        canonical_hash   = result.canonical_hash,
        idempotency_key  = result.idempotency_key,
        tenant_id        = str(result.tenant_id),
    )


# ── Validation ────────────────────────────────────────────────────────────────

@app.post(
    "/invoices/{source_record_id}/validate",
    response_model=ValidateResponse,
    tags=["invoices"],
)
def validate_invoice(
    source_record_id: str,
    body: ValidateRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _validation.validate(
            tenant_id        = str(claims.tenant_id),
            source_record_id = source_record_id,
            invoice_number   = body.invoice_number,
            carrier_id       = body.carrier_id,
            total_amount     = body.total_amount,
            currency         = body.currency,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ValidateResponse(
        validation_id     = str(result.validation_id),
        status            = result.status,
        overcharge_amount = result.overcharge_amount,
        violations        = len(result.rule_violations),
        currency          = result.currency,
    )


# ── Canonicalize ──────────────────────────────────────────────────────────────

@app.post(
    "/invoices/{source_record_id}/canonicalize",
    response_model=CanonicalizeResponse,
    tags=["invoices"],
)
def canonicalize_invoice(
    source_record_id: str,
    body: CanonicalizeRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _canonical.canonicalize_invoice(
            tenant_id        = str(claims.tenant_id),
            source_record_id = source_record_id,
            invoice_number   = body.invoice_number,
            carrier_id       = body.carrier_id,
            total_amount     = body.total_amount,
            currency         = body.currency,
            origin_city      = body.origin_city,
            dest_city        = body.dest_city,
            weight_lbs       = body.weight_lbs,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return CanonicalizeResponse(
        canonical_invoice_id  = str(result.canonical_invoice_id),
        canonical_shipment_id = str(result.canonical_shipment_id),
        canonical_hash        = result.canonical_hash,
        invoice_number        = result.invoice_number,
    )


# ── Cases ─────────────────────────────────────────────────────────────────────

@app.post("/cases", response_model=OpenCaseResponse, status_code=201, tags=["cases"])
def open_case(
    body: OpenCaseRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _cases.open_case(
            tenant_id            = str(claims.tenant_id),
            canonical_invoice_id = body.canonical_invoice_id,
            actor_sub            = claims.sub,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return OpenCaseResponse(
        case_id   = str(result.case_id),
        state     = result.state,
        is_new    = result.is_new,
        tenant_id = str(result.tenant_id),
    )


@app.patch("/cases/{case_id}/state", response_model=TransitionResponse, tags=["cases"])
def transition_case(
    case_id: str,
    body: TransitionRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        new_state = _cases.transition_state(
            tenant_id = str(claims.tenant_id),
            case_id   = case_id,
            new_state = body.new_state,
            actor_sub = body.actor_sub,
            payload   = body.payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return TransitionResponse(case_id=case_id, new_state=new_state)


# ══════════════════════════════════════════════════════════════════════════════
# FRONTEND UI API  — high-level REST endpoints shaped for the React dashboard
# ══════════════════════════════════════════════════════════════════════════════

def _r(row: dict) -> dict:
    """Convert a psycopg2 row to a JSON-safe dict (bytes→hex, Decimal→float, UUID→str)."""
    out = {}
    for k, v in row.items():
        if isinstance(v, memoryview):
            out[k] = "0x" + bytes(v).hex()
        elif isinstance(v, (bytes, bytearray)):
            out[k] = "0x" + v.hex()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _raw_exec(sql: str, params: tuple) -> None:
    import psycopg2 as _pg
    import psycopg2.extras as _pge
    _pge.register_uuid()
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _sign_dev(tenant_id: str, data: bytes) -> tuple[bytes, str]:
    row = q1("SELECT slug FROM tenants WHERE id = %s::uuid", (tenant_id,))
    slug = row["slug"] if row else "default"
    from shared.signer import sign as _sign
    return _sign(slug, data)


def _cases_q(where: str, params: tuple) -> list[dict]:
    rows = q(f"""
        SELECT
            c.id::text                                                   AS id,
            c.tenant_id::text                                            AS tenant_id,
            c.state,
            ci.carrier_id                                                AS carrier,
            COALESCE(cs.origin_city || '-' || cs.dest_city,
                     ci.invoice_number)                                  AS shipment_ref,
            ci.total_amount::float                                       AS amount,
            ci.currency,
            COALESCE((
                SELECT (vr.rule_violations->0->>'delta')::float
                FROM   validation_results vr
                WHERE  vr.source_record_id = ci.source_record_id
                  AND  vr.status = 'FAIL'
                LIMIT  1
            ), 0)                                                        AS diff,
            COALESCE((
                SELECT f.confidence::float
                FROM   findings f WHERE f.case_id = c.id LIMIT 1
            ), 0)                                                        AS confidence,
            c.opened_at,
            c.opened_at                                                  AS updated_at
        FROM  cases c
        JOIN  canonical_invoices ci  ON ci.id = c.invoice_id
        LEFT JOIN canonical_shipments cs ON cs.invoice_id = ci.id
        {where}
        ORDER BY c.opened_at DESC
        LIMIT 100
    """, params)
    return [_r(row) for row in rows]


# ── Dashboard stats ────────────────────────────────────────────────────────────

@app.get("/dashboard/stats", tags=["ui"])
def ui_stats(claims: ZoikoClaims = Depends(get_claims)):
    tid = claims.tenant_id
    cnt = q1("""
        SELECT
            COUNT(*)                                                           AS total_cases,
            SUM(CASE WHEN state='APPROVAL_PENDING'                  THEN 1 ELSE 0 END) AS pending_approval,
            SUM(CASE WHEN state IN ('EXECUTION_READY','DISPATCHED','OUTCOME_RECORDED','CLOSED')
                                                                    THEN 1 ELSE 0 END) AS approved
        FROM cases WHERE tenant_id = %s::uuid
    """, (tid,))
    rec = q1("""
        SELECT
            COALESCE(SUM((
                SELECT (vr.rule_violations->0->>'delta')::float
                FROM   validation_results vr
                WHERE  vr.source_record_id = ci.source_record_id AND vr.status='FAIL'
                LIMIT  1
            )), 0)                             AS total_recovered,
            COALESCE(AVG(f.confidence), 0)     AS avg_confidence
        FROM  cases c
        JOIN  canonical_invoices ci ON ci.id = c.invoice_id
        LEFT JOIN findings f ON f.case_id = c.id
        WHERE c.tenant_id = %s::uuid
          AND c.state IN ('EXECUTION_READY','DISPATCHED','OUTCOME_RECORDED','CLOSED')
    """, (tid,))
    return {
        "total_cases":      int(cnt["total_cases"] or 0),
        "pending_approval": int(cnt["pending_approval"] or 0),
        "approved":         int(cnt["approved"] or 0),
        "total_recovered":  float(rec["total_recovered"] or 0),
        "avg_confidence":   float(rec["avg_confidence"] or 0),
    }


# ── Cases list + detail ────────────────────────────────────────────────────────

@app.get("/cases", tags=["ui"])
def ui_list_cases(
    state: str | None = None,
    claims: ZoikoClaims = Depends(get_claims),
):
    tid = claims.tenant_id
    if state:
        return _cases_q("WHERE c.tenant_id=%s::uuid AND c.state=%s", (tid, state))
    return _cases_q("WHERE c.tenant_id=%s::uuid", (tid,))


@app.get("/cases/{case_id}", tags=["ui"])
def ui_get_case(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    rows = _cases_q(
        "WHERE c.tenant_id=%s::uuid AND c.id=%s::uuid",
        (claims.tenant_id, case_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Case not found")
    return rows[0]


# ── Case events ────────────────────────────────────────────────────────────────

@app.get("/cases/{case_id}/events", tags=["ui"])
def ui_case_events(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    rows = q("""
        SELECT id::text, case_id::text, from_state, to_state,
               actor_sub                                    AS actor,
               COALESCE(payload->>'reason', event_type)     AS reason,
               occurred_at                                  AS created_at
        FROM   case_events
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY occurred_at ASC
    """, (case_id, claims.tenant_id))
    return [_r(r) for r in rows]


# ── Validation result ──────────────────────────────────────────────────────────

@app.get("/cases/{case_id}/validation", tags=["ui"])
def ui_validation(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1("""
        SELECT
            vr.id::text,
            c.id::text                                                         AS case_id,
            vr.status                                                          AS outcome,
            COALESCE((vr.rule_violations->0->>'delta')::float, 0)              AS diff,
            ci.currency,
            COALESCE(vr.rule_violations->0->>'rule', 'No violation')           AS reason,
            ci.total_amount::float                                             AS invoice_amount,
            GREATEST(0, ci.total_amount::float -
                COALESCE((vr.rule_violations->0->>'delta')::float, 0))         AS contract_amount,
            vr.validated_at
        FROM   validation_results vr
        JOIN   canonical_invoices ci ON ci.source_record_id = vr.source_record_id
        JOIN   cases c ON c.invoice_id = ci.id
        WHERE  c.id=%s::uuid AND c.tenant_id=%s::uuid
        LIMIT  1
    """, (case_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No validation found")
    return _r(row)


# ── Canonical invoice ──────────────────────────────────────────────────────────

@app.get("/cases/{case_id}/canonical-invoice", tags=["ui"])
def ui_canonical_invoice(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1("""
        SELECT
            ci.id::text,
            ci.tenant_id::text,
            COALESCE(cs.origin_city||'-'||cs.dest_city, ci.invoice_number) AS shipment_ref,
            ci.carrier_id                       AS carrier,
            ci.total_amount::float              AS amount,
            ci.currency,
            encode(ci.canonical_hash, 'hex')    AS canonical_hash,
            encode(ci.signature,      'hex')    AS signature,
            ci.created_at                       AS signed_at
        FROM  canonical_invoices ci
        JOIN  cases c ON c.invoice_id = ci.id
        LEFT JOIN canonical_shipments cs ON cs.invoice_id = ci.id
        WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid
        LIMIT 1
    """, (case_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No canonical invoice found")
    return _r(row)


# ── Source records ─────────────────────────────────────────────────────────────

@app.get("/ingestion/source-records", tags=["ui"])
def ui_source_records(claims: ZoikoClaims = Depends(get_claims)):
    rows = q("""
        SELECT
            sr.id::text,
            sr.tenant_id::text,
            encode(sr.canonical_hash, 'hex')    AS canonical_hash,
            encode(sr.signature,      'hex')    AS signature,
            sr.kid                              AS key_id,
            sr.created_at                       AS received_at,
            ci.carrier_id                       AS _carrier,
            ci.total_amount::float              AS _amount,
            ci.invoice_number                   AS _shipment
        FROM  source_records sr
        LEFT JOIN canonical_invoices ci ON ci.source_record_id = sr.id
        WHERE sr.tenant_id=%s::uuid
        ORDER BY sr.created_at DESC
        LIMIT 50
    """, (claims.tenant_id,))
    result = []
    for r in rows:
        d = _r(r)
        d["payload_preview"] = {
            "carrier":  d.pop("_carrier",  ""),
            "amount":   d.pop("_amount",   0),
            "shipment": d.pop("_shipment", ""),
        }
        result.append(d)
    return result


# ── Evidence bundle ────────────────────────────────────────────────────────────

@app.get("/cases/{case_id}/evidence", tags=["ui"])
def ui_evidence(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    bundle = q1("""
        SELECT id::text, case_id::text,
               encode(bundle_hash, 'hex') AS merkle_root,
               created_at
        FROM   evidence_bundles
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        LIMIT  1
    """, (case_id, claims.tenant_id))
    if not bundle:
        raise HTTPException(status_code=404, detail="No evidence bundle found")
    items = q("""
        SELECT id::text, bundle_id::text, item_type,
               encode(item_hash, 'hex') AS leaf_hash,
               added_at
        FROM   evidence_items
        WHERE  bundle_id=%s::uuid
        ORDER BY added_at ASC
    """, (bundle["id"],))
    row = _r(bundle)
    row["item_count"] = len(items)
    row["items"] = [_r(i) for i in items]
    return row


# ── Finding ────────────────────────────────────────────────────────────────────

@app.get("/cases/{case_id}/finding", tags=["ui"])
def ui_finding(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1("""
        SELECT id::text, case_id::text, confidence::float,
               rule_trace,
               encode(signature, 'hex') AS finding_hash,
               created_at
        FROM   findings
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY created_at DESC LIMIT 1
    """, (case_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No finding found")
    d = _r(row)
    d["trace"] = d.pop("rule_trace") or {}
    return d


# ── Proposal ───────────────────────────────────────────────────────────────────

@app.get("/cases/{case_id}/proposal", tags=["ui"])
def ui_get_proposal(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1("""
        SELECT id::text, case_id::text,
               proposed_action AS action,
               amount::float, currency,
               proposer_sub    AS proposed_by,
               created_at      AS proposed_at
        FROM   decision_proposals
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY created_at DESC LIMIT 1
    """, (case_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No proposal found")
    return _r(row)


@app.post("/cases/{case_id}/proposal", tags=["ui"], status_code=201)
def ui_create_proposal(
    case_id: str,
    body: UIProposalRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    tid = claims.tenant_id
    now = datetime.now(timezone.utc)

    # Ensure evidence bundle exists (create placeholder if missing)
    b_row = q1("SELECT id FROM evidence_bundles WHERE case_id=%s::uuid AND tenant_id=%s::uuid LIMIT 1", (case_id, tid))
    if b_row:
        bundle_id = str(b_row["id"])
    else:
        bid = uuid.uuid4()
        ph = bytes(32)
        _raw_exec("""
            INSERT INTO evidence_bundles (id, tenant_id, case_id, bundle_hash, signature, kid, created_at)
            VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s)
        """, (bid, tid, case_id, ph, ph, "dev-placeholder", now))
        bundle_id = str(bid)

    # Ensure finding exists (create placeholder if missing)
    f_row = q1("SELECT id FROM findings WHERE case_id=%s::uuid AND tenant_id=%s::uuid LIMIT 1", (case_id, tid))
    if f_row:
        finding_id = str(f_row["id"])
    else:
        fid = uuid.uuid4()
        confidence = 0.96
        rule_trace = json.dumps({"fuel_charge": {"confidence": 1.0, "weight": 0.5}, "accessorial": {"confidence": 0.92, "weight": 0.5}})
        fhash = hashlib.sha256(b"zoiko.finding.v1:" + _jcs({"case_id": case_id, "confidence": confidence})).digest()
        fsig, fkid = _sign_dev(tid, fhash)
        _raw_exec("""
            INSERT INTO findings (id, tenant_id, case_id, bundle_id, confidence, rule_trace, signature, kid, created_at)
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s, %s)
        """, (fid, tid, case_id, uuid.UUID(bundle_id), confidence, rule_trace, fsig, fkid, now))
        finding_id = str(fid)

    # Create decision proposal
    pid = uuid.uuid4()
    prop_bytes = _jcs({"action": body.action, "amount": float(body.amount), "currency": body.currency, "case_id": case_id})
    prop_hash  = hashlib.sha256(b"zoiko.proposal.v1:" + prop_bytes).digest()
    psig, pkid = _sign_dev(tid, prop_hash)
    _raw_exec("""
        INSERT INTO decision_proposals
            (id, tenant_id, case_id, finding_id, proposed_action, amount, currency,
             proposer_sub, proposal_hash, signature, kid, created_at)
        VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (pid, tid, case_id, uuid.UUID(finding_id), body.action, float(body.amount),
          body.currency, claims.sub, prop_hash, psig, pkid, now))

    # Create approval task
    _raw_exec("""
        INSERT INTO approval_tasks (id, tenant_id, proposal_id, proposer_sub, status, created_at)
        VALUES (%s, %s::uuid, %s::uuid, %s, 'PENDING', %s)
    """, (uuid.uuid4(), tid, pid, claims.sub, now))

    # Transition case → APPROVAL_PENDING
    c_row = q1("SELECT state FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tid))
    if c_row and c_row["state"] in ("NEW", "EVIDENCE_PENDING", "FINDING_GENERATED"):
        prev = c_row["state"]
        _raw_exec("UPDATE cases SET state='APPROVAL_PENDING' WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tid))
        _raw_exec("""
            INSERT INTO case_events (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
            VALUES (%s, %s::uuid, %s::uuid, 'PROPOSAL_CREATED', %s, 'APPROVAL_PENDING', %s, %s::jsonb, %s)
        """, (uuid.uuid4(), tid, case_id, prev, claims.sub, json.dumps({"proposal_id": str(pid)}), now))

    return {"id": str(pid), "case_id": case_id, "action": body.action,
            "amount": float(body.amount), "currency": body.currency,
            "proposed_by": claims.sub, "proposed_at": now.isoformat()}


# ── Decide ─────────────────────────────────────────────────────────────────────

@app.post("/cases/{case_id}/decide", tags=["ui"])
def ui_decide(
    case_id: str,
    body: UIDecideRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    tid     = claims.tenant_id
    now     = datetime.now(timezone.utc)
    outcome = body.decision
    if outcome not in ("EXECUTION_READY", "ABORTED"):
        raise HTTPException(400, detail="decision must be EXECUTION_READY or ABORTED")

    task = q1("""
        SELECT at.id, at.proposal_id, at.proposer_sub
        FROM   approval_tasks at
        JOIN   decision_proposals dp ON dp.id = at.proposal_id
        WHERE  dp.case_id=%s::uuid AND at.tenant_id=%s::uuid AND at.status='PENDING'
        ORDER BY at.created_at DESC LIMIT 1
    """, (case_id, tid))
    if not task:
        raise HTTPException(404, detail="No pending approval task for this case")
    if claims.sub == str(task["proposer_sub"]):
        raise HTTPException(422, detail="Separation of Duties: proposer cannot approve own proposal")

    proposal_id = str(task["proposal_id"])
    task_id     = str(task["id"])

    # Get or create policy bundle
    pb = q1("SELECT id FROM policy_bundles WHERE tenant_id=%s::uuid AND active=TRUE LIMIT 1", (tid,))
    if pb:
        policy_bundle_id = str(pb["id"])
    else:
        pbid = uuid.uuid4()
        _raw_exec("""
            INSERT INTO policy_bundles (id, tenant_id, version, rego_hash, active, deployed_at)
            VALUES (%s::uuid, %s::uuid, 'v1.0.0', %s, TRUE, %s)
        """, (pbid, tid, hashlib.sha256(b"zoiko.opa.freight_dispute.v1").digest(), now))
        policy_bundle_id = str(pbid)

    # Create governance decision
    dec_bytes = _jcs({"actor_sub": claims.sub, "outcome": outcome, "proposal_id": proposal_id, "task_id": task_id, "tenant_id": tid})
    dec_hash  = hashlib.sha256(b"zoiko.governance.decision.v1:" + dec_bytes).digest()
    dec_sig, dec_kid = _sign_dev(tid, dec_hash)
    did = uuid.uuid4()
    _raw_exec("""
        INSERT INTO governance_decisions
            (id, tenant_id, proposal_id, policy_bundle_id, outcome, decision_hash, signature, kid, decided_at)
        VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s)
    """, (did, tid, uuid.UUID(proposal_id), uuid.UUID(policy_bundle_id), outcome, dec_hash, dec_sig, dec_kid, now))

    _raw_exec("""
        UPDATE approval_tasks SET status=%s, actor_sub=%s, actioned_at=%s
        WHERE  id=%s::uuid AND tenant_id=%s::uuid
    """, (outcome, claims.sub, now, uuid.UUID(task_id), tid))

    # Mint token if approved
    token_id = None
    if outcome == "EXECUTION_READY":
        prop_det = q1("SELECT proposed_action, amount, currency FROM decision_proposals WHERE id=%s::uuid", (uuid.UUID(proposal_id),))
        scope  = prop_det["proposed_action"] if prop_det else "EXECUTE_CREDIT_MEMO"
        exp    = now + timedelta(minutes=15)
        tb     = hashlib.sha256(tid.encode() + str(did).encode()).digest()
        th     = hashlib.sha256(b"zoiko.token.v1:" + _jcs({"decision_id": str(did), "tenant_id": tid, "scope": scope})).digest()
        tsig, tkid = _sign_dev(tid, th)
        token_id = uuid.uuid4()
        _raw_exec("""
            INSERT INTO governance_tokens
                (id, tenant_id, decision_id, scope, tenant_binding, status,
                 expires_at, token_hash, signature, kid, issued_at)
            VALUES (%s, %s::uuid, %s::uuid, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s)
        """, (token_id, tid, did, scope, tb, exp, th, tsig, tkid, now))

    # Transition case state
    c_row = q1("SELECT state FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tid))
    if c_row and c_row["state"] == "APPROVAL_PENDING":
        _raw_exec("UPDATE cases SET state=%s WHERE id=%s::uuid AND tenant_id=%s::uuid", (outcome, case_id, tid))
        _raw_exec("""
            INSERT INTO case_events (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
            VALUES (%s, %s::uuid, %s::uuid, %s, 'APPROVAL_PENDING', %s, %s, %s::jsonb, %s)
        """, (uuid.uuid4(), tid, case_id, f"GOVERNANCE_{outcome}", outcome, claims.sub, json.dumps({"decision_id": str(did)}), now))

    return {"id": str(did), "case_id": case_id, "decision": outcome,
            "actor_sub": claims.sub, "decided_at": now.isoformat(),
            "token_id": str(token_id) if token_id else None}


# ── Tokens ─────────────────────────────────────────────────────────────────────

_TOKEN_SELECT = """
    SELECT
        gt.id::text,
        dp.case_id::text,
        gt.tenant_id::text,
        dp.proposed_action              AS action,
        dp.amount::float,
        dp.currency,
        encode(gt.tenant_binding,'hex') AS tenant_binding,
        gt.expires_at                   AS exp,
        gt.status,
        encode(gt.signature,'hex')      AS signature,
        gt.kid                          AS key_id,
        gt.issued_at
    FROM  governance_tokens gt
    JOIN  governance_decisions gd ON gd.id = gt.decision_id
    JOIN  decision_proposals dp   ON dp.id = gd.proposal_id
"""


@app.get("/tokens", tags=["ui"])
def ui_list_tokens(
    status: str | None = None,
    claims: ZoikoClaims = Depends(get_claims),
):
    if status:
        rows = q(_TOKEN_SELECT + "WHERE gt.tenant_id=%s::uuid AND gt.status=%s ORDER BY gt.issued_at DESC LIMIT 50",
                 (claims.tenant_id, status))
    else:
        rows = q(_TOKEN_SELECT + "WHERE gt.tenant_id=%s::uuid ORDER BY gt.issued_at DESC LIMIT 50",
                 (claims.tenant_id,))
    return [_r(r) for r in rows]


@app.get("/cases/{case_id}/token", tags=["ui"])
def ui_case_token(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1(_TOKEN_SELECT + "WHERE dp.case_id=%s::uuid AND gt.tenant_id=%s::uuid ORDER BY gt.issued_at DESC LIMIT 1",
             (case_id, claims.tenant_id))
    if not row:
        return None
    return _r(row)


# ── Kafka events (from case_events) ───────────────────────────────────────────

@app.get("/kafka/events", tags=["ui"])
def ui_kafka_events(claims: ZoikoClaims = Depends(get_claims)):
    rows = q("""
        SELECT event_type AS topic, case_id::text AS key, payload, occurred_at AS published_at
        FROM   case_events WHERE tenant_id=%s::uuid
        ORDER BY occurred_at DESC LIMIT 50
    """, (claims.tenant_id,))
    return [_r(r) for r in rows]


# ── Contract rates ────────────────────────────────────────────────────────────

@app.get("/contract-rates", tags=["ui"])
def ui_list_contract_rates(claims: ZoikoClaims = Depends(get_claims)):
    rows = q("""
        SELECT id::text, carrier_id AS carrier, rate_type, rate_value::float,
               currency, effective_on::text, expires_on::text
        FROM   contract_rates
        WHERE  tenant_id = %s::uuid
        ORDER  BY carrier_id, rate_type
    """, (claims.tenant_id,))
    return [_r(r) for r in rows]


@app.post("/contract-rates", tags=["ui"], status_code=201)
def ui_create_contract_rate(
    body: ContractRateRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    rid = uuid.uuid4()
    _raw_exec("""
        INSERT INTO contract_rates
            (id, tenant_id, carrier_id, rate_type, rate_value, currency, effective_on, expires_on)
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s)
    """, (rid, claims.tenant_id, body.carrier_id, body.rate_type,
          body.rate_value, body.currency, body.effective_on, body.expires_on))
    return {"id": str(rid), "carrier_id": body.carrier_id, "rate_type": body.rate_type,
            "rate_value": body.rate_value, "currency": body.currency,
            "effective_on": body.effective_on}


@app.delete("/contract-rates/{rate_id}", tags=["ui"])
def ui_delete_contract_rate(rate_id: str, claims: ZoikoClaims = Depends(get_claims)):
    _raw_exec(
        "DELETE FROM contract_rates WHERE id=%s::uuid AND tenant_id=%s::uuid",
        (rate_id, claims.tenant_id),
    )
    return {"deleted": rate_id}


# ── Invoice file parse ────────────────────────────────────────────────────────

@app.post("/ingestion/parse-invoice", tags=["ui"])
async def parse_invoice_file(
    file: UploadFile = File(...),
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Accept an invoice PDF or image and return extracted fields.
    Demo: detects SC-001 (BlueDart) by filename; otherwise returns empty fields.
    Production: swap this body for an OCR/ML extraction pipeline.
    """
    name = (file.filename or "").lower()
    if any(k in name for k in ("bluedart", "sc001", "sc-001")):
        return {"carrier": "BlueDart", "route": "Hyderabad-Warangal",
                "amount": 12500, "currency": "INR"}
    # Generic invoice — return empty so user fills manually
    return {"carrier": "", "route": "", "amount": 0, "currency": "INR"}


# ── High-level case creation (ingest + validate + canonicalize + open) ─────────

@app.post("/cases/submit", tags=["ui"], status_code=201)
def ui_submit_case(
    body: SubmitCaseRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    parts  = _re.split(r'\s*[-→–]\s*', body.route.strip(), maxsplit=1)
    origin = parts[0].strip() if parts else body.route
    dest   = parts[1].strip() if len(parts) > 1 else "Unknown"
    inv_no = f"UI-{uuid.uuid4().hex[:8].upper()}"

    slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (claims.tenant_id,))
    slug = slug_row["slug"] if slug_row else "default"

    from kafka.mock_kafka import MockKafkaBroker as _MB
    _broker = _MB()
    from services.ingestion_svc.handler      import IngestionHandler
    from services.ingestion_svc.models       import InvoiceInput
    from services.validation_svc.handler     import ValidationHandler
    from services.canonical_truth.handler    import CanonicalHandler
    from services.case_orchestration.handler import CaseHandler

    inv = InvoiceInput(carrier_id=body.carrier, invoice_number=inv_no,
                       total_amount=float(body.amount), currency=body.currency,
                       route_origin=origin, route_destination=dest, weight_lbs=0.0)
    ing_r  = IngestionHandler(DB_URL, _broker, slug).ingest_invoice(claims.tenant_id, inv, idempotency_key)
    val_r  = ValidationHandler(DB_URL, _broker, slug).validate(claims.tenant_id, ing_r.source_record_id, inv_no, body.carrier, float(body.amount), body.currency)
    can_r  = CanonicalHandler(DB_URL, _broker, slug).canonicalize_invoice(claims.tenant_id, ing_r.source_record_id, inv_no, body.carrier, float(body.amount), body.currency, origin, dest, 0.0)
    case_r = CaseHandler(DB_URL, _broker).open_case(claims.tenant_id, can_r.canonical_invoice_id, claims.sub)

    rows = _cases_q("WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid", (str(case_r.case_id), claims.tenant_id))
    return rows[0] if rows else {"id": str(case_r.case_id), "state": case_r.state}

"""
SC-003 Gateway — FastAPI application for Shipment Exception / SLA Penalty.
Port: 8020

Routes:
  GET  /health
  POST /shipment-exceptions/submit          — full pipeline: ingest→canonical→case→finding
  GET  /shipment-exceptions                 — paginated list
  GET  /shipment-exceptions/{id}            — single exception
  GET  /shipment-exceptions/{id}/finding    — AI confidence + rule trace
  GET  /shipment-exceptions/{id}/events     — case FSM audit trail
  GET  /shipment-exceptions/{id}/shipment-events — carrier event stream
  POST /shipment-exceptions/{id}/propose    — analyst proposes SLA credit
  POST /shipment-exceptions/{id}/decide     — manager approves/rejects (SoD enforced)

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
from fastapi import FastAPI, APIRouter, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from services.api_gateway.auth import get_claims
from services.api_gateway.models import (
    ShipmentExceptionSubmitRequest, UIProposalRequest, UIDecideRequest,
)
from services.api_gateway.routes_logic import (
    submit_exception, ui_list_exceptions, ui_get_exception,
    ui_get_exception_finding, ui_get_exception_events, ui_get_shipment_events,
    run_evidence_and_reasoning_exception,
)
from services.ingestion_svc.handler    import IngestionHandler
from services.canonical_truth.handler  import CanonicalHandler
from services.case_orchestration.handler import CaseHandler
from services.governance_svc.handler   import GovernanceHandler
from shared.db import DB_URL

DB_URL          = os.getenv("DB_URL", DB_URL)
TENANT_SLUG     = os.getenv("TENANT_SLUG", "default")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "").strip()


def _make_broker():
    if KAFKA_BOOTSTRAP:
        try:
            from kafka.mock_kafka import MockKafkaBroker
            return MockKafkaBroker()
        except Exception:
            pass
    from kafka.mock_kafka import MockKafkaBroker
    return MockKafkaBroker()


_BROKER = _make_broker()

_v1 = APIRouter()

app = FastAPI(
    title="Zoiko SC-003 — Shipment Exception Gateway",
    version="1.0.0",
    description="SLA breach detection and penalty recovery pipeline",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def _capture_metadata(request: Request, idem_key: str) -> dict:
    return {
        "idempotency_key": idem_key,
        "source_ip":       request.client.host if request.client else "",
        "user_agent":      request.headers.get("User-Agent", ""),
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "sc003-gateway", "version": "1.0.0"}


# ── Submit ────────────────────────────────────────────────────────────────────

@_v1.post("/shipment-exceptions/submit")
def post_submit(
    request: Request,
    body: ShipmentExceptionSubmitRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims=Depends(get_claims),
):
    tenant_id = claims.tenant_id
    actor_sub = claims.sub
    return submit_exception(
        db_url                    = DB_URL,
        broker                    = _BROKER,
        ingestion_cls             = IngestionHandler,
        canonical_cls             = CanonicalHandler,
        case_cls                  = CaseHandler,
        run_evidence_and_reasoning_fn = run_evidence_and_reasoning_exception,
        capture_rest_push_metadata_fn = _capture_metadata,
        request                   = request,
        body                      = body,
        idempotency_key           = idempotency_key,
        tenant_id                 = tenant_id,
        actor_sub                 = actor_sub,
    )


# ── List / Get ────────────────────────────────────────────────────────────────

@_v1.get("/shipment-exceptions")
def list_exceptions(
    state: str | None = None,
    page: int = 1,
    page_size: int = 20,
    claims=Depends(get_claims),
):
    return ui_list_exceptions(_row, claims.tenant_id, state, page, page_size)


@_v1.get("/shipment-exceptions/{case_id}")
def get_exception(case_id: str, claims=Depends(get_claims)):
    return ui_get_exception(_row, claims.tenant_id, case_id)


@_v1.get("/shipment-exceptions/{case_id}/finding")
def get_finding(case_id: str, claims=Depends(get_claims)):
    return ui_get_exception_finding(_row, claims.tenant_id, case_id)


@_v1.get("/shipment-exceptions/{case_id}/events")
def get_events(case_id: str, claims=Depends(get_claims)):
    return ui_get_exception_events(_row, claims.tenant_id, case_id)


@_v1.get("/shipment-exceptions/{case_id}/shipment-events")
def get_shipment_events(case_id: str, claims=Depends(get_claims)):
    return ui_get_shipment_events(_row, claims.tenant_id, case_id)


# ── Governance ────────────────────────────────────────────────────────────────

@_v1.post("/shipment-exceptions/{case_id}/propose")
def propose(
    case_id: str,
    body: UIProposalRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims=Depends(get_claims),
):
    return GovernanceHandler(DB_URL, _BROKER, TENANT_SLUG).propose(
        tenant_id  = claims.tenant_id,
        case_id    = case_id,
        finding_id = body.finding_id,
        amount     = body.amount,
        currency   = body.currency,
        actor_sub  = claims.sub,
    )


@_v1.post("/shipment-exceptions/{case_id}/decide")
def decide(
    case_id: str,
    body: UIDecideRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims=Depends(get_claims),
):
    if body.decision not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=422, detail="decision must be APPROVE or REJECT")
    return GovernanceHandler(DB_URL, _BROKER, TENANT_SLUG).decide(
        tenant_id = claims.tenant_id,
        case_id   = case_id,
        task_id   = body.task_id,
        actor_sub = claims.sub,
        decision  = body.decision,
        note      = body.note or "",
    )


# ── Mount router ──────────────────────────────────────────────────────────────
app.include_router(_v1, prefix="/v1")

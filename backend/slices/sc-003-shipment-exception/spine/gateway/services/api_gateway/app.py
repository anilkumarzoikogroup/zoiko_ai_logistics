"""
SC-003 Gateway — FastAPI application for Shipment Exception / SLA Penalty.
Port: 8020

Routes:
  GET  /health
  POST /shipment-exceptions/submit          — blocking full pipeline (returns case inline)
  POST /shipment-exceptions/submit-async    — non-blocking, returns job_id immediately
  GET  /shipment-exceptions/submit-status/{job_id} — poll until status=done|error
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

# ── Async submit job store (in-memory + DB fallback) ─────────────────────────
_SUBMIT_JOBS: dict = {}


def _ensure_jobs_table() -> None:
    try:
        import psycopg2 as _pg
        conn = _pg.connect(DB_URL)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sc003_submit_jobs (
                job_id    TEXT PRIMARY KEY,
                status    TEXT NOT NULL DEFAULT 'pending',
                case_data JSONB,
                error     TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.close(); conn.close()
    except Exception:
        pass


def _persist_job(job_id: str, status: str, case_data, error) -> None:
    try:
        import psycopg2 as _pg, json as _json
        conn = _pg.connect(DB_URL)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sc003_submit_jobs (job_id, status, case_data, error)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (job_id) DO UPDATE
              SET status    = EXCLUDED.status,
                  case_data = EXCLUDED.case_data,
                  error     = EXCLUDED.error
        """, (job_id, status, _json.dumps(case_data) if case_data else None, error))
        cur.close(); conn.close()
    except Exception:
        pass


def _load_job(job_id: str):
    try:
        import psycopg2 as _pg, psycopg2.extras as _pge
        conn = _pg.connect(DB_URL)
        cur = conn.cursor(cursor_factory=_pge.RealDictCursor)
        cur.execute("SELECT status, case_data, error FROM sc003_submit_jobs WHERE job_id=%s", (job_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return {"status": row["status"], "case": row["case_data"], "error": row["error"]}
    except Exception:
        pass
    return None


def _async_worker(job_id: str, db_url: str, broker, body, tenant_id: str, actor_sub: str, idempotency_key: str, request_scope: dict) -> None:
    try:
        result = submit_exception(
            db_url                        = db_url,
            broker                        = broker,
            ingestion_cls                 = IngestionHandler,
            canonical_cls                 = CanonicalHandler,
            case_cls                      = CaseHandler,
            run_evidence_and_reasoning_fn = run_evidence_and_reasoning_exception,
            capture_rest_push_metadata_fn = lambda *a, **kw: None,
            request                       = None,
            body                          = body,
            idempotency_key               = idempotency_key,
            tenant_id                     = tenant_id,
            actor_sub                     = actor_sub,
        )
        _SUBMIT_JOBS[job_id] = {"status": "done", "case": result, "error": None}
        _persist_job(job_id, "done", result, None)
    except Exception as exc:
        _SUBMIT_JOBS[job_id] = {"status": "error", "case": None, "error": str(exc)}
        _persist_job(job_id, "error", None, str(exc))


_ensure_jobs_table()

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


# ── Async submit (non-blocking — frontend polls for result) ──────────────────

@_v1.post("/shipment-exceptions/submit-async", status_code=202)
def post_submit_async(
    request: Request,
    body: ShipmentExceptionSubmitRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims=Depends(get_claims),
):
    """Non-blocking submit: returns job_id immediately, runs pipeline in background.
    Poll GET /shipment-exceptions/submit-status/{job_id} every 2s until status='done'.
    """
    import threading as _th, uuid as _u
    job_id = str(_u.uuid4())
    _SUBMIT_JOBS[job_id] = {"status": "pending", "case": None, "error": None}
    _persist_job(job_id, "pending", None, None)
    _th.Thread(
        target=_async_worker,
        args=(job_id, DB_URL, _BROKER, body, str(claims.tenant_id), claims.sub, idempotency_key, {}),
        daemon=True,
        name=f"sc003-submit-{job_id[:8]}",
    ).start()
    return {"job_id": job_id, "status": "pending"}


@_v1.get("/shipment-exceptions/submit-status/{job_id}")
def get_submit_status(job_id: str, claims=Depends(get_claims)):
    """Poll after submit-async until status='done' or 'error'."""
    job = _SUBMIT_JOBS.get(job_id) or _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    if job_id not in _SUBMIT_JOBS:
        _SUBMIT_JOBS[job_id] = job
    return job


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

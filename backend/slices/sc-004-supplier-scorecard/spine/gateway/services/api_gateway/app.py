"""
SC-004 Gateway — FastAPI application for Supplier Performance Scorecard.
Port: 8030

Routes:
  GET  /health
  GET  /scorecards/carriers              — distinct carriers with claims data
  POST /scorecards/compute               — compute + persist a scorecard
  GET  /scorecards                       — paginated list of scorecards
  GET  /scorecards/{id}                  — single scorecard with sub-score breakdown

All mutating routes require:
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant-uuid>
  Idempotency-Key: <client-uuid>
"""
import os
from dotenv import load_dotenv
import paths  # noqa: F401 — must be first

load_dotenv()

from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from services.api_gateway.auth   import get_claims
from services.api_gateway.models import (
    ComputeScorecardRequest, UIProposalRequest, UIDecideRequest,
)
from services.scorecard_svc.handler import ScorecardHandler
from services.governance_svc.handler import GovernanceHandler
from shared.db import DB_URL
from middleware.oidc.claims import ZoikoClaims

_DB_URL          = os.getenv("DB_URL", DB_URL)
TENANT_SLUG      = os.getenv("TENANT_SLUG", "default")
KAFKA_BOOTSTRAP  = os.getenv("KAFKA_BOOTSTRAP", "").strip()


def _make_broker():
    from kafka.mock_kafka import MockKafkaBroker
    return MockKafkaBroker()


_BROKER = _make_broker()

app = FastAPI(
    title="Zoiko SC-004 — Supplier Performance Scorecard",
    version="1.0.0",
    description="Auto-computed carrier performance metrics from SC-002 claims and SC-003 SLA data",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
@app.get("/v1/health", tags=["system"], include_in_schema=False)
def health():
    return {"status": "ok", "service": "sc004-scorecard", "version": "1.0.0"}


# ── Scorecard routes ───────────────────────────────────────────────────────────

@app.get("/v1/scorecards/carriers", tags=["scorecards"])
@app.get("/scorecards/carriers",    tags=["scorecards"], include_in_schema=False)
def list_carriers(claims: ZoikoClaims = Depends(get_claims)):
    """List distinct carrier IDs that have claims data for this tenant."""
    handler = ScorecardHandler(_DB_URL)
    return handler.list_carriers(str(claims.tenant_id))


@app.post("/v1/scorecards/compute", status_code=201, tags=["scorecards"])
@app.post("/scorecards/compute",    status_code=201, tags=["scorecards"], include_in_schema=False)
def compute_scorecard(
    body:   ComputeScorecardRequest,
    claims: ZoikoClaims = Depends(get_claims),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Compute and persist a supplier performance scorecard for a carrier over a period."""
    now          = datetime.now(timezone.utc)
    period_end   = now
    period_start = now - timedelta(days=body.period_days)

    handler = ScorecardHandler(_DB_URL)
    return handler.compute(
        str(claims.tenant_id),
        body.carrier_id,
        period_start,
        period_end,
        body.contracted_threshold,
    )


@app.get("/v1/scorecards", tags=["scorecards"])
@app.get("/scorecards",    tags=["scorecards"], include_in_schema=False)
def list_scorecards(
    carrier_id: str | None = None,
    limit:  int = 50,
    offset: int = 0,
    claims: ZoikoClaims = Depends(get_claims),
):
    """List all scorecard periods for the tenant, optionally filtered by carrier."""
    handler = ScorecardHandler(_DB_URL)
    return handler.list_scorecards(str(claims.tenant_id), carrier_id, limit, offset)


@app.get("/v1/scorecards/{scorecard_id}", tags=["scorecards"])
@app.get("/scorecards/{scorecard_id}",    tags=["scorecards"], include_in_schema=False)
def get_scorecard(
    scorecard_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """Fetch a single scorecard with sub-score breakdown, raw metrics, and recent claims."""
    handler = ScorecardHandler(_DB_URL)
    return handler.get_scorecard(str(claims.tenant_id), scorecard_id)


# ── Governance ─────────────────────────────────────────────────────────────────

@app.post("/v1/scorecards/{scorecard_id}/propose", status_code=201, tags=["governance"])
@app.post("/scorecards/{scorecard_id}/propose",    status_code=201, tags=["governance"], include_in_schema=False)
def propose(
    scorecard_id: str,
    body: UIProposalRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    """Analyst proposes flagging the carrier for review (breach recovery).
    Requires finding_id, amount, currency. Advances case to APPROVAL_PENDING."""
    sc = ScorecardHandler(_DB_URL).get_scorecard(str(claims.tenant_id), scorecard_id)
    if not sc.get("case_id"):
        raise HTTPException(status_code=422, detail="No governed case on this scorecard — breach may not have been detected")
    case_id = sc["case_id"]
    return GovernanceHandler(_DB_URL, _BROKER, TENANT_SLUG).propose(
        tenant_id  = str(claims.tenant_id),
        case_id    = case_id,
        finding_id = body.finding_id,
        amount     = body.amount,
        currency   = body.currency,
        actor_sub  = claims.sub,
    )


@app.post("/v1/scorecards/{scorecard_id}/decide", tags=["governance"])
@app.post("/scorecards/{scorecard_id}/decide",    tags=["governance"], include_in_schema=False)
def decide(
    scorecard_id: str,
    body: UIDecideRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    """Manager approves or rejects the carrier flag. SoD: actor ≠ proposer."""
    if body.decision not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=422, detail="decision must be APPROVE or REJECT")
    sc = ScorecardHandler(_DB_URL).get_scorecard(str(claims.tenant_id), scorecard_id)
    if not sc.get("case_id"):
        raise HTTPException(status_code=422, detail="No governed case on this scorecard")
    case_id = sc["case_id"]
    return GovernanceHandler(_DB_URL, _BROKER, TENANT_SLUG).decide(
        tenant_id = str(claims.tenant_id),
        case_id   = case_id,
        task_id   = body.task_id,
        actor_sub = claims.sub,
        decision  = body.decision,
        note      = body.note or "",
    )

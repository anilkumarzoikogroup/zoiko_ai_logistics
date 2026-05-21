"""
API Gateway — FastAPI application for Phase 3.

Routes:
  GET  /health
  POST /evidence/{case_id}/items               (add evidence item)
  GET  /evidence/{case_id}/bundle              (get bundle info)
  POST /reasoning/{case_id}/analyze            (analyze + propose)
  POST /governance/tasks                       (create approval task)
  PATCH /governance/tasks/{task_id}/decide     (approve / reject)
  POST /tokens/mint                            (mint governance token)

All mutating routes require:
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant-uuid>
"""
import base64, os
import paths  # noqa: F401 — must be first

from fastapi import FastAPI, Depends, HTTPException

from services.api_gateway.auth   import get_claims
from services.api_gateway.models import (
    HealthResponse,
    AddEvidenceRequest, AddEvidenceResponse,
    GetBundleResponse,
    AnalyzeRequest, AnalyzeResponse,
    CreateTaskRequest, CreateTaskResponse,
    DecideRequest, DecideResponse,
    MintTokenRequest, MintTokenResponse,
)
from services.evidence_svc.handler   import EvidenceHandler
from services.reasoning_svc.handler  import ReasoningHandler
from services.governance_svc.handler import GovernanceHandler
from services.token_svc.handler      import TokenHandler
from middleware.oidc.claims import ZoikoClaims

DB_URL      = os.getenv("DB_URL",      "postgresql://postgres:1234@localhost/zoiko")
TENANT_SLUG = os.getenv("TENANT_SLUG", "default")

from kafka.mock_kafka import MockKafkaBroker as _MockBroker
_BROKER = _MockBroker()

app = FastAPI(title="Zoiko Logistics API Gateway", version="3.0.0")

_evidence   = EvidenceHandler(DB_URL, _BROKER, TENANT_SLUG)
_reasoning  = ReasoningHandler(DB_URL, _BROKER, TENANT_SLUG)
_governance = GovernanceHandler(DB_URL, _BROKER, TENANT_SLUG)
_tokens     = TokenHandler(DB_URL, _BROKER, TENANT_SLUG)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health():
    return HealthResponse(status="ok", service="api-gateway", version="3.0.0")


# ── Evidence ──────────────────────────────────────────────────────────────────

@app.post(
    "/evidence/{case_id}/items",
    response_model=AddEvidenceResponse,
    status_code=201,
    tags=["evidence"],
)
def add_evidence_item(
    case_id: str,
    body: AddEvidenceRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        content_bytes = base64.b64decode(body.content_b64)
    except Exception:
        raise HTTPException(status_code=422, detail="content_b64 is not valid base64")
    try:
        result = _evidence.add_item(
            tenant_id     = str(claims.tenant_id),
            case_id       = case_id,
            item_type     = body.item_type,
            content_bytes = content_bytes,
            entity_id     = body.entity_id,
            actor_sub     = claims.sub,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return AddEvidenceResponse(
        item_id     = str(result.item_id),
        bundle_id   = str(result.bundle_id),
        item_type   = result.item_type,
        item_hash   = result.item_hash,
        bundle_hash = result.bundle_hash,
        tenant_id   = result.tenant_id,
    )


@app.get("/evidence/{case_id}/bundle", response_model=GetBundleResponse, tags=["evidence"])
def get_evidence_bundle(
    case_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _evidence.get_bundle(
            tenant_id = str(claims.tenant_id),
            case_id   = case_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return GetBundleResponse(
        bundle_id   = str(result.bundle_id),
        case_id     = result.case_id,
        bundle_hash = result.bundle_hash,
        item_count  = result.item_count,
        tenant_id   = result.tenant_id,
    )


# ── Reasoning ─────────────────────────────────────────────────────────────────

@app.post(
    "/reasoning/{case_id}/analyze",
    response_model=AnalyzeResponse,
    status_code=201,
    tags=["reasoning"],
)
def analyze(
    case_id: str,
    body: AnalyzeRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _reasoning.analyze(
            tenant_id       = str(claims.tenant_id),
            case_id         = case_id,
            bundle_id       = body.bundle_id,
            proposer_sub    = body.proposer_sub,
            proposed_action = body.proposed_action,
            amount          = body.amount,
            currency        = body.currency,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return AnalyzeResponse(
        finding_id      = str(result.finding_id),
        proposal_id     = str(result.proposal_id),
        confidence      = result.confidence,
        proposed_action = result.proposed_action,
        amount          = result.amount,
        currency        = result.currency,
        tenant_id       = result.tenant_id,
    )


# ── Governance ────────────────────────────────────────────────────────────────

@app.post(
    "/governance/tasks",
    response_model=CreateTaskResponse,
    status_code=201,
    tags=["governance"],
)
def create_governance_task(
    body: CreateTaskRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _governance.create_task(
            tenant_id    = str(claims.tenant_id),
            proposal_id  = body.proposal_id,
            proposer_sub = body.proposer_sub,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return CreateTaskResponse(
        task_id      = str(result.task_id),
        proposal_id  = result.proposal_id,
        proposer_sub = result.proposer_sub,
        status       = result.status,
        tenant_id    = result.tenant_id,
    )


@app.patch(
    "/governance/tasks/{task_id}/decide",
    response_model=DecideResponse,
    tags=["governance"],
)
def decide_governance_task(
    task_id: str,
    body: DecideRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _governance.decide(
            tenant_id = str(claims.tenant_id),
            task_id   = task_id,
            actor_sub = body.actor_sub,
            outcome   = body.outcome,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return DecideResponse(
        decision_id   = str(result.decision_id),
        task_id       = result.task_id,
        outcome       = result.outcome,
        actor_sub     = result.actor_sub,
        decision_hash = result.decision_hash,
        tenant_id     = result.tenant_id,
    )


# ── Token ─────────────────────────────────────────────────────────────────────

@app.post("/tokens/mint", response_model=MintTokenResponse, status_code=201, tags=["tokens"])
def mint_token(
    body: MintTokenRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _tokens.mint(
            tenant_id   = str(claims.tenant_id),
            decision_id = body.decision_id,
            case_id     = body.case_id,
            scope       = body.scope,
            actor_sub   = body.actor_sub,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return MintTokenResponse(
        token_id       = str(result.token_id),
        decision_id    = result.decision_id,
        case_id        = result.case_id,
        scope          = result.scope,
        status         = result.status,
        token_hash     = result.token_hash,
        tenant_binding = result.tenant_binding,
        expires_at     = result.expires_at.isoformat(),
        tenant_id      = result.tenant_id,
    )

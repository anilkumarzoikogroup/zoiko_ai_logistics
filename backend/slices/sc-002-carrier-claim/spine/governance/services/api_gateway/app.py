import base64, os, uuid as _uuid_lib
from dotenv import load_dotenv
import paths  # noqa: F401 — must be first

load_dotenv()

from fastapi import FastAPI, APIRouter, Depends, HTTPException

from services.api_gateway.auth   import get_claims
from services.api_gateway.models import (
    HealthResponse,
    AddEvidenceRequest, AddEvidenceResponse,
    GetBundleResponse, SealBundleResponse,
    AnalyzeRequest, AnalyzeResponse,
    GetFindingsResponse,
    CreateTaskRequest, CreateTaskResponse,
    DecideRequest, DecideResponse,
    MintTokenRequest, MintTokenResponse,
)
from services.evidence_svc.handler   import EvidenceHandler
from services.reasoning_svc.handler  import ReasoningHandler
from services.governance_svc.handler import GovernanceHandler
from services.token_svc.handler      import TokenHandler
from middleware.oidc.claims import ZoikoClaims

DB_URL      = os.getenv("DB_URL")
TENANT_SLUG = os.getenv("TENANT_SLUG", "default")

from kafka.mock_kafka import MockKafkaBroker as _MockBroker
_BROKER = _MockBroker()

app = FastAPI(title="Zoiko Logistics API Gateway", version="3.0.0")

try:
    from zoiko_common.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)
except ImportError:
    pass

_evidence   = EvidenceHandler(DB_URL, _BROKER, TENANT_SLUG)
_reasoning  = ReasoningHandler(DB_URL, _BROKER, TENANT_SLUG)
_governance = GovernanceHandler(DB_URL, _BROKER, TENANT_SLUG)
_tokens     = TokenHandler(DB_URL, _BROKER, TENANT_SLUG)

v1_router = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["ops"])
@app.get("/v1/health", response_model=HealthResponse, tags=["ops"], include_in_schema=False)
def health():
    return HealthResponse(status="ok", service="api-gateway", version="3.0.0")


# ── Evidence ──────────────────────────────────────────────────────────────────

@v1_router.post(
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
    if body.entity_id:
        try:
            entity_uuid = _uuid_lib.UUID(str(body.entity_id))
        except ValueError:
            entity_uuid = _uuid_lib.uuid5(_uuid_lib.NAMESPACE_URL, str(body.entity_id))
    else:
        entity_uuid = None
    try:
        result = _evidence.add_item(
            tenant_id     = str(claims.tenant_id),
            case_id       = case_id,
            item_type     = body.item_type,
            content_bytes = content_bytes,
            entity_id     = entity_uuid,
            actor_sub     = claims.sub,
        )
    except Exception as e:
        import logging
        logging.getLogger("zoiko.evidence").error("add_evidence_item failed for case %s: %s", case_id, e)
        raise HTTPException(status_code=422, detail="Failed to add evidence item")
    return AddEvidenceResponse(
        item_id     = str(result.item_id),
        bundle_id   = str(result.bundle_id),
        item_type   = result.item_type,
        item_hash   = result.item_hash,
        bundle_hash = result.bundle_hash,
        tenant_id   = result.tenant_id,
    )


@v1_router.get("/evidence/{case_id}/bundle", response_model=GetBundleResponse, tags=["evidence"])
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
        bundle_id           = str(result.bundle_id),
        case_id             = result.case_id,
        bundle_hash         = result.bundle_hash,
        item_count          = result.item_count,
        tenant_id           = result.tenant_id,
        completeness_status = result.completeness_status,
    )


@v1_router.post(
    "/evidence/{case_id}/bundle/seal",
    response_model=SealBundleResponse,
    tags=["evidence"],
)
def seal_evidence_bundle(
    case_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """Seal (mark COMPLETE) the evidence bundle for a case.
    Reasoning is blocked until this is called — T-006 enforcement."""
    try:
        result = _evidence.seal_bundle(
            tenant_id = str(claims.tenant_id),
            case_id   = case_id,
            actor_sub = claims.sub,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return SealBundleResponse(
        bundle_id           = str(result.bundle_id),
        case_id             = result.case_id,
        bundle_hash         = result.bundle_hash,
        item_count          = result.item_count,
        completeness_status = result.completeness_status,
        tenant_id           = result.tenant_id,
    )


# ── Reasoning ─────────────────────────────────────────────────────────────────

@v1_router.post(
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
            carrier         = body.carrier,        # ← NEW
            route           = body.route,          # ← NEW
            contract_rate   = body.contract_rate,  # ← NEW
        )
    except Exception as e:
        import logging
        logging.getLogger("zoiko.reasoning").error("analyze failed for case %s: %s", case_id, e)
        raise HTTPException(status_code=422, detail="Analysis failed — check inputs and try again")
    return AnalyzeResponse(
        finding_id      = str(result.finding_id),
        proposal_id     = str(result.proposal_id),
        confidence      = result.confidence,
        proposed_action = result.proposed_action,
        amount          = result.amount,
        currency        = result.currency,
        tenant_id       = result.tenant_id,
    )


@v1_router.get(
    "/reasoning/{case_id}/findings",
    response_model=GetFindingsResponse,
    tags=["reasoning"],
)
def get_findings(
    case_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Retrieve all AI-generated findings and decision proposals for a given case.
    Returns every finding joined with its latest decision proposal so the caller
    can inspect confidence scores, risk levels, AI reasoning, and proposed action
    without re-running the analysis.
    """
    try:
        result = _reasoning.get_findings(
            tenant_id = str(claims.tenant_id),
            case_id   = case_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import logging
        logging.getLogger("zoiko.reasoning").error("get_findings failed for case %s: %s", case_id, e)
        raise HTTPException(status_code=500, detail="Internal error retrieving findings")
    return GetFindingsResponse(
        case_id   = case_id,
        tenant_id = str(claims.tenant_id),
        findings  = result,
    )


# ── Governance ────────────────────────────────────────────────────────────────

@v1_router.post(
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
        import logging
        logging.getLogger("zoiko.governance").error("create_task failed: %s", e)
        raise HTTPException(status_code=422, detail="Failed to create governance task")
    return CreateTaskResponse(
        task_id      = str(result.task_id),
        proposal_id  = result.proposal_id,
        proposer_sub = result.proposer_sub,
        status       = result.status,
        tenant_id    = result.tenant_id,
    )


@v1_router.patch(
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
        import logging
        logging.getLogger("zoiko.governance").error("decide_task %s failed: %s", task_id, e)
        raise HTTPException(status_code=500, detail="Internal error processing decision")
    return DecideResponse(
        decision_id   = str(result.decision_id) if result.decision_id is not None else None,
        task_id       = result.task_id,
        outcome       = result.outcome,
        actor_sub     = result.actor_sub,
        decision_hash = result.decision_hash,
        tenant_id     = result.tenant_id,
    )


# ── Token ─────────────────────────────────────────────────────────────────────

@v1_router.post("/tokens/mint", response_model=MintTokenResponse, status_code=201, tags=["tokens"])
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
        import logging
        logging.getLogger("zoiko.tokens").error("mint_token failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal error minting token")
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


# ── Route registration ────────────────────────────────────────────────────────
app.include_router(v1_router, prefix="/v1")
app.include_router(v1_router)
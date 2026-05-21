from pydantic import BaseModel
from typing import Optional


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:  str
    service: str
    version: str


# ── Evidence ──────────────────────────────────────────────────────────────────

class AddEvidenceRequest(BaseModel):
    item_type:     str          # e.g. "BOL", "POD", "RATE_SHEET", "PHOTO"
    content_b64:   str          # base64-encoded raw bytes
    entity_id:     Optional[str] = None


class AddEvidenceResponse(BaseModel):
    item_id:     str
    bundle_id:   str
    item_type:   str
    item_hash:   str
    bundle_hash: str
    tenant_id:   str


class GetBundleResponse(BaseModel):
    bundle_id:   str
    case_id:     str
    bundle_hash: str
    item_count:  int
    tenant_id:   str


# ── Reasoning ─────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    bundle_id:       str
    proposer_sub:    str
    proposed_action: str  = "CREDIT_MEMO"
    amount:          float = 0.0
    currency:        str   = "USD"


class AnalyzeResponse(BaseModel):
    finding_id:      str
    proposal_id:     str
    confidence:      float
    proposed_action: str
    amount:          float
    currency:        str
    tenant_id:       str


# ── Governance ────────────────────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    proposal_id:  str
    proposer_sub: str


class CreateTaskResponse(BaseModel):
    task_id:      str
    proposal_id:  str
    proposer_sub: str
    status:       str
    tenant_id:    str


class DecideRequest(BaseModel):
    actor_sub: str
    outcome:   str    # "APPROVED" | "REJECTED"


class DecideResponse(BaseModel):
    decision_id:   str
    task_id:       str
    outcome:       str
    actor_sub:     str
    decision_hash: str
    tenant_id:     str


# ── Token ─────────────────────────────────────────────────────────────────────

class MintTokenRequest(BaseModel):
    decision_id: str
    case_id:     str
    scope:       str  = "EXECUTE_CREDIT_MEMO"
    actor_sub:   str  = "system"


class MintTokenResponse(BaseModel):
    token_id:       str
    decision_id:    str
    case_id:        str
    scope:          str
    status:         str
    token_hash:     str
    tenant_binding: str
    expires_at:     str
    tenant_id:      str

from pydantic import BaseModel, Field
from typing import List, Optional


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    str
    password: str

class LoginResponse(BaseModel):
    token:      str
    tenant_id:  str
    role:       str
    full_name:  str
    email:      str
    expires_in: int   # seconds

class RegisterRequest(BaseModel):
    email:     str
    password:  str
    full_name: str
    role:      str    # analyst | manager | admin

class RegisterResponse(BaseModel):
    user_id:    str
    email:      str
    full_name:  str
    role:       str
    tenant_id:  str
    created_at: str

class UserItem(BaseModel):
    user_id:    str
    email:      str
    full_name:  str
    role:       str
    is_active:  bool
    created_at: str

class UsersListResponse(BaseModel):
    tenant_id: str
    users:     List[UserItem]


# ── Requests ──────────────────────────────────────────────────────────────────

class InvoiceRequest(BaseModel):
    carrier_id:        str
    invoice_number:    str
    total_amount:      float
    currency:          str   = "USD"
    route_origin:      str
    route_destination: str
    weight_lbs:        float = 0.0


class ValidateRequest(BaseModel):
    invoice_number: str
    carrier_id:     str
    total_amount:   float
    currency:       str = "USD"


class CanonicalizeRequest(BaseModel):
    invoice_number: str
    carrier_id:     str
    total_amount:   float
    currency:       str   = "USD"
    origin_city:    str
    dest_city:      str
    weight_lbs:     float = 0.0


class OpenCaseRequest(BaseModel):
    canonical_invoice_id: str


class TransitionRequest(BaseModel):
    new_state:  str
    actor_sub:  str
    version:    int | None = None   # OCC: if provided, must match cases.version (T-016)
    payload:    dict = Field(default_factory=dict)


# ── Responses ─────────────────────────────────────────────────────────────────

class InvoiceResponse(BaseModel):
    source_record_id: str
    canonical_hash:   str
    idempotency_key:  str
    tenant_id:        str


class ValidateResponse(BaseModel):
    validation_id:    str
    status:           str
    overcharge_amount: float
    violations:       int
    currency:         str


class CanonicalizeResponse(BaseModel):
    canonical_invoice_id:  str
    canonical_shipment_id: str
    canonical_hash:        str
    invoice_number:        str


class OpenCaseResponse(BaseModel):
    case_id:   str
    state:     str
    is_new:    bool
    tenant_id: str


class TransitionResponse(BaseModel):
    case_id:   str
    new_state: str


class HealthResponse(BaseModel):
    status:  str
    service: str
    version: str


# ── Frontend UI request models ─────────────────────────────────────────────────

class SubmitCaseRequest(BaseModel):
    carrier:  str
    route:    str
    amount:   float
    currency: str = "INR"


class UIProposalRequest(BaseModel):
    action:   str   = "EXECUTE_CREDIT_MEMO"
    amount:   float
    currency: str   = "INR"


class UIDecideRequest(BaseModel):
    decision: str        # "APPROVED" | "REJECTED"
    note:     str = ""


class ContractRateRequest(BaseModel):
    carrier_id:   str
    rate_type:    str   = "FUEL_CHARGE"
    rate_value:   float
    currency:     str   = "INR"
    effective_on: str   = "2025-01-01"   # ISO date string
    expires_on:   str | None = None


# ── Execution request ─────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    token_id: str
    case_id:  Optional[str]   = None
    amount:   Optional[float] = 0.0
    currency: Optional[str]   = "INR"


# ── Tenant admin models ────────────────────────────────────────────────────────

class TenantCreateRequest(BaseModel):
    display_name:   str
    slug:           str
    admin_email:    str
    admin_name:     str
    admin_password: str

class TenantItem(BaseModel):
    tenant_id:    str
    display_name: str
    slug:         str
    status:       str
    user_count:   int
    created_at:   str

class TenantsListResponse(BaseModel):
    tenants: List[TenantItem]
    total:   int


# ── Phase-4 Execution / Reconciliation / ACR models ──────────────────────────

class ExecuteResponse(BaseModel):
    envelope_id:   str
    token_id:      str
    case_id:       str
    status:        str
    connector_ref: str
    dispatched_at: str

class ReconcileRequest(BaseModel):
    envelope_id: str
    actor_sub:   str = "system"

class ReconcileResponse(BaseModel):
    reconciliation_id: str
    envelope_id:       str
    status:            str
    delta:             float
    reconciled_at:     str

class ACRResponse(BaseModel):
    acr_id:         str
    case_id:        str
    merkle_root:    str
    artifact_count: int
    is_locked:      bool
    issued_at:      str
    verify_bundle:  dict

class VarianceRecord(BaseModel):
    id:             str
    case_id:        str
    tenant_id:      str
    variance_type:  str
    expected_value: Optional[float]
    actual_value:   Optional[float]
    delta:          Optional[float]
    status:         str
    resolved_by:    Optional[str]
    resolved_at:    Optional[str]
    created_at:     str

class ResolveVarianceRequest(BaseModel):
    action:      str
    resolved_by: str

class ResolveVarianceResponse(BaseModel):
    id:          str
    case_id:     str
    status:      str
    resolved_by: str
    resolved_at: str


# ── Phase-3 Evidence / Reasoning / Governance / Token models ─────────────────

class AddEvidenceRequest(BaseModel):
    item_type:   str
    content_b64: str
    entity_id:   Optional[str] = None

class AddEvidenceResponse(BaseModel):
    item_id:     str
    bundle_id:   str
    item_type:   str
    item_hash:   str
    bundle_hash: str
    tenant_id:   str

class GetBundleResponse(BaseModel):
    bundle_id:           str
    case_id:             str
    bundle_hash:         str
    item_count:          int
    tenant_id:           str
    completeness_status: str = "INCOMPLETE"

class SealBundleResponse(BaseModel):
    bundle_id:           str
    case_id:             str
    bundle_hash:         str
    item_count:          int
    completeness_status: str
    tenant_id:           str

class AnalyzeRequest(BaseModel):
    bundle_id:       str
    proposer_sub:    str
    proposed_action: str   = "CREDIT_MEMO"
    amount:          float = 0.0
    currency:        str   = "USD"
    carrier:         str   = ""
    route:           str   = ""
    contract_rate:   float = 0.0

class AnalyzeResponse(BaseModel):
    finding_id:      str
    proposal_id:     str
    confidence:      float
    proposed_action: str
    amount:          float
    currency:        str
    tenant_id:       str

class FindingItem(BaseModel):
    finding_id:      str
    bundle_id:       str
    confidence:      float
    ai_confidence:   Optional[float] = None
    risk_level:      Optional[str]   = None
    ai_reasoning:    Optional[str]   = None
    proposed_action: str
    amount:          float
    currency:        str
    created_at:      Optional[str]   = None

class GetFindingsResponse(BaseModel):
    case_id:   str
    tenant_id: str
    findings:  List[FindingItem]

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
    outcome:   str

class DecideResponse(BaseModel):
    decision_id:   Optional[str] = None
    task_id:       str
    outcome:       str
    actor_sub:     str
    decision_hash: str
    tenant_id:     str

class MintTokenRequest(BaseModel):
    decision_id: str
    case_id:     str
    scope:       str = "EXECUTE_CREDIT_MEMO"
    actor_sub:   str = "system"

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

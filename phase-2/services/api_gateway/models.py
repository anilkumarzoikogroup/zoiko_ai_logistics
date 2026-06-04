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
    carrier:        str
    route:          str
    amount:         float
    currency:       str   = "INR"
    invoice_number: str   = ""   # Optional — if blank, server generates UI-XXXXXXXX


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

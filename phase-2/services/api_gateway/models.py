from pydantic import BaseModel, Field


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

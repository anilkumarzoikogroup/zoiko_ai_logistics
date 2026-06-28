"""SC-003 API gateway request/response models."""
from pydantic import BaseModel, Field
from typing import Optional


class ShipmentEventItem(BaseModel):
    event_type:       str
    event_timestamp:  str         # ISO-8601
    location:        Optional[str] = None
    description:     Optional[str] = None


class ShipmentExceptionSubmitRequest(BaseModel):
    carrier:              str = Field(..., description="Carrier ID (e.g. BLUEDART, DELHIVERY)")
    shipment_reference:   str = Field(..., description="AWB / tracking number — dedup key")
    committed_eta:        str = Field(..., description="ISO-8601 datetime — carrier's delivery promise")
    actual_delivery:      str = Field(..., description="ISO-8601 datetime — when shipment arrived")
    origin:               str = Field(..., description="Origin city / hub")
    destination:          str = Field(..., description="Destination city / hub")
    penalty_rate_per_hour: float = Field(..., gt=0, description="Contract penalty per breach hour")
    penalty_cap:          float = Field(10_000.0, description="Maximum claimable penalty amount")
    currency:             str = Field("INR", description="ISO-4217 currency code")
    description:         Optional[str] = None
    event_stream:        list[ShipmentEventItem] = Field(default_factory=list)


class UIProposalRequest(BaseModel):
    finding_id: str
    amount:     float
    currency:   str = "INR"
    note:      Optional[str] = None


class UIDecideRequest(BaseModel):
    task_id:  str
    decision: str    # "APPROVE" | "REJECT"
    note:    Optional[str] = None


class ShipmentExceptionResponse(BaseModel):
    id:                 str
    tenant_id:          str
    state:              str
    case_type:          str = "SHIPMENT_EXCEPTION"
    carrier:            str
    shipment_reference: str
    committed_eta:     Optional[str] = None
    actual_delivery:   Optional[str] = None
    sla_breach_hours:  Optional[float] = None
    sla_penalty_amount: Optional[float] = None
    currency:           str
    confidence:         float = 0.0
    opened_at:          str
    updated_at:         str
    duplicate:          bool = False

"""SC-003 Execution Gateway — request/response models."""
from pydantic import BaseModel, Field
from typing import Optional


class ExecuteRequest(BaseModel):
    case_id:  str = Field(..., description="UUID of the shipment exception case")
    token_id: str = Field(..., description="Governance token UUID")
    action:   str = Field("ISSUE_SLA_CREDIT", description="Execution action")
    metadata: Optional[dict] = None


class ReconcileRequest(BaseModel):
    case_id:     str = Field(..., description="UUID of the shipment exception case")
    envelope_id: str = Field(..., description="Execution envelope UUID from /execute")


class ResolveVarianceRequest(BaseModel):
    resolution: str = Field(..., description="RESOLVED or WAIVED")
    note:       Optional[str] = ""


class IssueACRRequest(BaseModel):
    case_id:     str = Field(..., description="UUID of the shipment exception case")
    envelope_id: str = Field(..., description="Execution envelope UUID")

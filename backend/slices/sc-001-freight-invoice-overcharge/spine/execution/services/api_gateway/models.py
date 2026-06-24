from __future__ import annotations
from pydantic import BaseModel
from typing import Optional


class HealthResponse(BaseModel):
    status:  str
    service: str
    version: str


class ExecuteRequest(BaseModel):
    token_id:  str
    actor_sub: str


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
    acr_id:        str
    case_id:       str
    merkle_root:   str
    artifact_count: int
    is_locked:     bool
    issued_at:     str
    verify_bundle: dict


class VarianceRecord(BaseModel):
    id:             str
    case_id:        str
    tenant_id:      str
    variance_type:  str
    expected_value: Optional[float]
    actual_value:   Optional[float]
    delta:          Optional[float]
    status:         str           # OPEN | RESOLVED | WAIVED
    resolved_by:    Optional[str]
    resolved_at:    Optional[str]
    created_at:     str


class ResolveVarianceRequest(BaseModel):
    action:      str   # "RESOLVE" | "WAIVE"
    resolved_by: str   # actor_sub of the person resolving


class ResolveVarianceResponse(BaseModel):
    id:          str
    case_id:     str
    status:      str
    resolved_by: str
    resolved_at: str

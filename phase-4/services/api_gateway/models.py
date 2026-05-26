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

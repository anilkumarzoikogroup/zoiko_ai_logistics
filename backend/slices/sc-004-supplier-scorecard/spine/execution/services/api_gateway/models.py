"""Pydantic models for SC-004 execution API."""
from typing import Optional
from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    case_id:    str
    token_id:   str
    actor_sub:  str
    action:     str = "NOTIFY_FLAG"
    metadata:   Optional[dict] = None


class ReconcileRequest(BaseModel):
    case_id:     str
    envelope_id: str
    actor_sub:   str


class ResolveVarianceRequest(BaseModel):
    resolution: str
    note:       Optional[str] = None
    actor_sub:  str


class IssueACRRequest(BaseModel):
    actor_sub: str

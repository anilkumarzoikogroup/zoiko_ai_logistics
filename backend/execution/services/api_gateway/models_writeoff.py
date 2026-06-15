"""Pydantic request/response models — Phase 6 / Clarification 06 Slice 1.

Write-Off Workflow API models.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class WriteOffCreateRequest(BaseModel):
    expected_recovery_id:            str
    reason_code:                     str
    amount:                          Optional[float] = None


class RejectWriteOffRequest(BaseModel):
    reason:                          str = ""


class WriteOffResponse(BaseModel):
    write_off_id:                    str
    tenant_id:                        str
    case_id:                          str
    expected_recovery_id:             str
    amount:                           float
    currency:                         str
    reason_code:                      str
    policy_version_id:                str
    authorized_by:                    Optional[str] = None
    authorized_at:                    Optional[str] = None
    ledger_entry_id:                  Optional[str] = None
    status:                           str
    created_at:                       str

"""Pydantic response models — Phase 6 / Clarification 06 Slice 1.

Recovery exceptions / observability API models.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class RecoveryExceptionResponse(BaseModel):
    exception_type:                   str
    tenant_id:                        str
    case_id:                           str
    expected_recovery_id:              str
    recovery_match_id:                 Optional[str] = None
    status:                            str
    amount:                            float
    currency:                          str
    age_days:                          int
    detail:                            str
    detected_at:                       str

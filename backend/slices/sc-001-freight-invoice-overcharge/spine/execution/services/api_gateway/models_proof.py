"""Pydantic request/response models — Phase 6 / Clarification 06 Slice 1.

Recovery Proof / ACR Readiness API models.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class GenerateProofRequest(BaseModel):
    case_id:                          str


class RecoveryProofResponse(BaseModel):
    proof_id:                         str
    tenant_id:                         str
    case_id:                           str
    claimed_amount:                    float
    currency:                          str
    expected_recovery_ids:             list[str]
    recovery_instrument_ids:           list[str]
    recovery_match_ids:                list[str]
    ledger_entry_ids:                  list[str]
    total_expected:                    float
    total_recovered:                   float
    total_unrecovered:                 float
    recovery_status:                   str
    ledger_status:                     str
    acr_ready:                         bool
    superseded_by:                     Optional[str] = None
    created_at:                        str

"""Pydantic request/response models — Phase 6 / Clarification 06 Slice 1.

Expected Recovery + Recovery Instrument API models.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


# ── Expected Recovery ─────────────────────────────────────────────────────────

class ExpectedRecoveryCreateRequest(BaseModel):
    case_id:                        str
    expected_amount:                float
    currency:                       str = "INR"
    expected_recovery_method:       str = "carrier_credit_memo"
    counterparty_type:               str = "carrier"
    counterparty_id:                  Optional[str] = None
    expected_invoice_id:              Optional[str] = None
    expected_external_invoice_ref:    Optional[str] = None
    authorization_decision_id:        Optional[str] = None
    tolerance_policy_id:              str = "recovery-match-tolerance-v1"


class ExpectedRecoveryResponse(BaseModel):
    expected_recovery_id:           str
    case_id:                         str
    tenant_id:                       str
    expected_amount:                 float
    currency:                        str
    expected_recovery_method:        str
    status:                          str
    created_at:                      str


class SupersedeExpectedRecoveryRequest(BaseModel):
    expected_amount:                 float
    currency:                        Optional[str] = None
    expected_recovery_method:        Optional[str] = None
    reason:                          str = ""


# ── Recovery Instrument ────────────────────────────────────────────────────────

class RecoveryInstrumentCreateRequest(BaseModel):
    instrument_type:                 str
    instrument_amount:               float
    currency:                        str = "INR"
    counterparty_type:                str = "carrier"
    counterparty_id:                   Optional[str] = None
    related_case_id:                   Optional[str] = None
    external_reference:                Optional[str] = None
    related_external_invoice_ref:      Optional[str] = None
    instrument_date:                   Optional[str] = None
    source_record_id:                  Optional[str] = None


class RecoveryInstrumentResponse(BaseModel):
    recovery_instrument_id:          str
    tenant_id:                        str
    instrument_type:                  str
    instrument_amount:                float
    currency:                         str
    status:                           str
    related_case_id:                  Optional[str] = None
    created_by:                       str
    created_at:                       str


# ── Recovery Match ─────────────────────────────────────────────────────────────

class MatchRequest(BaseModel):
    expected_recovery_id:            str


class ReverseMatchRequest(BaseModel):
    reason:                          str = ""


class RecoveryMatchResponse(BaseModel):
    match_id:                        str
    expected_recovery_id:             str
    recovery_instrument_id:           str
    tenant_id:                         str
    match_tier:                       Optional[int] = None
    match_method:                     Optional[str] = None
    match_confidence:                 Optional[float] = None
    matched_amount:                   float
    expected_amount:                  float
    variance:                         float
    currency:                         str
    allocation_status:                str
    matched_by:                       str
    matched_at:                       str

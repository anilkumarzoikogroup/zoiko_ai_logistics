"""Pydantic request/response models — Phase 6 / Clarification 06 Slice 1.

Ledger Closure API models.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class PostLedgerEntryRequest(BaseModel):
    match_id:                        str


class ReverseLedgerEntryRequest(BaseModel):
    reason:                          str = ""


class LedgerEntryResponse(BaseModel):
    entry_id:                        str
    tenant_id:                        str
    case_id:                          str
    entry_type:                       str
    amount:                           float
    currency:                         str
    debit_account:                    str
    credit_account:                   str
    source_recovery_match_id:         Optional[str] = None
    reversal_of_entry_id:             Optional[str] = None
    status:                           str
    posted_at:                        str
    created_at:                       str

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RecoveryProofResult:
    proof_id:                str
    tenant_id:               str
    case_id:                 str
    claimed_amount:          float
    currency:                str
    expected_recovery_ids:   list[str]
    recovery_instrument_ids: list[str]
    recovery_match_ids:      list[str]
    ledger_entry_ids:        list[str]
    total_expected:          float
    total_recovered:         float
    total_unrecovered:       float
    recovery_status:         str
    ledger_status:           str
    acr_ready:               bool
    superseded_by:           Optional[str]
    created_at:              datetime

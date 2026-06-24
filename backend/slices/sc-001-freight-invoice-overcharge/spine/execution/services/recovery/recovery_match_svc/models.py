from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RecoveryMatchResult:
    match_id:                str
    expected_recovery_id:    str
    recovery_instrument_id:  str
    tenant_id:                str
    match_tier:               Optional[int]
    match_method:             Optional[str]
    match_confidence:         Optional[float]
    matched_amount:           float
    expected_amount:          float
    variance:                 float
    currency:                 str
    allocation_status:        str
    matched_by:                str
    matched_at:                datetime

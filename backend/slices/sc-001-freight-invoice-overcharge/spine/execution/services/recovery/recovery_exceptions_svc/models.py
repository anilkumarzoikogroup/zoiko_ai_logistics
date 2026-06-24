from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RecoveryExceptionResult:
    exception_type:       str   # MISMATCHED | REVIEW_REQUIRED | STUCK_PENDING
    tenant_id:            str
    case_id:              str
    expected_recovery_id: str
    recovery_match_id:    Optional[str]
    status:               str
    amount:               float
    currency:             str
    age_days:             int
    detail:               str
    detected_at:          datetime

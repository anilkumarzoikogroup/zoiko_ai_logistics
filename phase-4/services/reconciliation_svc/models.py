from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ReconciliationResult:
    reconciliation_id: str
    envelope_id:       str
    case_id:           str
    tenant_id:         str
    expected_amount:   float
    actual_amount:     float
    currency:          str
    status:            str   # MATCHED | PARTIAL | DISCREPANCY
    delta:             float
    reconciled_at:     datetime
    outcome_id:        Optional[str] = None

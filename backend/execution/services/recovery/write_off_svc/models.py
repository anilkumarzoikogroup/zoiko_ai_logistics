from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class WriteOffResult:
    write_off_id:         str
    tenant_id:            str
    case_id:              str
    expected_recovery_id: str
    amount:               float
    currency:             str
    reason_code:          str
    policy_version_id:    str
    authorized_by:        Optional[str]
    authorized_at:        Optional[datetime]
    ledger_entry_id:      Optional[str]
    status:               str
    created_at:           datetime

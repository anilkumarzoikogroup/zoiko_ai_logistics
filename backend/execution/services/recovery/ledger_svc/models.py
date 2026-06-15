from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class LedgerEntryResult:
    entry_id:                 str
    tenant_id:                str
    case_id:                  str
    entry_type:               str
    amount:                   float
    currency:                 str
    debit_account:            str
    credit_account:           str
    source_recovery_match_id: Optional[str]
    reversal_of_entry_id:     Optional[str]
    status:                   str
    posted_at:                datetime
    created_at:               datetime

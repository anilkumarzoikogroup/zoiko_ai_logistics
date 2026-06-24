from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ExpectedRecoveryCreate:
    case_id:                        str
    tenant_id:                       str
    expected_amount:                 float
    currency:                        str = "INR"
    expected_recovery_method:        str = "carrier_credit_memo"
    counterparty_type:               str = "carrier"
    counterparty_id:                  Optional[str] = None
    expected_invoice_id:              Optional[str] = None
    expected_external_invoice_ref:    Optional[str] = None
    authorization_decision_id:        Optional[str] = None
    tolerance_policy_id:              str = "recovery-match-tolerance-v1"


@dataclass
class ExpectedRecoveryResult:
    expected_recovery_id:    str
    case_id:                  str
    tenant_id:                str
    expected_amount:          float
    currency:                 str
    expected_recovery_method: str
    status:                   str
    created_at:               datetime

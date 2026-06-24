from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class RecoveryInstrumentCreate:
    tenant_id:                       str
    instrument_type:                  str
    instrument_amount:                float
    created_by:                       str
    currency:                         str = "INR"
    counterparty_type:                str = "carrier"
    counterparty_id:                   Optional[str] = None
    related_case_id:                   Optional[str] = None
    external_reference:                Optional[str] = None
    related_external_invoice_ref:      Optional[str] = None
    instrument_date:                   Optional[date] = None
    source_record_id:                  Optional[str] = None


@dataclass
class RecoveryInstrumentResult:
    recovery_instrument_id:  str
    tenant_id:                str
    instrument_type:          str
    instrument_amount:        float
    currency:                 str
    status:                   str
    related_case_id:          Optional[str]
    created_by:               str
    created_at:               datetime

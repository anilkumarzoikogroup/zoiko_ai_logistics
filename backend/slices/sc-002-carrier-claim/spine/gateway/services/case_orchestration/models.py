from dataclasses import dataclass
from uuid import UUID
from datetime import datetime


@dataclass
class CaseResult:
    case_id: UUID
    tenant_id: str
    state: str
    opened_at: datetime
    is_new: bool = True          # False if case already existed (idempotent)
    case_type: str = "CARRIER_CLAIM"
    claim_id: UUID = None

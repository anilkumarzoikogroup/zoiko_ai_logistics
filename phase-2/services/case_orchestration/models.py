from dataclasses import dataclass
from uuid import UUID
from datetime import datetime


@dataclass
class CaseResult:
    case_id: UUID
    tenant_id: str
    invoice_id: UUID
    state: str
    opened_at: datetime
    is_new: bool = True          # False if case already existed (idempotent)

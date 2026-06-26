"""SC-003 Case Orchestration models."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class CaseResult:
    case_id:      UUID
    tenant_id:    str
    state:        str
    opened_at:    datetime
    is_new:       bool = True           # False if case already existed (idempotent)
    case_type:    str  = "SHIPMENT_EXCEPTION"
    canonical_id: UUID = None           # canonical_shipment_exception UUID

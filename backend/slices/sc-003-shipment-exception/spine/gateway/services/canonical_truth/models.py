from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class CanonicalShipmentExceptionResult:
    id:                  UUID       # canonical_shipment_exceptions PK
    tenant_id:           str
    source_record_id:    UUID
    case_id:             UUID | None  # populated later by case_orchestration; None at canonical stage
    shipment_reference:  str
    carrier_id:          str
    committed_eta:       datetime
    actual_delivery:     datetime
    sla_breach_hours:    float
    penalty_amount:      float       # min(breach_hours * rate, cap)
    currency:            str
    origin:              str
    destination:         str
    canonical_hash:      str         # hex string — THE authoritative hash
    created_at:          datetime

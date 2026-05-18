from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class InvoiceInput:
    carrier_id: str
    invoice_number: str
    total_amount: float
    currency: str
    route_origin: str
    route_destination: str
    weight_lbs: float = 0.0
    line_items: dict = field(default_factory=dict)


@dataclass
class IngestResult:
    source_record_id: UUID
    canonical_hash: str          # hex string
    idempotency_key: str
    tenant_id: str

from dataclasses import dataclass
from uuid import UUID


@dataclass
class CanonicalResult:
    canonical_invoice_id: UUID
    canonical_shipment_id: UUID
    source_record_id: UUID
    tenant_id: str
    invoice_number: str
    carrier_id: str
    total_amount: float
    canonical_hash: str          # hex string — THE authoritative hash


@dataclass
class CanonicalClaimResult:
    claim_id: UUID
    source_record_id: UUID
    tenant_id: str
    claim_reference: str
    carrier_id: str
    claimed_amount: float
    canonical_hash: str          # hex string — THE authoritative hash

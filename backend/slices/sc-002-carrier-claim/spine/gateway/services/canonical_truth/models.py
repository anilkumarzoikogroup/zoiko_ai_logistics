from dataclasses import dataclass
from uuid import UUID


@dataclass
class CanonicalClaimResult:
    claim_id: UUID
    source_record_id: UUID
    tenant_id: str
    claim_reference: str
    carrier_id: str
    claimed_amount: float
    canonical_hash: str          # hex string — THE authoritative hash

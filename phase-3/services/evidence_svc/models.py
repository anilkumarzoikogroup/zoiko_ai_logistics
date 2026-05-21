from dataclasses import dataclass
import uuid
from datetime import datetime


@dataclass
class EvidenceItemResult:
    item_id:     uuid.UUID
    bundle_id:   uuid.UUID
    tenant_id:   str
    case_id:     str
    item_type:   str
    item_hash:   str        # hex SHA-256 of content
    bundle_hash: str        # hex Merkle root of all items in bundle
    added_at:    datetime


@dataclass
class EvidenceBundleResult:
    bundle_id:   uuid.UUID
    tenant_id:   str
    case_id:     str
    bundle_hash: str        # hex Merkle root
    item_count:  int
    created_at:  datetime

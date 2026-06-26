"""SC-003 Evidence Service models."""
from dataclasses import dataclass
from datetime import datetime
import uuid


@dataclass
class EvidenceItemResult:
    item_id:     uuid.UUID
    bundle_id:   uuid.UUID
    tenant_id:   str
    case_id:     str
    item_type:   str
    item_hash:   str   # hex
    bundle_hash: str   # hex
    added_at:    datetime


@dataclass
class EvidenceBundleResult:
    bundle_id:           uuid.UUID
    tenant_id:           str
    case_id:             str
    bundle_hash:         str   # hex
    item_count:          int
    completeness_status: str
    created_at:          datetime

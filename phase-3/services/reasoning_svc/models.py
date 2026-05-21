from dataclasses import dataclass
import uuid
from datetime import datetime


@dataclass
class FindingResult:
    finding_id:      uuid.UUID
    proposal_id:     uuid.UUID
    tenant_id:       str
    case_id:         str
    bundle_id:       str
    confidence:      float      # 0.96 for SC-001
    rule_trace:      dict
    proposed_action: str
    amount:          float
    currency:        str
    proposer_sub:    str
    created_at:      datetime

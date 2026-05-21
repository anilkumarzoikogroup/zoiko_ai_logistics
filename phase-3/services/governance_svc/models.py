from dataclasses import dataclass
import uuid
from datetime import datetime


@dataclass
class ApprovalTaskResult:
    task_id:      uuid.UUID
    proposal_id:  str
    tenant_id:    str
    proposer_sub: str
    status:       str           # PENDING
    created_at:   datetime


@dataclass
class GovernanceDecisionResult:
    decision_id:      uuid.UUID
    task_id:          str
    proposal_id:      str
    tenant_id:        str
    outcome:          str       # APPROVED | REJECTED
    actor_sub:        str
    decision_hash:    str       # hex
    decided_at:       datetime

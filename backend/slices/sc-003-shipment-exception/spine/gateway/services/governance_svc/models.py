from dataclasses import dataclass
import uuid
from datetime import datetime
from typing import Optional


@dataclass
class ApprovalTaskResult:
    task_id:        uuid.UUID
    proposal_id:    str
    tenant_id:      str
    proposer_sub:   str
    status:         str           # PENDING | APPROVED (AUTO)
    approval_level: str           # AUTO | SINGLE | DUAL
    created_at:     datetime


@dataclass
class GovernanceDecisionResult:
    decision_id:               Optional[uuid.UUID]  # None when awaiting second dual-auth approval
    task_id:                   str
    proposal_id:               str
    tenant_id:                 str
    outcome:                   str       # EXECUTION_READY | ABORTED | AWAITING_SECOND_APPROVAL
    actor_sub:                 str
    decision_hash:             str       # hex (empty when awaiting second approval)
    decided_at:                datetime
    awaiting_second_approval:  bool = False
    approval_chain_hash:       str = ""  # hex SHA-256(proposer||actor||decision_hash)
    policy_version:            str = "sla-penalty-policy@2026.05.01"


@dataclass
class ApprovalThreshold:
    threshold_id:         uuid.UUID
    tenant_id:            str
    currency:             str
    auto_approve_below:   Optional[float]
    dual_auth_above:      Optional[float]
    escalate_after_hours: int

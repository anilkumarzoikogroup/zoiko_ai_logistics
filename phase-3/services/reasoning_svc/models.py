from dataclasses import dataclass, field
import uuid
from datetime import datetime
from typing import Optional


@dataclass
class FindingResult:
    finding_id:         uuid.UUID
    proposal_id:        uuid.UUID
    tenant_id:          str
    case_id:            str
    bundle_id:          str
    confidence:         float      # 0.96 for SC-001
    rule_trace:         dict
    proposed_action:    str
    amount:             float
    currency:           str
    proposer_sub:       str
    created_at:         datetime
    reasoning_trace_id: Optional[uuid.UUID] = None   # set by AgentRuntime


@dataclass
class ReasoningTrace:
    trace_id:       uuid.UUID
    tenant_id:      str
    case_id:        str
    agent_id:       str
    steps:          list
    tools_used:     list
    evidence_refs:  list
    confidence:     float
    action_intent:  str
    policy_version: str
    created_at:     datetime

"""Domain constants and enumerations shared across Phase 2 services."""
from __future__ import annotations

from enum import Enum


class CaseStatus(str, Enum):
    NEW                = "NEW"
    EVIDENCE_PENDING   = "EVIDENCE_PENDING"
    FINDING_GENERATED  = "FINDING_GENERATED"
    APPROVAL_PENDING   = "APPROVAL_PENDING"
    EXECUTION_READY    = "EXECUTION_READY"
    DISPATCHED         = "DISPATCHED"
    OUTCOME_RECORDED   = "OUTCOME_RECORDED"
    CLOSED             = "CLOSED"
    ABORTED            = "ABORTED"

    # Clarification 05 — case candidate + extended lifecycle states
    CANDIDATE                  = "CANDIDATE"
    UNDER_REVIEW               = "UNDER_REVIEW"
    ACTION_PLAN_READY          = "ACTION_PLAN_READY"
    READY_FOR_AUTHORIZATION    = "READY_FOR_AUTHORIZATION"
    AUTHORIZED                 = "AUTHORIZED"
    EXECUTING                  = "EXECUTING"
    AWAITING_EXTERNAL_RESPONSE = "AWAITING_EXTERNAL_RESPONSE"
    RECONCILING                = "RECONCILING"

    # Clarification 05 — closure sub-states
    CLOSED_RECOVERED     = "CLOSED_RECOVERED"
    CLOSED_NO_ACTION     = "CLOSED_NO_ACTION"
    CLOSED_REJECTED      = "CLOSED_REJECTED"
    CLOSED_WITHDRAWN     = "CLOSED_WITHDRAWN"
    CLOSED_UNRECOVERABLE = "CLOSED_UNRECOVERABLE"
    CLOSED_DUPLICATE     = "CLOSED_DUPLICATE"

    # Clarification 05 — exception states
    ESCALATED  = "ESCALATED"
    QUARANTINED = "QUARANTINED"


class ClosureReason(str, Enum):
    RECOVERED_FULL      = "RECOVERED_FULL"
    RECOVERED_PARTIAL   = "RECOVERED_PARTIAL"
    NO_ACTION_REQUIRED  = "NO_ACTION_REQUIRED"
    FINDING_INVALID     = "FINDING_INVALID"
    DUPLICATE_CASE      = "DUPLICATE_CASE"
    UNRECOVERABLE       = "UNRECOVERABLE"
    WITHDRAWN           = "WITHDRAWN"
    EXTERNAL_REJECTED   = "EXTERNAL_REJECTED"
    POLICY_CLOSED       = "POLICY_CLOSED"


# Closure reasons that require a matching reconciliation record before ACR generation
CLOSURE_REASONS_REQUIRING_RECONCILIATION: frozenset[str] = frozenset({
    ClosureReason.RECOVERED_FULL,
    ClosureReason.RECOVERED_PARTIAL,
})

# Closure reasons valid as terminal states (used by closure validation)
TERMINAL_CLOSURE_STATES: frozenset[str] = frozenset({
    "CLOSED", "CLOSED_RECOVERED", "CLOSED_NO_ACTION", "CLOSED_REJECTED",
    "CLOSED_WITHDRAWN", "CLOSED_UNRECOVERABLE", "CLOSED_DUPLICATE", "ABORTED",
})


class ActionStatus(str, Enum):
    PENDING   = "PENDING"
    ACTIVE    = "ACTIVE"
    CONSUMED  = "CONSUMED"
    EXPIRED   = "EXPIRED"
    REVOKED   = "REVOKED"


class GovernanceDecisionType(str, Enum):
    APPROVE  = "APPROVE"
    REJECT   = "REJECT"
    ESCALATE = "ESCALATE"


class RiskClass(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class ChannelType(str, Enum):
    EMAIL   = "EMAIL"
    API     = "API"
    KAFKA   = "KAFKA"
    WEBHOOK = "WEBHOOK"


class ActorType(str, Enum):
    USER    = "USER"
    SERVICE = "SERVICE"
    SYSTEM  = "SYSTEM"


class RetentionClass(str, Enum):
    TRANSIENT  = "TRANSIENT"   # 30 days
    STANDARD   = "STANDARD"    # 7 years
    LEGAL_HOLD = "LEGAL_HOLD"  # indefinite


class EventType(str, Enum):
    CASE_OPENED          = "case.opened"
    CASE_UPDATED         = "case.updated"
    CASE_CLOSED          = "case.closed"
    EVIDENCE_BUNDLED     = "evidence.bundled"
    FINDING_GENERATED    = "finding.generated"
    PROPOSAL_CREATED     = "proposal.created"
    DECISION_ISSUED      = "governance.decision.issued"
    TOKEN_ISSUED         = "governance.token.issued"
    TOKEN_CONSUMED       = "governance.token.consumed"
    EXECUTION_DISPATCHED = "execution.dispatched"
    EXECUTION_COMPLETED  = "execution.completed"
    RECONCILIATION_DONE  = "reconciliation.updated"
    ACR_GENERATED        = "acr.generated"
    AUDIT_LOCKED         = "audit.artifact.written"
    SECURITY_EVENT       = "security.event.detected"


# Events that must be written to the WORM audit index
AUDIT_EVENTS: frozenset[str] = frozenset({
    EventType.CASE_OPENED,
    EventType.DECISION_ISSUED,
    EventType.TOKEN_ISSUED,
    EventType.TOKEN_CONSUMED,
    EventType.EXECUTION_DISPATCHED,
    EventType.EXECUTION_COMPLETED,
    EventType.ACR_GENERATED,
    EventType.AUDIT_LOCKED,
})

# Tables whose rows must never be UPDATE-d or DELETE-d
VERSIONED_TABLES: frozenset[str] = frozenset({
    "lineage_records",
    "case_events",
    "evidence_items",
    "audit_worm_index",
})

# SLO constants
SLO_CASE_RESOLUTION_HOURS     = 72    # cases must reach CLOSED within 72h
SLO_TOKEN_TTL_MINUTES         = 15    # governance token lifetime
SLO_EVIDENCE_BUNDLE_SECONDS   = 30    # evidence bundling must complete within 30s
SLO_MAX_PIPELINE_SECONDS      = 120   # full submit-async pipeline budget

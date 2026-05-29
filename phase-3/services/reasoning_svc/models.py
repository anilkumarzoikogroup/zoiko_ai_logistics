from dataclasses import dataclass
import uuid
from datetime import datetime
from typing import Dict


@dataclass
class FindingResult:

    # PRIMARY IDS
    finding_id: uuid.UUID
    proposal_id: uuid.UUID

    # TENANT + CASE
    tenant_id: str
    case_id: str
    bundle_id: str

    # FINAL CONFIDENCE
    confidence: float

    # AI FIELDS
    ai_confidence: float
    risk_level: str
    ai_reasoning: str

    # RULE TRACE
    rule_trace: Dict

    # PROPOSAL
    proposed_action: str
    amount: float
    currency: str
    proposer_sub: str

    # CREATED TIME
    created_at: datetime
"""Pydantic request/response models for SC-004 scorecard gateway."""
import paths  # noqa: F401
from pydantic import BaseModel, Field
from typing import Optional


class ComputeScorecardRequest(BaseModel):
    carrier_id:           str   = Field(..., description="Carrier identifier (e.g. 'BlueDart')")
    period_days:          int   = Field(30, ge=7, le=365, description="Look-back window in days")
    contracted_threshold: float = Field(70.0, ge=0.0, le=100.0, description="Breach threshold (0-100 composite score)")


class ScorecardListItem(BaseModel):
    id:                      str
    tenant_id:               str
    carrier_id:              str
    period_start:            str
    period_end:              str
    on_time_rate:            float
    damage_rate:             float
    claim_frequency:         float
    dispute_turnaround_days: float
    composite_score:         float
    contracted_threshold:    float
    breach_detected:         bool
    breach_amount:           float
    currency:                str
    created_at:              str


class SubScore(BaseModel):
    score:  float
    weight: float
    label:  str


class SubScores(BaseModel):
    on_time:    SubScore
    quality:    SubScore
    frequency:  SubScore
    resolution: SubScore


class RawMetrics(BaseModel):
    total_claims:        int   = 0
    total_claimed:       float = 0.0
    total_approved:      float = 0.0
    avg_turnaround_days: float = 0.0
    sla_cases:           int   = 0
    on_time_cases:       int   = 0


class RecentClaim(BaseModel):
    id:               str
    claim_reference:  Optional[str] = None
    claim_type:       str
    claimed_amount:   float
    approved_amount:  Optional[float] = None
    status:           str
    filed_at:         Optional[str] = None
    currency:         str


class ScorecardDetail(ScorecardListItem):
    sub_scores:    Optional[SubScores]   = None
    raw_metrics:   Optional[RawMetrics]  = None
    recent_claims: Optional[list[RecentClaim]] = None
    case_id:       Optional[str]         = None
    case_state:    Optional[str]         = None
    finding_id:    Optional[str]         = None
    task_id:       Optional[str]         = None
    task_status:   Optional[str]         = None


class UIProposalRequest(BaseModel):
    finding_id: str   = Field(..., description="Finding UUID to attach this proposal to")
    amount:     float = Field(..., gt=0, description="Proposed recovery/penalty amount")
    currency:   str   = Field("INR", description="ISO currency code")


class UIDecideRequest(BaseModel):
    task_id:  str           = Field(..., description="Governance task UUID to decide on")
    decision: str           = Field(..., description="APPROVE or REJECT")
    note:     Optional[str] = Field(None, description="Optional decision note")

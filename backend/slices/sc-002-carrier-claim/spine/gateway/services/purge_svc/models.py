from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class PurgeJobResult:
    purge_job_id:        str
    tenant_id:           str
    purge_scope:         str
    record_count:        int
    retention_policy_id: Optional[str]
    legal_hold_checked:  bool
    legal_hold_blocked:  bool
    approval_id:         Optional[str]
    approved_by:         Optional[str]
    approved_at:         Optional[str]
    status:              str
    completed_at:        Optional[str]
    evidence_id:         Optional[str]
    created_at:          str

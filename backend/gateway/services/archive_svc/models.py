from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ArchiveJobResult:
    archive_job_id:      str
    tenant_id:           str
    archive_scope:       str
    record_ids:          List[str]
    status:              str
    requested_by:        str
    retention_policy_id: Optional[str]
    legal_hold_checked:  bool
    completed_at:        Optional[str]
    evidence_id:         Optional[str]
    created_at:          str

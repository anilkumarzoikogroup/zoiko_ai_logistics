from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class RetentionPolicyResult:
    policy_id:         str
    tenant_id:         str
    policy_name:       str
    data_class:        str
    retention_class:   str
    retention_days:    int
    archive_after_days: Optional[int]
    purge_after_days:   Optional[int]
    status:            str
    created_by:        str
    created_at:        str


@dataclass
class RetentionAssignResult:
    record_id:         str
    record_type:       str
    policy_id:         str
    retention_class:   str
    retention_until:   Optional[str]
    archive_after:     Optional[str]
    purge_after:       Optional[str]

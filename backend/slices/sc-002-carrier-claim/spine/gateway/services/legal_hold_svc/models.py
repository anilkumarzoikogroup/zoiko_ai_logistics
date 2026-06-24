from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class LegalHoldResult:
    legal_hold_id:  str
    tenant_id:      str
    hold_scope:     str
    scope_id:       str
    reason_code:    str
    requested_by:   str
    approved_by:    Optional[str]
    status:         str
    effective_from: str
    released_at:    Optional[str]
    evidence_id:    Optional[str]
    created_at:     str

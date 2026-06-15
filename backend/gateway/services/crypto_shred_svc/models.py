from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CryptoShredResult:
    crypto_shred_id:    str
    tenant_id:          str
    subject_ref:        str
    affected_key_ids:   List[str]
    affected_record_ids: List[str]
    legal_hold_checked: bool
    legal_hold_blocked: bool
    status:             str
    requested_by:       str
    completed_at:       Optional[str]
    evidence_id:        Optional[str]
    created_at:         str


@dataclass
class CryptoShredVerifyResult:
    crypto_shred_id: str
    status:          str
    shred_confirmed: bool
    detail:          str

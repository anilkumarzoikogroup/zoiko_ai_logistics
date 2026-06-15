from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class RestoreJobResult:
    restore_job_id: str
    tenant_id:      str
    restore_type:   str
    restored_scope: str
    status:         str
    requested_by:   str
    approved_by:    Optional[str]
    approved_at:    Optional[str]
    evidence_id:    Optional[str]
    created_at:     str
    updated_at:     str


@dataclass
class RestoreVerificationResult:
    restore_verification_id:        str
    restore_job_id:                 str
    tenant_id:                      str
    source_records_verified:        bool
    evidence_chain_verified:        bool
    acr_verified:                   bool
    ledger_continuity_verified:     bool
    tenant_isolation_verified:      bool
    residency_verified:             bool
    permissions_verified:           bool
    legal_hold_verified:            bool
    indexes_rebuilt:                bool
    projection_consistency_verified: bool
    verification_status:            str
    verified_at:                    Optional[str]
    evidence_id:                    Optional[str]
    created_at:                     str

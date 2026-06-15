"""Clarification 07 — Data Residency, Retention, Legal Hold,
Crypto-Shred, Restore, Archive and Purge API routes.

All 22 routes defined in C07 §18.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.api_gateway.auth import get_claims
from services.legal_hold_svc.handler  import LegalHoldHandler
from services.crypto_shred_svc.handler import CryptoShredHandler
from services.restore_svc.handler     import RestoreHandler
from services.retention_svc.handler   import RetentionHandler
from services.purge_svc.handler       import PurgeHandler
from services.archive_svc.handler     import ArchiveHandler

router = APIRouter(tags=["c07-data-governance"])

DB_URL = os.getenv("DB_URL", "")


def _broker():
    try:
        from kafka.mock_kafka import MockKafkaBroker  # noqa
        return MockKafkaBroker()
    except Exception:
        return None


def _lh():  return LegalHoldHandler(DB_URL, _broker())
def _cs():  return CryptoShredHandler(DB_URL, _broker())
def _rs():  return RestoreHandler(DB_URL, _broker())
def _ret(): return RetentionHandler(DB_URL, _broker())
def _pu():  return PurgeHandler(DB_URL, _broker())
def _ar():  return ArchiveHandler(DB_URL, _broker())


# ═══════════════════════════════════════════════════════════════════════════════
# §18.1 — Retention APIs
# ═══════════════════════════════════════════════════════════════════════════════

class RetentionPolicyIn(BaseModel):
    policy_name:        str
    data_class:         str
    retention_class:    str
    retention_days:     int
    archive_after_days: Optional[int] = None
    purge_after_days:   Optional[int] = None


class RetentionAssignIn(BaseModel):
    record_type: str
    record_id:   str
    policy_id:   str


@router.post("/data/retention/policies", status_code=201)
def create_retention_policy(body: RetentionPolicyIn, claims=Depends(get_claims)):
    try:
        result = _ret().create_policy(
            tenant_id=str(claims.tenant_id),
            policy_name=body.policy_name,
            data_class=body.data_class,
            retention_class=body.retention_class,
            retention_days=body.retention_days,
            archive_after_days=body.archive_after_days,
            purge_after_days=body.purge_after_days,
            created_by=claims.sub,
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/data/retention/policies/{policy_id}")
def get_retention_policy(policy_id: str, claims=Depends(get_claims)):
    try:
        return _ret().get_policy(policy_id, str(claims.tenant_id)).__dict__
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/data/retention/assign", status_code=200)
def assign_retention(body: RetentionAssignIn, claims=Depends(get_claims)):
    try:
        result = _ret().assign(
            tenant_id=str(claims.tenant_id),
            record_type=body.record_type,
            record_id=body.record_id,
            policy_id=body.policy_id,
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/data/retention:by-record")
def retention_by_record(record_id: str, claims=Depends(get_claims)):
    try:
        return _ret().by_record(record_id, str(claims.tenant_id))
    except ValueError as e:
        raise HTTPException(404, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# §18.2 — Archive APIs
# ═══════════════════════════════════════════════════════════════════════════════

class ArchiveJobIn(BaseModel):
    archive_scope:       str
    record_ids:          List[str]
    retention_policy_id: Optional[str] = None


@router.post("/data/archive/jobs", status_code=201)
def create_archive_job(body: ArchiveJobIn, claims=Depends(get_claims)):
    try:
        result = _ar().create_job(
            tenant_id=str(claims.tenant_id),
            archive_scope=body.archive_scope,
            record_ids=body.record_ids,
            requested_by=claims.sub,
            retention_policy_id=body.retention_policy_id,
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/data/archive/jobs/{archive_job_id}")
def get_archive_job(archive_job_id: str, claims=Depends(get_claims)):
    try:
        return _ar().get_job(archive_job_id, str(claims.tenant_id)).__dict__
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/data/archive/{archive_id}/restore", status_code=201)
def restore_from_archive(archive_id: str, claims=Depends(get_claims)):
    try:
        return _ar().restore(archive_id, str(claims.tenant_id), claims.sub)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/data/archive/{archive_id}/verify")
def verify_archive(archive_id: str, claims=Depends(get_claims)):
    try:
        return _ar().verify(archive_id, str(claims.tenant_id))
    except ValueError as e:
        raise HTTPException(404, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# §18.3 — Legal Hold APIs
# ═══════════════════════════════════════════════════════════════════════════════

class LegalHoldIn(BaseModel):
    hold_scope:   str
    scope_id:     str
    reason_code:  str
    approved_by:  Optional[str] = None


class LegalHoldReleaseIn(BaseModel):
    released_by: str


@router.post("/legal-holds", status_code=201)
def create_legal_hold(body: LegalHoldIn, claims=Depends(get_claims)):
    try:
        result = _lh().create(
            tenant_id=str(claims.tenant_id),
            hold_scope=body.hold_scope,
            scope_id=body.scope_id,
            reason_code=body.reason_code,
            requested_by=claims.sub,
            approved_by=body.approved_by,
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/legal-holds/{legal_hold_id}")
def get_legal_hold(legal_hold_id: str, claims=Depends(get_claims)):
    try:
        return _lh().get(legal_hold_id, str(claims.tenant_id)).__dict__
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/legal-holds/{legal_hold_id}/release")
def release_legal_hold(legal_hold_id: str, body: LegalHoldReleaseIn, claims=Depends(get_claims)):
    try:
        result = _lh().release(legal_hold_id, str(claims.tenant_id), body.released_by)
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/legal-holds:by-scope")
def legal_holds_by_scope(scope_id: str, claims=Depends(get_claims)):
    results = _lh().by_scope(scope_id, str(claims.tenant_id))
    return [r.__dict__ for r in results]


# ═══════════════════════════════════════════════════════════════════════════════
# §18.4 — Crypto-Shred APIs
# ═══════════════════════════════════════════════════════════════════════════════

class CryptoShredIn(BaseModel):
    subject_ref:         str
    affected_key_ids:    List[str]
    affected_record_ids: List[str]


@router.post("/privacy/crypto-shred", status_code=201)
def request_crypto_shred(body: CryptoShredIn, claims=Depends(get_claims)):
    try:
        result = _cs().request(
            tenant_id=str(claims.tenant_id),
            subject_ref=body.subject_ref,
            affected_key_ids=body.affected_key_ids,
            affected_record_ids=body.affected_record_ids,
            requested_by=claims.sub,
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/privacy/crypto-shred/{crypto_shred_id}")
def get_crypto_shred(crypto_shred_id: str, claims=Depends(get_claims)):
    try:
        return _cs().get(crypto_shred_id, str(claims.tenant_id)).__dict__
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/privacy/crypto-shred/{crypto_shred_id}/verify")
def verify_crypto_shred(crypto_shred_id: str, claims=Depends(get_claims)):
    try:
        return _cs().verify(crypto_shred_id, str(claims.tenant_id)).__dict__
    except ValueError as e:
        raise HTTPException(404, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# §18.5 — Restore APIs
# ═══════════════════════════════════════════════════════════════════════════════

class RestoreJobIn(BaseModel):
    restore_type:   str
    restored_scope: str


class RestoreVerifyIn(BaseModel):
    source_records_verified:         bool = False
    evidence_chain_verified:         bool = False
    acr_verified:                    bool = False
    ledger_continuity_verified:      bool = False
    tenant_isolation_verified:       bool = False
    residency_verified:              bool = False
    permissions_verified:            bool = False
    legal_hold_verified:             bool = False
    indexes_rebuilt:                 bool = False
    projection_consistency_verified: bool = False


@router.post("/data/restore/jobs", status_code=201)
def create_restore_job(body: RestoreJobIn, claims=Depends(get_claims)):
    try:
        result = _rs().create_job(
            tenant_id=str(claims.tenant_id),
            restore_type=body.restore_type,
            restored_scope=body.restored_scope,
            requested_by=claims.sub,
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/data/restore/jobs/{restore_job_id}")
def get_restore_job(restore_job_id: str, claims=Depends(get_claims)):
    try:
        return _rs().get_job(restore_job_id, str(claims.tenant_id)).__dict__
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/data/restore/jobs/{restore_job_id}/verification")
def get_restore_verification(restore_job_id: str, claims=Depends(get_claims)):
    try:
        result = _rs().get_verification(restore_job_id, str(claims.tenant_id))
        return result.__dict__
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/data/restore/jobs/{restore_job_id}/verify", status_code=200)
def submit_restore_verification(restore_job_id: str, body: RestoreVerifyIn, claims=Depends(get_claims)):
    try:
        result = _rs().verify(
            restore_job_id=restore_job_id,
            tenant_id=str(claims.tenant_id),
            **body.model_dump(),
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/data/restore/jobs/{restore_job_id}/approve-use", status_code=200)
def approve_restore_use(restore_job_id: str, claims=Depends(get_claims)):
    try:
        result = _rs().approve_use(restore_job_id, str(claims.tenant_id), claims.sub)
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# §18.6 — Purge APIs
# ═══════════════════════════════════════════════════════════════════════════════

class PurgeJobIn(BaseModel):
    purge_scope:         str
    record_count:        int
    retention_policy_id: Optional[str] = None
    scope_ids:           List[str] = []


class PurgeApproveIn(BaseModel):
    approval_id: str


@router.post("/data/purge/jobs", status_code=201)
def create_purge_job(body: PurgeJobIn, claims=Depends(get_claims)):
    try:
        result = _pu().create_job(
            tenant_id=str(claims.tenant_id),
            purge_scope=body.purge_scope,
            record_count=body.record_count,
            retention_policy_id=body.retention_policy_id,
            requested_by=claims.sub,
            scope_ids=body.scope_ids,
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/data/purge/jobs/{purge_job_id}")
def get_purge_job(purge_job_id: str, claims=Depends(get_claims)):
    try:
        return _pu().get_job(purge_job_id, str(claims.tenant_id)).__dict__
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/data/purge/jobs/{purge_job_id}/approve", status_code=200)
def approve_purge(purge_job_id: str, body: PurgeApproveIn, claims=Depends(get_claims)):
    try:
        result = _pu().approve(purge_job_id, str(claims.tenant_id), body.approval_id, claims.sub)
        return result.__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/data/purge/jobs/{purge_job_id}/evidence")
def get_purge_evidence(purge_job_id: str, claims=Depends(get_claims)):
    try:
        return _pu().get_evidence(purge_job_id, str(claims.tenant_id))
    except ValueError as e:
        raise HTTPException(404, str(e))

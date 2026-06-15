"""Connector management and ingestion run routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional

from services.api_gateway.auth import get_claims
from shared.db import q, q1

router = APIRouter(tags=["connectors"])


# ── Connector CRUD ─────────────────────────────────────────────────────────────

class ConnectorIn(BaseModel):
    name:               str
    connector_type:     str = "API"
    auth_method:        str = "API_KEY"
    trust_tier:         str = "T2"
    endpoint_url:       str = ""
    credentials_ref:    str = ""
    rate_limit_rps:     int = 10

class ConnectorOut(BaseModel):
    id: str; tenant_id: str; name: str; connector_type: str
    auth_method: str; trust_tier: str; certification_state: str
    operational_state: str; endpoint_url: str; rate_limit_rps: int
    created_at: str; updated_at: str

def _fmt_connector(r: dict) -> dict:
    return {**r, "id": str(r["id"]), "tenant_id": str(r["tenant_id"]),
            "created_at": r["created_at"].isoformat(),
            "updated_at": r["updated_at"].isoformat()}

@router.post("/connectors", response_model=ConnectorOut, status_code=201)
def create_connector(body: ConnectorIn, claims=Depends(get_claims)):
    row = q1("""
        INSERT INTO connectors
            (id, tenant_id, name, connector_type, auth_method, trust_tier, endpoint_url, credentials_ref, rate_limit_rps)
        VALUES (gen_random_uuid(), %s::uuid, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, tenant_id, name, connector_type, auth_method, trust_tier,
                  certification_state, operational_state, endpoint_url, rate_limit_rps, created_at, updated_at
    """, (claims.tenant_id, body.name, body.connector_type, body.auth_method,
          body.trust_tier, body.endpoint_url, body.credentials_ref, body.rate_limit_rps))
    return _fmt_connector(row)

@router.get("/connectors", response_model=List[ConnectorOut])
def list_connectors(claims=Depends(get_claims)):
    rows = q("""
        SELECT id, tenant_id, name, connector_type, auth_method, trust_tier,
               certification_state, operational_state, endpoint_url, rate_limit_rps, created_at, updated_at
        FROM connectors WHERE tenant_id=%s::uuid ORDER BY name
    """, (claims.tenant_id,))
    return [_fmt_connector(r) for r in rows]

@router.get("/connectors/{connector_id}", response_model=ConnectorOut)
def get_connector(connector_id: str, claims=Depends(get_claims)):
    row = q1("""
        SELECT id, tenant_id, name, connector_type, auth_method, trust_tier,
               certification_state, operational_state, endpoint_url, rate_limit_rps, created_at, updated_at
        FROM connectors WHERE id=%s::uuid AND tenant_id=%s::uuid
    """, (connector_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Connector not found")
    return _fmt_connector(row)

class ConnectorStateIn(BaseModel):
    operational_state:  Optional[str] = None
    certification_state: Optional[str] = None

@router.patch("/connectors/{connector_id}/state")
def update_connector_state(connector_id: str, body: ConnectorStateIn, claims=Depends(get_claims)):
    if not body.certification_state and not body.operational_state:
        raise HTTPException(status_code=400, detail="Provide certification_state or operational_state")
    if body.certification_state:
        q1("UPDATE connectors SET certification_state=%s, updated_at=NOW() WHERE id=%s::uuid AND tenant_id=%s::uuid",
           (body.certification_state, connector_id, claims.tenant_id))
    if body.operational_state:
        q1("UPDATE connectors SET operational_state=%s, updated_at=NOW() WHERE id=%s::uuid AND tenant_id=%s::uuid",
           (body.operational_state, connector_id, claims.tenant_id))
    return {"message": "Connector state updated"}

@router.delete("/connectors/{connector_id}", status_code=200)
def delete_connector(connector_id: str, claims=Depends(get_claims)):
    q1("DELETE FROM connectors WHERE id=%s::uuid AND tenant_id=%s::uuid", (connector_id, claims.tenant_id))
    return {"message": "Connector deleted"}


# ── Ingestion Runs ─────────────────────────────────────────────────────────────

class SyncIn(BaseModel):
    idempotency_key: Optional[str] = None

class IngestionRunOut(BaseModel):
    id: str; tenant_id: str; connector_id: str; status: str
    records_received: int; records_accepted: int; records_rejected: int
    started_at: str; completed_at: Optional[str]; error_detail: str

def _fmt_run(r: dict) -> dict:
    return {**r, "id": str(r["id"]), "tenant_id": str(r["tenant_id"]),
            "connector_id": str(r["connector_id"]),
            "started_at": r["started_at"].isoformat(),
            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None}

@router.post("/ingestion/connectors/{connector_id}/sync", response_model=IngestionRunOut, status_code=201)
def trigger_connector_sync(
    connector_id: str,
    body: SyncIn,
    claims=Depends(get_claims),
):
    conn_row = q1("""
        SELECT id, name, connector_type, endpoint_url
        FROM connectors WHERE id=%s::uuid AND tenant_id=%s::uuid AND operational_state='healthy'
    """, (connector_id, claims.tenant_id))
    if not conn_row:
        raise HTTPException(status_code=404, detail="Connector not found or not healthy")

    run = q1("""
        INSERT INTO ingestion_runs (id, tenant_id, connector_id, status)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'RUNNING')
        RETURNING id
    """, (claims.tenant_id, connector_id))
    run_id = str(run["id"])

    # Attempt real fetch if endpoint_url is configured; otherwise complete with 0 records.
    records_received = 0
    records_accepted = 0
    records_rejected = 0
    error_detail = ""
    new_status = "COMPLETED"

    if conn_row.get("endpoint_url"):
        try:
            import urllib.request
            with urllib.request.urlopen(conn_row["endpoint_url"], timeout=5) as resp:
                records_received = 1 if resp.status == 200 else 0
                records_accepted = records_received
        except Exception as exc:
            new_status = "FAILED"
            error_detail = str(exc)[:500]

    completed = q1("""
        UPDATE ingestion_runs
        SET status=%s, records_received=%s, records_accepted=%s, records_rejected=%s,
            completed_at=NOW(), error_detail=%s
        WHERE id=%s::uuid
        RETURNING id, tenant_id, connector_id, status, records_received, records_accepted,
                  records_rejected, started_at, completed_at, error_detail
    """, (new_status, records_received, records_accepted, records_rejected, error_detail, run_id))
    return _fmt_run(completed)

@router.get("/ingestion/runs/{run_id}", response_model=IngestionRunOut)
def get_ingestion_run(run_id: str, claims=Depends(get_claims)):
    row = q1("""
        SELECT id, tenant_id, connector_id, status, records_received, records_accepted,
               records_rejected, started_at, completed_at, error_detail
        FROM ingestion_runs WHERE id=%s::uuid AND tenant_id=%s::uuid
    """, (run_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    return _fmt_run(row)

@router.get("/ingestion/runs", response_model=List[IngestionRunOut])
def list_ingestion_runs(connector_id: Optional[str] = None, claims=Depends(get_claims)):
    if connector_id:
        rows = q("""
            SELECT id, tenant_id, connector_id, status, records_received, records_accepted,
                   records_rejected, started_at, completed_at, error_detail
            FROM ingestion_runs WHERE tenant_id=%s::uuid AND connector_id=%s::uuid ORDER BY started_at DESC LIMIT 50
        """, (claims.tenant_id, connector_id))
    else:
        rows = q("""
            SELECT id, tenant_id, connector_id, status, records_received, records_accepted,
                   records_rejected, started_at, completed_at, error_detail
            FROM ingestion_runs WHERE tenant_id=%s::uuid ORDER BY started_at DESC LIMIT 50
        """, (claims.tenant_id,))
    return [_fmt_run(r) for r in rows]

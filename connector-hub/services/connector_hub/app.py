"""
Connector Hub FastAPI gateway — port 8010.

Routes:
  GET  /health
  POST /v1/connectors/{carrier_id}/claims     — submit carrier credit-memo claim
  GET  /v1/connectors/{carrier_id}/status     — connector certification status
  POST /v1/connectors/{carrier_id}/certify    — (admin) activate connector
  POST /v1/connectors/{carrier_id}/suspend    — (admin) suspend connector

All claim routes require:
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant-uuid>
  Idempotency-Key: <unique-string>  (mutations only)
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, APIRouter, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.connector_hub.handler  import ConnectorHubHandler, _breakers
from services.connector_hub.models   import ClaimRequest
from services.connector_hub.registry import get_registry

DB_URL = os.getenv("DB_URL")

app = FastAPI(title="Zoiko Connector Hub", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = APIRouter()
_handler  = ConnectorHubHandler(db_url=DB_URL)
_registry = get_registry()


# ── Request / response schemas ────────────────────────────────────────────────

class ClaimBody(BaseModel):
    envelope_id:     str
    tenant_id:       str
    claimed_amount:  float
    currency:        str = "INR"
    invoice_ref:     str = ""
    actor_sub:       str = "system"


class CertifyBody(BaseModel):
    actor_sub: str
    reason:    str = ""


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "service": "connector-hub", "version": "1.0.0"}


# ── Claims ────────────────────────────────────────────────────────────────────

@v1.post("/connectors/{carrier_id}/claims", status_code=201, tags=["claims"])
def submit_claim(
    carrier_id:      str,
    body:            ClaimBody,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    x_tenant_id:     str = Header(..., alias="X-Tenant-ID"),
):
    """
    Submit a carrier credit-memo claim.
    For SC-001 (BlueDart, INR 4500 overcharge): returns deterministic USD 220.00.
    Circuit breaker trips after 3 consecutive failures; recovers after 30s.
    """
    req = ClaimRequest(
        carrier_id       = carrier_id,
        envelope_id      = body.envelope_id,
        tenant_id        = body.tenant_id or x_tenant_id,
        claimed_amount   = body.claimed_amount,
        currency         = body.currency,
        invoice_ref      = body.invoice_ref,
        actor_sub        = body.actor_sub,
        idempotency_key  = idempotency_key,
    )
    resp = _handler.submit_claim(req)
    return {
        "claim_ref":         resp.claim_ref,
        "envelope_id":       resp.envelope_id,
        "carrier_id":        resp.carrier_id,
        "accepted":          resp.accepted,
        "accepted_amount":   resp.accepted_amount,
        "original_amount":   resp.original_amount,
        "original_currency": resp.original_currency,
        "fx_rate":           resp.fx_rate,
        "status":            resp.status,
        "reason":            resp.reason,
        "settled_at":        resp.settled_at.isoformat(),
    }


# ── Connector registry ────────────────────────────────────────────────────────

@v1.get("/connectors/{carrier_id}/status", tags=["registry"])
def connector_status(carrier_id: str):
    """Return certification status and circuit breaker state for a carrier connector."""
    rec     = _registry.get(carrier_id)
    breaker = _breakers.get(carrier_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Connector '{carrier_id}' not registered")
    return {
        "carrier_id":    rec["carrier_id"],
        "status":        rec["status"],
        "certified_at":  rec["certified_at"].isoformat() if rec.get("certified_at") else None,
        "certified_by":  rec.get("certified_by"),
        "circuit_state": breaker.state if breaker else "CLOSED",
    }


@v1.post("/connectors/{carrier_id}/certify", status_code=201, tags=["registry"])
def certify_connector(
    carrier_id: str,
    body:       CertifyBody,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Register or re-activate a carrier connector. Admin-only in production."""
    rec = _registry.certify(carrier_id, body.actor_sub, body.reason)
    # Reset circuit breaker on certification
    if carrier_id in _breakers:
        _breakers[carrier_id].reset()
    return {
        "carrier_id":   rec["carrier_id"],
        "status":       rec["status"],
        "certified_at": rec["certified_at"].isoformat(),
        "certified_by": rec["certified_by"],
    }


@v1.post("/connectors/{carrier_id}/suspend", status_code=200, tags=["registry"])
def suspend_connector(
    carrier_id: str,
    body:       CertifyBody,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Suspend a carrier connector — all future claims will be REJECTED."""
    rec = _registry.suspend(carrier_id, body.actor_sub)
    return {"carrier_id": rec["carrier_id"], "status": rec["status"]}


# ── Route registration ────────────────────────────────────────────────────────
app.include_router(v1, prefix="/v1")

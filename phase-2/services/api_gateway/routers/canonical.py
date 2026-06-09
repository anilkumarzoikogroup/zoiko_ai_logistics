"""Canonical Truth read endpoints: shipments, invoices, contracts, claims."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from services.api_gateway.auth import get_claims
from shared.db import q, q1

router = APIRouter(tags=["canonical-truth"])


# ── Shipments ──────────────────────────────────────────────────────────────────

class ShipmentOut(BaseModel):
    id: str; tenant_id: str; shipment_number: str; status: str
    transport_mode: str; carrier_id: Optional[str]
    origin_facility_id: Optional[str]; dest_facility_id: Optional[str]
    scheduled_pickup: Optional[str]; actual_pickup: Optional[str]
    scheduled_delivery: Optional[str]; actual_delivery: Optional[str]
    total_weight_kg: float; total_volume_m3: float
    created_at: str; updated_at: str

def _fmt_shipment(r: dict) -> dict:
    return {**r,
            "id": str(r["id"]), "tenant_id": str(r["tenant_id"]),
            "carrier_id": str(r["carrier_id"]) if r.get("carrier_id") else None,
            "origin_facility_id": str(r["origin_facility_id"]) if r.get("origin_facility_id") else None,
            "dest_facility_id": str(r["dest_facility_id"]) if r.get("dest_facility_id") else None,
            "total_weight_kg": float(r["total_weight_kg"]),
            "total_volume_m3": float(r["total_volume_m3"]),
            "scheduled_pickup": r["scheduled_pickup"].isoformat() if r.get("scheduled_pickup") else None,
            "actual_pickup": r["actual_pickup"].isoformat() if r.get("actual_pickup") else None,
            "scheduled_delivery": r["scheduled_delivery"].isoformat() if r.get("scheduled_delivery") else None,
            "actual_delivery": r["actual_delivery"].isoformat() if r.get("actual_delivery") else None,
            "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat()}

@router.get("/shipments", response_model=List[ShipmentOut])
def list_shipments(status: Optional[str] = None, claims=Depends(get_claims)):
    if status:
        rows = q("SELECT * FROM shipments WHERE tenant_id=%s::uuid AND status=%s ORDER BY created_at DESC LIMIT 100", (claims.tenant_id, status))
    else:
        rows = q("SELECT * FROM shipments WHERE tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 100", (claims.tenant_id,))
    return [_fmt_shipment(r) for r in rows]

@router.get("/shipments/{shipment_id}", response_model=ShipmentOut)
def get_shipment(shipment_id: str, claims=Depends(get_claims)):
    row = q1("SELECT * FROM shipments WHERE id=%s::uuid AND tenant_id=%s::uuid", (shipment_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return _fmt_shipment(row)

@router.get("/shipments/{shipment_id}/legs")
def get_shipment_legs(shipment_id: str, claims=Depends(get_claims)):
    rows = q("""
        SELECT id, shipment_id, leg_sequence, carrier_id, origin, destination,
               transport_mode, departure_at, arrival_at, created_at
        FROM shipment_legs WHERE shipment_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY leg_sequence
    """, (shipment_id, claims.tenant_id))
    return [{"id": str(r["id"]), "shipment_id": str(r["shipment_id"]),
             "leg_sequence": r["leg_sequence"], "origin": r["origin"],
             "destination": r["destination"], "transport_mode": r["transport_mode"],
             "carrier_id": str(r["carrier_id"]) if r.get("carrier_id") else None,
             "departure_at": r["departure_at"].isoformat() if r.get("departure_at") else None,
             "arrival_at": r["arrival_at"].isoformat() if r.get("arrival_at") else None,
             "created_at": r["created_at"].isoformat()} for r in rows]


# ── Invoices ───────────────────────────────────────────────────────────────────

@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str, claims=Depends(get_claims)):
    row = q1("""
        SELECT ci.id, ci.tenant_id, ci.invoice_number, ci.carrier_id, ci.total_amount,
               ci.currency, ci.invoice_date, ci.transport_mode, ci.charge_lines,
               ci.created_at,
               COALESCE(json_agg(il.*) FILTER (WHERE il.id IS NOT NULL), '[]') AS lines
        FROM canonical_invoices ci
        LEFT JOIN invoice_lines il ON il.canonical_invoice_id = ci.id
        WHERE ci.id=%s::uuid AND ci.tenant_id=%s::uuid
        GROUP BY ci.id
    """, (invoice_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {**row, "id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "total_amount": float(row["total_amount"]),
            "created_at": row["created_at"].isoformat()}

@router.get("/invoices")
def list_invoices(carrier_id: Optional[str] = None, claims=Depends(get_claims)):
    if carrier_id:
        rows = q("SELECT id, tenant_id, invoice_number, carrier_id, total_amount, currency, invoice_date, created_at FROM canonical_invoices WHERE tenant_id=%s::uuid AND carrier_id=%s ORDER BY created_at DESC LIMIT 100", (claims.tenant_id, carrier_id))
    else:
        rows = q("SELECT id, tenant_id, invoice_number, carrier_id, total_amount, currency, invoice_date, created_at FROM canonical_invoices WHERE tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 100", (claims.tenant_id,))
    return [{"id": str(r["id"]), "tenant_id": str(r["tenant_id"]),
             "invoice_number": r["invoice_number"], "carrier_id": r["carrier_id"],
             "total_amount": float(r["total_amount"]), "currency": r["currency"],
             "invoice_date": r["invoice_date"],
             "created_at": r["created_at"].isoformat()} for r in rows]


# ── Contracts ──────────────────────────────────────────────────────────────────

@router.get("/contracts/{contract_id}")
def get_contract(contract_id: str, claims=Depends(get_claims)):
    row = q1("""
        SELECT cr.id, cr.tenant_id, cr.carrier_id, cr.origin, cr.destination,
               cr.rate_per_kg, cr.currency, cr.effective_from, cr.effective_to, cr.created_at,
               COALESCE(json_agg(cc.*) FILTER (WHERE cc.id IS NOT NULL), '[]') AS clauses
        FROM contract_rates cr
        LEFT JOIN contract_clauses cc ON cc.contract_rate_id = cr.id
        WHERE cr.id=%s::uuid AND cr.tenant_id=%s::uuid
        GROUP BY cr.id
    """, (contract_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Contract not found")
    return {**row, "id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "rate_per_kg": float(row["rate_per_kg"]),
            "effective_from": row["effective_from"].isoformat() if row.get("effective_from") else None,
            "effective_to": row["effective_to"].isoformat() if row.get("effective_to") else None,
            "created_at": row["created_at"].isoformat()}


# ── Claims ─────────────────────────────────────────────────────────────────────

class ClaimIn(BaseModel):
    case_id:        Optional[str] = None
    shipment_id:    Optional[str] = None
    claim_type:     str = "OVERCHARGE"
    claimed_amount: float
    currency:       str = "USD"

class ClaimOut(BaseModel):
    id: str; tenant_id: str; claim_type: str; claimed_amount: float
    approved_amount: Optional[float]; currency: str; status: str
    case_id: Optional[str]; shipment_id: Optional[str]
    filed_at: str; resolved_at: Optional[str]; created_at: str

def _fmt_claim(r: dict) -> dict:
    return {**r, "id": str(r["id"]), "tenant_id": str(r["tenant_id"]),
            "case_id": str(r["case_id"]) if r.get("case_id") else None,
            "shipment_id": str(r["shipment_id"]) if r.get("shipment_id") else None,
            "claimed_amount": float(r["claimed_amount"]),
            "approved_amount": float(r["approved_amount"]) if r.get("approved_amount") else None,
            "filed_at": r["filed_at"].isoformat(),
            "resolved_at": r["resolved_at"].isoformat() if r.get("resolved_at") else None,
            "created_at": r["created_at"].isoformat()}

@router.post("/claims", response_model=ClaimOut, status_code=201)
def create_claim(body: ClaimIn, claims=Depends(get_claims)):
    row = q1("""
        INSERT INTO claims (id, tenant_id, case_id, shipment_id, claim_type, claimed_amount, currency)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, %s::uuid, %s, %s, %s)
        RETURNING id, tenant_id, case_id, shipment_id, claim_type, claimed_amount,
                  approved_amount, currency, status, filed_at, resolved_at, created_at
    """, (claims.tenant_id,
          body.case_id if body.case_id else None,
          body.shipment_id if body.shipment_id else None,
          body.claim_type, body.claimed_amount, body.currency))
    return _fmt_claim(row)

@router.get("/claims/{claim_id}", response_model=ClaimOut)
def get_claim(claim_id: str, claims=Depends(get_claims)):
    row = q1("""
        SELECT id, tenant_id, case_id, shipment_id, claim_type, claimed_amount,
               approved_amount, currency, status, filed_at, resolved_at, created_at
        FROM claims WHERE id=%s::uuid AND tenant_id=%s::uuid
    """, (claim_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Claim not found")
    return _fmt_claim(row)

@router.get("/claims", response_model=List[ClaimOut])
def list_claims(status: Optional[str] = None, claims=Depends(get_claims)):
    if status:
        rows = q("SELECT id, tenant_id, case_id, shipment_id, claim_type, claimed_amount, approved_amount, currency, status, filed_at, resolved_at, created_at FROM claims WHERE tenant_id=%s::uuid AND status=%s ORDER BY filed_at DESC", (claims.tenant_id, status))
    else:
        rows = q("SELECT id, tenant_id, case_id, shipment_id, claim_type, claimed_amount, approved_amount, currency, status, filed_at, resolved_at, created_at FROM claims WHERE tenant_id=%s::uuid ORDER BY filed_at DESC", (claims.tenant_id,))
    return [_fmt_claim(r) for r in rows]

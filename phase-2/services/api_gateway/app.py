"""
API Gateway — FastAPI application for Phase 2.

Routes:
  GET  /health
  POST /invoices                          (ingest)
  POST /invoices/{source_record_id}/validate
  POST /invoices/{source_record_id}/canonicalize
  POST /cases                             (open case)
  PATCH /cases/{case_id}/state            (transition)

All mutating routes require:
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant-uuid>
  Idempotency-Key: <client-uuid>   (POST /invoices only)
"""
import os
import paths  # noqa: F401 — must be first

from fastapi import FastAPI, Depends, Header, HTTPException

from services.api_gateway.auth   import get_claims
from services.api_gateway.models import (
    InvoiceRequest, InvoiceResponse,
    ValidateRequest, ValidateResponse,
    CanonicalizeRequest, CanonicalizeResponse,
    OpenCaseRequest, OpenCaseResponse,
    TransitionRequest, TransitionResponse,
    HealthResponse,
)
from services.ingestion_svc.handler    import IngestionHandler
from services.ingestion_svc.models     import InvoiceInput
from services.validation_svc.handler  import ValidationHandler
from services.canonical_truth.handler import CanonicalHandler
from services.case_orchestration.handler import CaseHandler
from middleware.oidc.claims import ZoikoClaims

DB_URL      = os.getenv("DB_URL",      "postgresql://postgres:zoiko123@localhost/zoiko")
TENANT_SLUG = os.getenv("TENANT_SLUG", "default")

# Dev: in-memory mock; prod: swap for a real kafka-python KafkaProducer
from kafka.mock_kafka import MockKafkaBroker as _MockBroker
_BROKER = _MockBroker()

app = FastAPI(title="Zoiko Logistics API Gateway", version="2.0.0")


# ── Singleton handlers ────────────────────────────────────────────────────────

_ingestion  = IngestionHandler(DB_URL, _BROKER, TENANT_SLUG)
_validation = ValidationHandler(DB_URL, _BROKER, TENANT_SLUG)
_canonical  = CanonicalHandler(DB_URL, _BROKER, TENANT_SLUG)
_cases      = CaseHandler(DB_URL, _BROKER)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health():
    return HealthResponse(status="ok", service="api-gateway", version="2.0.0")


# ── Ingestion ─────────────────────────────────────────────────────────────────

@app.post("/invoices", response_model=InvoiceResponse, status_code=201, tags=["invoices"])
def ingest_invoice(
    body: InvoiceRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    invoice = InvoiceInput(
        carrier_id        = body.carrier_id,
        invoice_number    = body.invoice_number,
        total_amount      = body.total_amount,
        currency          = body.currency,
        route_origin      = body.route_origin,
        route_destination = body.route_destination,
        weight_lbs        = body.weight_lbs,
    )
    result = _ingestion.ingest_invoice(
        tenant_id       = str(claims.tenant_id),
        invoice         = invoice,
        idempotency_key = idempotency_key,
    )
    return InvoiceResponse(
        source_record_id = str(result.source_record_id),
        canonical_hash   = result.canonical_hash,
        idempotency_key  = result.idempotency_key,
        tenant_id        = str(result.tenant_id),
    )


# ── Validation ────────────────────────────────────────────────────────────────

@app.post(
    "/invoices/{source_record_id}/validate",
    response_model=ValidateResponse,
    tags=["invoices"],
)
def validate_invoice(
    source_record_id: str,
    body: ValidateRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _validation.validate(
            tenant_id        = str(claims.tenant_id),
            source_record_id = source_record_id,
            invoice_number   = body.invoice_number,
            carrier_id       = body.carrier_id,
            total_amount     = body.total_amount,
            currency         = body.currency,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ValidateResponse(
        validation_id     = str(result.validation_id),
        status            = result.status,
        overcharge_amount = result.overcharge_amount,
        violations        = len(result.rule_violations),
        currency          = result.currency,
    )


# ── Canonicalize ──────────────────────────────────────────────────────────────

@app.post(
    "/invoices/{source_record_id}/canonicalize",
    response_model=CanonicalizeResponse,
    tags=["invoices"],
)
def canonicalize_invoice(
    source_record_id: str,
    body: CanonicalizeRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _canonical.canonicalize_invoice(
            tenant_id        = str(claims.tenant_id),
            source_record_id = source_record_id,
            invoice_number   = body.invoice_number,
            carrier_id       = body.carrier_id,
            total_amount     = body.total_amount,
            currency         = body.currency,
            origin_city      = body.origin_city,
            dest_city        = body.dest_city,
            weight_lbs       = body.weight_lbs,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return CanonicalizeResponse(
        canonical_invoice_id  = str(result.canonical_invoice_id),
        canonical_shipment_id = str(result.canonical_shipment_id),
        canonical_hash        = result.canonical_hash,
        invoice_number        = result.invoice_number,
    )


# ── Cases ─────────────────────────────────────────────────────────────────────

@app.post("/cases", response_model=OpenCaseResponse, status_code=201, tags=["cases"])
def open_case(
    body: OpenCaseRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _cases.open_case(
            tenant_id            = str(claims.tenant_id),
            canonical_invoice_id = body.canonical_invoice_id,
            actor_sub            = claims.sub,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return OpenCaseResponse(
        case_id   = str(result.case_id),
        state     = result.state,
        is_new    = result.is_new,
        tenant_id = str(result.tenant_id),
    )


@app.patch("/cases/{case_id}/state", response_model=TransitionResponse, tags=["cases"])
def transition_case(
    case_id: str,
    body: TransitionRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        new_state = _cases.transition_state(
            tenant_id = str(claims.tenant_id),
            case_id   = case_id,
            new_state = body.new_state,
            actor_sub = body.actor_sub,
            payload   = body.payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return TransitionResponse(case_id=case_id, new_state=new_state)

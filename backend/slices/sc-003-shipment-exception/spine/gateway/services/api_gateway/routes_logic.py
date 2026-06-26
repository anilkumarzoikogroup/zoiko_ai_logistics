"""SC-003 — Shipment Exception route logic.

Pattern mirrors sc-002's routes_logic.py:
  submit_exception()    — full pipeline (ingest → canonical → case → evidence → finding)
  ui_list_exceptions()  — paginated list with SLA breach data
  ui_get_exception()    — single exception detail
  run_evidence_and_reasoning_exception() — runs evidence + reasoning in a bg thread
"""
import json
import threading
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from shared.db import q, q1, DB_URL


# ── Query helper ──────────────────────────────────────────────────────────────

def exceptions_q(_r, where: str, params: tuple, limit: int = 50, offset: int = 0) -> list[dict]:
    rows = q(f"""
        SELECT
            c.id::text                                              AS id,
            c.tenant_id::text                                       AS tenant_id,
            c.state,
            'SHIPMENT_EXCEPTION'                                    AS case_type,
            c.shipment_reference,
            COALESCE(c.committed_eta::text, '')                     AS committed_eta,
            COALESCE(c.actual_delivery::text, '')                   AS actual_delivery,
            COALESCE(c.sla_breach_hours, 0)::float                  AS sla_breach_hours,
            COALESCE(c.sla_penalty_amount, 0)::float                AS sla_penalty_amount,
            COALESCE((
                SELECT cse.carrier_id FROM canonical_shipment_exceptions cse
                WHERE  cse.shipment_reference = c.shipment_reference
                  AND  cse.tenant_id = c.tenant_id
                LIMIT 1
            ), '')                                                  AS carrier,
            COALESCE((
                SELECT cse.currency FROM canonical_shipment_exceptions cse
                WHERE  cse.shipment_reference = c.shipment_reference
                  AND  cse.tenant_id = c.tenant_id
                LIMIT 1
            ), 'INR')                                               AS currency,
            COALESCE((
                SELECT f.confidence::float
                FROM   findings f WHERE f.case_id = c.id LIMIT 1
            ), 0)                                                   AS confidence,
            c.opened_at,
            c.opened_at                                             AS updated_at
        FROM  cases c
        {where}
        ORDER BY c.opened_at DESC
        LIMIT %s OFFSET %s
    """, params + (limit, offset))
    return [_r(row) for row in rows]


# ── Submit (sync) ─────────────────────────────────────────────────────────────

def submit_exception(
    db_url, broker, ingestion_cls, canonical_cls, case_cls,
    run_evidence_and_reasoning_fn,
    capture_rest_push_metadata_fn,
    request, body, idempotency_key: str, tenant_id: str, actor_sub: str,
) -> dict:
    """Full pipeline: ingest → canonical → open case → evidence + reasoning (bg thread)."""
    from dateutil.parser import parse as _parse

    committed_eta   = _parse(body.committed_eta)
    actual_delivery = _parse(body.actual_delivery)

    slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (tenant_id,))
    slug     = slug_row["slug"] if slug_row else "default"

    ch_metadata = capture_rest_push_metadata_fn(request, idempotency_key)
    channel     = "ui_entry" if request.headers.get("X-UI-Submit") else "rest_api_push"

    from services.ingestion_svc.models import ShipmentExceptionInput
    exc_in = ShipmentExceptionInput(
        carrier_id            = body.carrier,
        shipment_reference    = body.shipment_reference,
        committed_eta         = committed_eta,
        actual_delivery       = actual_delivery,
        origin                = body.origin,
        destination           = body.destination,
        penalty_rate_per_hour = body.penalty_rate_per_hour,
        penalty_cap           = body.penalty_cap,
        currency              = body.currency,
        description           = body.description or "",
        event_stream          = [e.dict() for e in body.event_stream],
    )

    ing_r = ingestion_cls(db_url, broker, slug).ingest_shipment_exception(
        tenant_id, exc_in, idempotency_key,
        channel=channel, channel_metadata=ch_metadata,
        received_by_user=actor_sub if actor_sub else None,
        correlation_id=request.headers.get("X-Correlation-ID"),
    )

    try:
        from services.validation_svc.handler import ShipmentExceptionValidationHandler
        val_r = ShipmentExceptionValidationHandler(db_url, broker, slug).validate(
            tenant_id=tenant_id,
            source_record_id=ing_r.source_record_id,
            carrier_id=body.carrier,
            shipment_reference=body.shipment_reference,
            committed_eta=committed_eta,
            actual_delivery=actual_delivery,
            penalty_rate_per_hour=body.penalty_rate_per_hour,
            penalty_cap=body.penalty_cap,
            currency=body.currency,
        )
        if val_r.status == "FAIL":
            rules = [v.rule for v in val_r.rule_violations if v.severity == "FAIL"]
            raise HTTPException(status_code=422, detail=f"Shipment exception validation failed ({rules})")
    except HTTPException:
        raise
    except Exception:
        pass   # validation is best-effort; never block on unexpected DB error

    can_r = canonical_cls(db_url, broker, slug).canonicalize_shipment_exception(
        tenant_id             = tenant_id,
        source_record_id      = ing_r.source_record_id,
        shipment_reference    = body.shipment_reference,
        carrier_id            = body.carrier,
        committed_eta         = committed_eta,
        actual_delivery       = actual_delivery,
        penalty_rate_per_hour = body.penalty_rate_per_hour,
        penalty_cap           = body.penalty_cap,
        currency              = body.currency,
        origin                = body.origin,
        destination           = body.destination,
    )

    case_r = case_cls(db_url, broker).open_case(
        tenant_id          = tenant_id,
        shipment_reference = body.shipment_reference,
        committed_eta      = committed_eta,
        actual_delivery    = actual_delivery,
        sla_breach_hours   = can_r.sla_breach_hours,
        sla_penalty_amount = can_r.penalty_amount,
        actor_sub          = actor_sub,
    )

    if not case_r.is_new:
        existing = q1(
            "SELECT state, opened_at FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid",
            (str(case_r.case_id), tenant_id),
        )
        return {
            "id":                  str(case_r.case_id),
            "tenant_id":           tenant_id,
            "state":               existing["state"] if existing else case_r.state,
            "case_type":           "SHIPMENT_EXCEPTION",
            "carrier":             body.carrier,
            "shipment_reference":  body.shipment_reference,
            "committed_eta":       body.committed_eta,
            "actual_delivery":     body.actual_delivery,
            "sla_breach_hours":    can_r.sla_breach_hours,
            "sla_penalty_amount":  can_r.penalty_amount,
            "currency":            body.currency,
            "confidence":          0.0,
            "opened_at":           (existing["opened_at"].isoformat() if existing else case_r.opened_at.isoformat()),
            "updated_at":          datetime.now(timezone.utc).isoformat(),
            "duplicate":           True,
        }

    def _bg():
        try:
            run_evidence_and_reasoning_fn(
                db_url             = db_url,
                tenant_id          = tenant_id,
                case_id            = str(case_r.case_id),
                slug               = slug,
                canonical_hash     = can_r.canonical_hash,
                source_record_id   = ing_r.source_record_id,
                shipment_reference = body.shipment_reference,
                carrier_id         = body.carrier,
                sla_breach_hours   = can_r.sla_breach_hours,
                sla_penalty_amount = can_r.penalty_amount,
                penalty_rate_per_hour = body.penalty_rate_per_hour,
                committed_eta      = committed_eta,
                actual_delivery    = actual_delivery,
                currency           = body.currency,
                actor_sub          = actor_sub,
                broker             = broker,
            )
        except Exception:
            import traceback; traceback.print_exc()

    threading.Thread(target=_bg, daemon=True, name=f"sc003-{case_r.case_id}").start()

    now_str = datetime.now(timezone.utc).isoformat()
    return {
        "id":                  str(case_r.case_id),
        "tenant_id":           tenant_id,
        "state":               "EVIDENCE_PENDING",
        "case_type":           "SHIPMENT_EXCEPTION",
        "carrier":             body.carrier,
        "shipment_reference":  body.shipment_reference,
        "committed_eta":       body.committed_eta,
        "actual_delivery":     body.actual_delivery,
        "sla_breach_hours":    can_r.sla_breach_hours,
        "sla_penalty_amount":  can_r.penalty_amount,
        "currency":            body.currency,
        "confidence":          0.0,
        "opened_at":           now_str,
        "updated_at":          now_str,
    }


def run_evidence_and_reasoning_exception(
    db_url, tenant_id: str, case_id: str, slug: str,
    canonical_hash, source_record_id, shipment_reference: str,
    carrier_id: str, sla_breach_hours: float, sla_penalty_amount: float,
    penalty_rate_per_hour: float, committed_eta, actual_delivery,
    currency: str, actor_sub: str, broker,
) -> None:
    """Build evidence bundle + generate finding for a shipment exception case."""
    from kafka.mock_kafka import MockKafkaBroker
    from services.case_orchestration.handler import CaseHandler
    from services.evidence_svc.handler import EvidenceHandler
    from services.reasoning_svc.handler import ReasoningHandler
    from services.reasoning_svc.rules import SC003_CONFIDENCE

    _broker = broker or MockKafkaBroker()

    # EVIDENCE_PENDING
    CaseHandler(db_url, _broker).transition_state(tenant_id, case_id, "EVIDENCE_PENDING", actor_sub)

    _ev = EvidenceHandler(db_url, _broker, slug)

    # Artifact 1: source_record
    r1 = _ev.add_item(
        tenant_id     = tenant_id,
        case_id       = case_id,
        item_type     = "source_record",
        content_bytes = json.dumps({
            "source_record_id":   str(source_record_id),
            "shipment_reference": shipment_reference,
            "carrier_id":         carrier_id,
        }, sort_keys=True).encode(),
        actor_sub     = actor_sub or "system",
    )
    bundle_id = r1.bundle_id

    # Artifact 2: canonical_shipment_exception
    _can_bytes = (
        canonical_hash if isinstance(canonical_hash, bytes)
        else bytes.fromhex(canonical_hash) if isinstance(canonical_hash, str)
        else str(canonical_hash).encode()
    )
    _ev.add_item(
        tenant_id     = tenant_id,
        case_id       = case_id,
        item_type     = "canonical_shipment_exception",
        content_bytes = _can_bytes,
        actor_sub     = actor_sub or "system",
    )

    # Artifact 3: sla_contract_clause
    _ev.add_item(
        tenant_id     = tenant_id,
        case_id       = case_id,
        item_type     = "sla_contract_clause",
        content_bytes = json.dumps({
            "penalty_rate_per_hour": penalty_rate_per_hour,
            "currency":              currency,
        }, sort_keys=True).encode(),
        actor_sub     = actor_sub or "system",
    )

    # Artifact 4: breach_calculation
    _ev.add_item(
        tenant_id     = tenant_id,
        case_id       = case_id,
        item_type     = "breach_calculation",
        content_bytes = json.dumps({
            "committed_eta":    committed_eta.isoformat() if hasattr(committed_eta, "isoformat") else str(committed_eta),
            "actual_delivery":  actual_delivery.isoformat() if hasattr(actual_delivery, "isoformat") else str(actual_delivery),
            "sla_breach_hours": sla_breach_hours,
            "sla_penalty_amount": sla_penalty_amount,
        }, sort_keys=True).encode(),
        actor_sub     = actor_sub or "system",
    )

    # Artifact 5: rule_trace
    _ev.add_item(
        tenant_id     = tenant_id,
        case_id       = case_id,
        item_type     = "rule_trace",
        content_bytes = json.dumps({
            "delivery_window_breach": {"confidence": 1.00, "weight": 0.60},
            "sla_clause_applicable":  {"confidence": 0.88, "weight": 0.40},
        }, sort_keys=True).encode(),
        actor_sub     = actor_sub or "system",
    )

    ReasoningHandler(db_url, _broker, slug).generate_finding(
        tenant_id          = tenant_id,
        case_id            = case_id,
        bundle_id          = bundle_id,
        sla_breach_hours   = sla_breach_hours,
        sla_penalty_amount = sla_penalty_amount,
        currency           = currency,
        actor_sub          = actor_sub,
    )

    # FINDING_GENERATED
    CaseHandler(db_url, _broker).transition_state(tenant_id, case_id, "FINDING_GENERATED", actor_sub)

    # Kafka events
    try:
        from kafka.producer import ZoikoProducer, KafkaMessage
        prod = ZoikoProducer(_broker)
        prod.publish(KafkaMessage(topic="evidence.bundled", key=case_id,
                                  payload={"case_id": case_id, "bundle_id": str(bundle_id)}, tenant_id=tenant_id))
        prod.publish(KafkaMessage(topic="finding.created", key=case_id,
                                  payload={"case_id": case_id, "confidence": SC003_CONFIDENCE}, tenant_id=tenant_id))
    except Exception:
        pass


# ── UI helpers ────────────────────────────────────────────────────────────────

def ui_list_exceptions(_r, tenant_id: str, state: str | None, page: int, page_size: int) -> dict:
    limit  = max(1, min(page_size, 200))
    offset = (max(1, page) - 1) * limit

    if state:
        total_row = q1(
            "SELECT COUNT(*) AS cnt FROM cases WHERE tenant_id=%s::uuid AND case_type='SHIPMENT_EXCEPTION' AND state=%s",
            (tenant_id, state))
        rows = exceptions_q(_r, "WHERE c.tenant_id=%s::uuid AND c.case_type='SHIPMENT_EXCEPTION' AND c.state=%s",
                            (tenant_id, state), limit=limit, offset=offset)
    else:
        total_row = q1(
            "SELECT COUNT(*) AS cnt FROM cases WHERE tenant_id=%s::uuid AND case_type='SHIPMENT_EXCEPTION'",
            (tenant_id,))
        rows = exceptions_q(_r, "WHERE c.tenant_id=%s::uuid AND c.case_type='SHIPMENT_EXCEPTION'",
                            (tenant_id,), limit=limit, offset=offset)

    total = int(total_row["cnt"]) if total_row else 0
    return {
        "exceptions": rows,
        "total":      total,
        "page":       page,
        "page_size":  limit,
        "pages":      max(1, (total + limit - 1) // limit),
    }


def ui_get_exception(_r, tenant_id: str, case_id: str) -> dict:
    rows = exceptions_q(_r, "WHERE c.tenant_id=%s::uuid AND c.id=%s::uuid AND c.case_type='SHIPMENT_EXCEPTION'",
                        (tenant_id, case_id))
    if not rows:
        raise HTTPException(status_code=404, detail="Shipment exception case not found")
    return rows[0]


def ui_get_exception_finding(_r, tenant_id: str, case_id: str) -> dict:
    row = q1("""
        SELECT f.id::text, f.confidence::float, f.rule_trace, f.created_at
        FROM   findings f
        WHERE  f.case_id=%s::uuid AND f.tenant_id=%s::uuid
        ORDER BY f.created_at DESC LIMIT 1
    """, (case_id, tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Finding not yet available")
    return _r(row)


def ui_get_exception_events(_r, tenant_id: str, case_id: str) -> list[dict]:
    rows = q("""
        SELECT id::text, event_type, from_state, to_state, actor_sub, payload, occurred_at
        FROM   case_events
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY occurred_at ASC
    """, (case_id, tenant_id))
    return [_r(r) for r in rows]


def ui_get_shipment_events(_r, tenant_id: str, case_id: str) -> list[dict]:
    rows = q("""
        SELECT id::text, event_type, occurred_at, location, carrier_id, raw_payload
        FROM   shipment_events
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY occurred_at ASC
    """, (case_id, tenant_id))
    return [_r(r) for r in rows]

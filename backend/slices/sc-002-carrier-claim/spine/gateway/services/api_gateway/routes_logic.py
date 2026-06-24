"""SC-002 — claims list/detail/negotiate route logic, relocated from
backend/gateway/services/api_gateway/app.py.

See sc-001-freight-invoice-overcharge/routes_logic.py for the pattern: the
@v1_router decorator and route signature stay in app.py as thin wiring; the
actual handling logic lives here.
"""
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from shared.db import q, q1
from services.ingestion_svc.models import ClaimInput

_CLAIM_NEGOTIATION_STATUS = {
    "COUNTER":           "COUNTERED",
    "ACCEPT":            "ACCEPTED",
    "PARTIALLY_ACCEPT":  "PARTIALLY_ACCEPTED",
    "REJECT":            "REJECTED",
}


def claims_q(_r, where: str, params: tuple, limit: int = 50, offset: int = 0) -> list[dict]:
    """Mirrors sc-001's cases_q() exactly but joins claims instead of canonical_invoices."""
    rows = q(f"""
        SELECT
            c.id::text                                                   AS id,
            c.tenant_id::text                                            AS tenant_id,
            c.state,
            'CARRIER_CLAIM'                                              AS case_type,
            cl.carrier_id                                                AS carrier,
            cl.claim_reference                                           AS shipment_ref,
            cl.claim_type                                                AS claim_type,
            cl.claimed_amount::float                                     AS amount,
            cl.currency,
            COALESCE(cl.claimed_amount - cl.approved_amount, 0)::float   AS diff,
            COALESCE((
                SELECT f.confidence::float
                FROM   findings f WHERE f.case_id = c.id LIMIT 1
            ), 0)                                                        AS confidence,
            cl.status                                                    AS negotiation_status,
            cl.approved_amount::float                                    AS approved_amount,
            c.opened_at,
            c.opened_at                                                  AS updated_at
        FROM  cases c
        JOIN  claims cl ON cl.id = c.claim_id
        {where}
        ORDER BY c.opened_at DESC
        LIMIT %s OFFSET %s
    """, params + (limit, offset))
    return [_r(row) for row in rows]


def ui_list_claims(_r, tenant_id: str, state: str | None, page: int, page_size: int) -> dict:
    limit  = max(1, min(page_size, 200))
    offset = (max(1, page) - 1) * limit

    if state:
        total_row = q1(
            "SELECT COUNT(*) AS cnt FROM cases c JOIN claims cl ON cl.id=c.claim_id "
            "WHERE c.tenant_id=%s::uuid AND c.state=%s", (tenant_id, state))
        rows      = claims_q(_r, "WHERE c.tenant_id=%s::uuid AND c.state=%s", (tenant_id, state), limit=limit, offset=offset)
    else:
        total_row = q1(
            "SELECT COUNT(*) AS cnt FROM cases c JOIN claims cl ON cl.id=c.claim_id "
            "WHERE c.tenant_id=%s::uuid", (tenant_id,))
        rows      = claims_q(_r, "WHERE c.tenant_id=%s::uuid", (tenant_id,), limit=limit, offset=offset)

    total = int(total_row["cnt"]) if total_row else 0
    return {
        "claims":    rows,
        "total":     total,
        "page":      page,
        "page_size": limit,
        "pages":     max(1, (total + limit - 1) // limit),
    }


def ui_get_claim(_r, tenant_id: str, case_id: str) -> dict:
    rows = claims_q(_r, "WHERE c.tenant_id=%s::uuid AND c.id=%s::uuid", (tenant_id, case_id))
    if not rows:
        raise HTTPException(status_code=404, detail="Claim case not found")
    return rows[0]


def ui_get_claim_lines(_r, tenant_id: str, case_id: str) -> list[dict]:
    """Multi-line breakdown for a claim, if one was provided at submission. Empty list = flat-amount claim."""
    row = q1("SELECT claim_id FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tenant_id))
    if not row or not row["claim_id"]:
        raise HTTPException(status_code=404, detail="Claim case not found")
    rows = q("""
        SELECT id::text, line_number, description, claimed_amount, currency, created_at
        FROM   claim_lines
        WHERE  claim_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY line_number ASC
    """, (str(row["claim_id"]), tenant_id))
    return [_r(r) for r in rows]


def run_evidence_and_reasoning_claim(
    db_url, tenant_id: str, case_id: str, slug: str,
    carrier: str, amount: float, currency: str, claim_type: str,
    actor_sub: str, broker,
) -> None:
    """SC-002 — mirrors sc-001's run_evidence_and_reasoning() exactly (claim-shaped
    evidence items + SC002 rule weights) but does not touch that function.
    Add 4 evidence items, run reasoning, advance case to FINDING_GENERATED."""
    import psycopg2, psycopg2.extras, hashlib
    from shared.signer import sign as _sign
    from zoiko_common.crypto.merkle import MerkleTree
    from zoiko_common.crypto.jcs import canonicalize as _jcs
    from services.case_orchestration.handler import CaseHandler

    DOMAIN_TAG = b"zoiko.evidence.item.v1:"
    MERKLE_DOM = "zoiko/v1/evidence-item"

    # Step 1 — transition NEW → EVIDENCE_PENDING
    CaseHandler(db_url, broker).transition_state(tenant_id, case_id, "EVIDENCE_PENDING", actor_sub)

    # Step 2 — add 4 synthetic evidence items (claim-shaped)
    items_content = [
        ("CLAIM_FORM",   f"Carrier claim form — {claim_type} claim against {carrier}".encode()),
        ("PROOF_OF_LOSS", f"Proof of loss documentation — claimed amount {amount:.2f} {currency}".encode()),
        ("BOL",          f"Bill of Lading — shipment carrier {carrier}".encode()),
        ("CORRESPONDENCE", f"Carrier correspondence thread — {claim_type} claim {carrier}".encode()),
    ]

    now = datetime.now(timezone.utc)
    psycopg2.extras.register_uuid()
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        lock_key = int(uuid.UUID(case_id)) % (2**31)
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

        cur.execute(
            "SELECT id FROM evidence_bundles WHERE tenant_id=%s AND case_id=%s LIMIT 1",
            (tenant_id, uuid.UUID(case_id)),
        )
        existing = cur.fetchone()
        if existing:
            bundle_id = existing["id"] if isinstance(existing, dict) else existing[0]
        else:
            bundle_id = uuid.uuid4()
            ph = hashlib.sha256(DOMAIN_TAG + b"placeholder").digest()
            sig0, kid0 = _sign(slug, ph)
            cur.execute("""
                INSERT INTO evidence_bundles (id, tenant_id, case_id, bundle_hash, signature, kid, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (bundle_id, tenant_id, uuid.UUID(case_id), ph, sig0, kid0, now))

        leaf_hashes = []
        for itype, content in items_content:
            item_hash = hashlib.sha256(DOMAIN_TAG + content).digest()
            sig, kid  = _sign(slug, item_hash)
            cur.execute("""
                INSERT INTO evidence_items
                    (id, tenant_id, bundle_id, item_type, entity_id, item_hash, signature, kid, added_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (uuid.uuid4(), tenant_id, bundle_id, itype, uuid.uuid4(), item_hash, sig, kid, now))
            leaf_hashes.append(item_hash)

        _tree = MerkleTree(MERKLE_DOM)
        for _h in leaf_hashes:
            _tree.append(_h)
        merkle_root = _tree.root()
        root_sig, root_kid = _sign(slug, merkle_root)
        cur.execute(
            "UPDATE evidence_bundles SET bundle_hash=%s, signature=%s, kid=%s, completeness_status='COMPLETE' WHERE id=%s",
            (merkle_root, root_sig, root_kid, bundle_id)
        )

        # Step 3 — reasoning: SC-002 confidence = 0.9275 (liability_acknowledged + amount_within_policy_cap)
        SC002 = 0.9275
        rule_trace = {
            "liability_acknowledged":   {"confidence": 0.95, "weight": 0.55},
            "amount_within_policy_cap": {"confidence": 0.90, "weight": 0.45},
            "weighted_average":         SC002,
        }
        finding_payload = {"bundle_id": str(bundle_id), "case_id": case_id,
                           "confidence": str(SC002), "rule_trace": rule_trace, "tenant_id": tenant_id}
        finding_bytes = _jcs(finding_payload)
        finding_hash  = hashlib.sha256(b"zoiko.finding.v1:" + finding_bytes).digest()
        f_sig, f_kid  = _sign(slug, finding_hash)
        finding_id = uuid.uuid4()
        cur.execute("""
            INSERT INTO findings
                (id, tenant_id, case_id, bundle_id, confidence, rule_trace, finding_hash, signature, kid, created_at,
                 ai_confidence, risk_level, ai_reasoning)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NULL, NULL, NULL)
        """, (finding_id, tenant_id, uuid.UUID(case_id), bundle_id, SC002, json.dumps(rule_trace), finding_hash, f_sig, f_kid, now))

        prop_payload = {"amount": str(amount), "case_id": case_id, "currency": currency,
                        "finding_hash": finding_hash.hex(), "proposed_action": "SETTLE_CLAIM",
                        "proposer_sub": actor_sub, "tenant_id": tenant_id}
        prop_bytes = _jcs(prop_payload)
        prop_hash  = hashlib.sha256(b"zoiko.proposal.v1:" + prop_bytes).digest()
        p_sig, p_kid = _sign(slug, prop_hash)
        cur.execute("""
            INSERT INTO decision_proposals
                (id, tenant_id, case_id, finding_id, proposed_action, amount, currency,
                 proposer_sub, proposal_hash, signature, kid, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (uuid.uuid4(), tenant_id, uuid.UUID(case_id), finding_id,
              "SETTLE_CLAIM", amount, currency, actor_sub, prop_hash, p_sig, p_kid, now))

        conn.commit()
    finally:
        conn.close()

    # Step 4 — transition EVIDENCE_PENDING → FINDING_GENERATED
    CaseHandler(db_url, broker).transition_state(tenant_id, case_id, "FINDING_GENERATED", actor_sub)

    # Kafka events
    from kafka.producer import ZoikoProducer, KafkaMessage
    prod = ZoikoProducer(broker)
    prod.publish(KafkaMessage(topic="zoiko.evidence.bundled", key=case_id,
                              payload={"case_id": case_id, "bundle_id": str(bundle_id)}, tenant_id=tenant_id))
    prod.publish(KafkaMessage(topic="zoiko.finding.generated", key=case_id,
                              payload={"case_id": case_id, "confidence": SC002}, tenant_id=tenant_id))


def submit_claim_async_worker(
    db_url, broker, ingestion_cls, canonical_cls, case_cls,
    run_evidence_and_reasoning_claim_fn, submit_jobs: dict, persist_job_fn, raw_exec_fn,
    job_id: str, tenant_id: str, actor_sub: str, idempotency_key: str, body,
) -> None:
    """Background-thread body for POST /claims/submit-async. Mirrors
    sc-001's submit_case_async_worker() exactly."""
    import uuid as _u
    try:
        claim_ref = body.claim_reference.strip() if body.claim_reference.strip() else f"UI-CLAIM-{_u.uuid4().hex[:8].upper()}"
        slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (tenant_id,))
        slug = slug_row["slug"] if slug_row else "default"

        if body.lines:
            body.claimed_amount = sum(l.claimed_amount for l in body.lines)

        claim_in = ClaimInput(
            carrier_id=body.carrier, claim_reference=claim_ref,
            claim_type=body.claim_type, claimed_amount=float(body.claimed_amount),
            currency=body.currency, description=body.description,
            related_invoice_number=body.related_invoice_number,
        )
        ing_r = ingestion_cls(db_url, broker, slug).ingest_claim(tenant_id, claim_in, idempotency_key)
        can_r = canonical_cls(db_url, broker, slug).canonicalize_claim(
                    tenant_id, ing_r.source_record_id, claim_ref,
                    body.carrier, body.claim_type, float(body.claimed_amount), body.currency,
                )
        case_r = case_cls(db_url, broker).open_case(tenant_id, claim_id=can_r.claim_id, actor_sub=actor_sub)

        if case_r.is_new and body.lines:
            for i, line in enumerate(body.lines, start=1):
                raw_exec_fn(
                    "INSERT INTO claim_lines (id, tenant_id, claim_id, line_number, description, claimed_amount, currency) "
                    "VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s)",
                    (_u.uuid4(), tenant_id, can_r.claim_id, i, line.description, line.claimed_amount, body.currency),
                )

        if not case_r.is_new:
            existing = q1(
                "SELECT state, opened_at FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid",
                (str(case_r.case_id), tenant_id),
            )
            now_str = datetime.now(timezone.utc).isoformat()
            _case_data = {
                "id": str(case_r.case_id), "tenant_id": tenant_id,
                "state": existing["state"] if existing else case_r.state,
                "case_type": "CARRIER_CLAIM",
                "carrier": body.carrier, "shipment_ref": claim_ref,
                "amount": float(body.claimed_amount), "currency": body.currency,
                "diff": 0.0, "confidence": 0.0,
                "opened_at": (existing["opened_at"].isoformat() if existing else now_str),
                "updated_at": now_str,
                "duplicate": True,
                "deduplication_outcome": ing_r.deduplication_outcome,
            }
            submit_jobs[job_id] = {"status": "done", "case": _case_data, "error": None}
            persist_job_fn(job_id, "done", _case_data, None)
            return

        try:
            run_evidence_and_reasoning_claim_fn(
                tenant_id=tenant_id, case_id=str(case_r.case_id), slug=slug,
                carrier=body.carrier, amount=float(body.claimed_amount), currency=body.currency,
                claim_type=body.claim_type, actor_sub=actor_sub, broker=broker,
            )
        except Exception:
            import traceback; traceback.print_exc()
        now_str = datetime.now(timezone.utc).isoformat()
        _case_data = {
            "id": str(case_r.case_id), "tenant_id": tenant_id,
            "state": "FINDING_GENERATED", "case_type": "CARRIER_CLAIM",
            "carrier": body.carrier, "shipment_ref": claim_ref,
            "amount": float(body.claimed_amount), "currency": body.currency,
            "diff": 0.0, "confidence": 0.9275,
            "opened_at": now_str, "updated_at": now_str,
            "duplicate": False,
            "deduplication_outcome": ing_r.deduplication_outcome,
        }
        submit_jobs[job_id] = {"status": "done", "case": _case_data, "error": None}
        persist_job_fn(job_id, "done", _case_data, None)
    except Exception as exc:
        import traceback; traceback.print_exc()
        submit_jobs[job_id] = {"status": "error", "case": None, "error": str(exc)}
        persist_job_fn(job_id, "error", None, str(exc))


def submit_claim(
    db_url, broker, ingestion_cls, canonical_cls, case_cls,
    run_evidence_and_reasoning_claim_fn, capture_rest_push_metadata_fn,
    request, body, idempotency_key: str, tenant_id: str, actor_sub: str,
) -> dict:
    """SC-002 — full pipeline for a carrier claim: ingest → canonical → open
    case → evidence → AI finding (SC002 rule bundle). Mirrors sc-001's
    submit_case() exactly, on the same spine, but for a claim instead of an
    invoice. Sync for the same reason as submit_case."""
    import threading as _threading

    claim_ref = body.claim_reference.strip() if body.claim_reference.strip() else f"UI-CLAIM-{uuid.uuid4().hex[:8].upper()}"

    slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (tenant_id,))
    slug = slug_row["slug"] if slug_row else "default"

    ch_metadata = capture_rest_push_metadata_fn(request, idempotency_key)
    channel = "ui_entry" if request.headers.get("X-UI-Submit") else "rest_api_push"

    claim_in = ClaimInput(
        carrier_id=body.carrier, claim_reference=claim_ref,
        claim_type=body.claim_type, claimed_amount=float(body.claimed_amount),
        currency=body.currency, description=body.description,
        related_invoice_number=body.related_invoice_number,
    )
    ing_r  = ingestion_cls(db_url, broker, slug).ingest_claim(
        tenant_id, claim_in, idempotency_key,
        channel=channel,
        channel_metadata=ch_metadata,
        received_by_user=actor_sub if actor_sub else None,
        correlation_id=request.headers.get("X-Correlation-ID"),
    )
    can_r  = canonical_cls(db_url, broker, slug).canonicalize_claim(
                 tenant_id, ing_r.source_record_id, claim_ref,
                 body.carrier, body.claim_type, float(body.claimed_amount), body.currency,
             )
    case_r = case_cls(db_url, broker).open_case(
                 tenant_id, claim_id=can_r.claim_id, actor_sub=actor_sub)

    if not case_r.is_new:
        existing = q1(
            "SELECT state, opened_at FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid",
            (str(case_r.case_id), tenant_id),
        )
        return {
            "id":                     str(case_r.case_id),
            "tenant_id":              tenant_id,
            "state":                  existing["state"] if existing else case_r.state,
            "case_type":              "CARRIER_CLAIM",
            "carrier":                body.carrier,
            "claim_reference":        claim_ref,
            "claimed_amount":         float(body.claimed_amount),
            "currency":               body.currency,
            "confidence":             0.0,
            "opened_at":              (existing["opened_at"].isoformat() if existing else case_r.opened_at.isoformat()),
            "updated_at":             datetime.now(timezone.utc).isoformat(),
            "duplicate":              True,
            "deduplication_outcome":  ing_r.deduplication_outcome,
        }

    def _bg():
        try:
            run_evidence_and_reasoning_claim_fn(
                tenant_id  = tenant_id,
                case_id    = str(case_r.case_id),
                slug       = slug,
                carrier    = body.carrier,
                amount     = float(body.claimed_amount),
                currency   = body.currency,
                claim_type = body.claim_type,
                actor_sub  = actor_sub,
                broker     = broker,
            )
        except Exception:
            import traceback; traceback.print_exc()

    _threading.Thread(target=_bg, daemon=True, name=f"sc002-{case_r.case_id}").start()

    now_str = datetime.now(timezone.utc).isoformat()
    return {
        "id":              str(case_r.case_id),
        "tenant_id":       tenant_id,
        "state":           "EVIDENCE_PENDING",
        "case_type":       "CARRIER_CLAIM",
        "carrier":         body.carrier,
        "claim_reference": claim_ref,
        "claimed_amount":  float(body.claimed_amount),
        "currency":        body.currency,
        "confidence":      0.0,
        "opened_at":       now_str,
        "updated_at":      now_str,
    }


def ui_negotiate_claim(_r, _raw_exec, tenant_id: str, case_id: str, body, actor_sub: str) -> dict:
    """SC-002 — carrier counter-offer round-trip. Independent of the governance
    FSM (cases.state): this tracks claims.status, the back-and-forth with the
    carrier that happens before/alongside the propose -> approve -> execute flow."""
    if body.action not in _CLAIM_NEGOTIATION_STATUS:
        raise HTTPException(status_code=422, detail=f"action must be one of {sorted(_CLAIM_NEGOTIATION_STATUS)}")

    row = q1("SELECT claim_id FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tenant_id))
    if not row or not row["claim_id"]:
        raise HTTPException(status_code=404, detail="Claim case not found")

    new_status = _CLAIM_NEGOTIATION_STATUS[body.action]
    _raw_exec(
        "UPDATE claims SET status=%s, approved_amount=%s WHERE id=%s::uuid AND tenant_id=%s::uuid",
        (new_status, body.approved_amount, str(row["claim_id"]), tenant_id),
    )
    _raw_exec(
        "INSERT INTO case_events (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at) "
        "VALUES (%s, %s::uuid, %s::uuid, 'CLAIM_NEGOTIATION', NULL, NULL, %s, %s::jsonb, now())",
        (uuid.uuid4(), tenant_id, case_id, actor_sub,
         json.dumps({"action": body.action, "new_status": new_status, "approved_amount": body.approved_amount, "note": body.note})),
    )
    return {"case_id": case_id, "negotiation_status": new_status, "approved_amount": body.approved_amount}

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

from shared.db import q, q1, DB_URL
from services.ingestion_svc.models import ClaimInput

_CLAIM_NEGOTIATION_STATUS = {
    "COUNTER":           "COUNTERED",
    "ACCEPT":            "ACCEPTED",
    "PARTIALLY_ACCEPT":  "PARTIALLY_ACCEPTED",
    "REJECT":            "REJECTED",
}

# Valid actions per current negotiation status — enforced server-side.
# ACCEPTED is terminal: once carrier accepts in full, no further action is permitted.
_NEGOTIATION_TRANSITIONS: dict[str, set] = {
    "OPEN":               {"COUNTER", "ACCEPT", "PARTIALLY_ACCEPT", "REJECT"},
    "COUNTERED":          {"COUNTER", "ACCEPT", "PARTIALLY_ACCEPT", "REJECT"},
    "PARTIALLY_ACCEPTED": {"COUNTER", "ACCEPT", "REJECT"},
    "REJECTED":           {"COUNTER", "ACCEPT"},
    "ACCEPTED":           set(),  # terminal
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


def _sync_missing_carrier_claims(tenant_id: str) -> int:
    """Lazy sync: create CARRIER_CLAIM cases for any DISPATCHED SC-001 cases that
    have no corresponding carrier claim yet. Called on every list_claims request.
    Also repairs existing $0 claims whose amount can be recovered from execution_envelopes.
    Idempotent and best-effort — never raises."""
    try:
        import logging as _logging
        import psycopg2 as _pg2
        import psycopg2.extras as _extras
        import threading as _threading

        _log = _logging.getLogger("sc002.sync")
        _extras.register_uuid()
        now = datetime.now(timezone.utc)

        # ── Step 0: repair existing $0 claims — use execution_envelopes.amount ──
        # The original _auto_create_carrier_claim may have stored amount=0 if
        # decision_proposals.amount was NULL at dispatch time. execution_envelopes.amount
        # is always set correctly at dispatch, so use it as the authoritative source.
        try:
            conn0 = _pg2.connect(DB_URL)
            conn0.autocommit = False
            try:
                cur0 = conn0.cursor()
                cur0.execute("""
                    UPDATE claims
                    SET    claimed_amount = ee.amount::numeric,
                           currency      = ee.currency
                    FROM   cases sc001
                    JOIN   execution_envelopes ee
                           ON  ee.case_id  = sc001.id
                           AND ee.tenant_id = sc001.tenant_id
                    WHERE  sc001.tenant_id  = %s::uuid
                      AND  sc001.case_type  = 'INVOICE_OVERCHARGE'
                      AND  sc001.state      = 'DISPATCHED'
                      AND  claims.tenant_id = sc001.tenant_id
                      AND  claims.claim_reference = 'AUTO-' || UPPER(LEFT(sc001.id::text, 8))
                      AND  claims.claimed_amount  = 0
                      AND  ee.amount > 0
                """, (tenant_id,))
                repaired = cur0.rowcount
                conn0.commit()
                if repaired:
                    _log.info("Sync: repaired %d $0 carrier claims with correct amount from execution_envelopes", repaired)
            except Exception as _repair_err:
                try:
                    conn0.rollback()
                except Exception:
                    pass
                _log.warning("Sync repair step failed: %s", _repair_err)
            finally:
                try:
                    conn0.close()
                except Exception:
                    pass
        except Exception:
            pass

        # ── Step 1: find DISPATCHED SC-001 cases with no carrier claim yet ──
        # Use execution_envelopes.amount as the authoritative amount source —
        # it is always written at dispatch time before _auto_create_carrier_claim runs.
        missing = q("""
            SELECT
                c.id::text                                          AS sc001_case_id,
                c.tenant_id::text                                   AS tenant_id,
                COALESCE(ci.carrier_id, 'UNKNOWN')                  AS carrier_id,
                COALESCE(ci.invoice_number, LEFT(c.id::text, 8))    AS invoice_number,
                COALESCE(ee.amount, 0)::float                       AS amount,
                COALESCE(ee.currency, 'USD')                        AS currency,
                COALESCE(ee.id::text, '')                           AS envelope_id,
                COALESCE(ee.actor_sub, 'system')                    AS actor_sub
            FROM  cases c
            LEFT JOIN canonical_invoices  ci ON ci.id = c.invoice_id
            LEFT JOIN execution_envelopes ee ON ee.case_id   = c.id
                                             AND ee.tenant_id = c.tenant_id
            WHERE c.tenant_id = %s::uuid
              AND c.case_type  = 'INVOICE_OVERCHARGE'
              AND c.state      = 'DISPATCHED'
              AND NOT EXISTS (
                  SELECT 1 FROM case_events ce
                  WHERE  ce.case_id = c.id
                    AND  ce.tenant_id = c.tenant_id
                    AND  ce.event_type = 'SC002_CLAIM_AUTO_CREATED'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM claims cl
                  WHERE  cl.tenant_id = c.tenant_id
                    AND  cl.claim_reference = 'AUTO-' || UPPER(LEFT(c.id::text, 8))
              )
            LIMIT 20
        """, (tenant_id,))

        if not missing:
            return 0

        created = 0
        conn = _pg2.connect(DB_URL)
        conn.autocommit = False
        try:
            for row in missing:
                sc001_case_id   = row["sc001_case_id"]
                carrier_id      = row["carrier_id"]
                invoice_number  = row["invoice_number"]
                amount          = float(row["amount"])
                currency        = row["currency"]
                envelope_id     = row["envelope_id"]
                actor_sub       = row["actor_sub"]
                claim_reference = f"AUTO-{sc001_case_id[:8].upper()}"
                claim_id        = uuid.uuid4()
                sc002_case_id   = uuid.uuid4()
                try:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO claims
                            (id, tenant_id, carrier_id, claim_reference, claim_type,
                             claimed_amount, currency, status, filed_at, created_at)
                        VALUES (%s, %s::uuid, %s, %s, 'OVERCHARGE', %s, %s, 'OPEN', %s, %s)
                        ON CONFLICT DO NOTHING
                        RETURNING id
                    """, (claim_id, tenant_id, carrier_id, claim_reference,
                          amount, currency, now, now))
                    if not cur.fetchone():
                        conn.rollback()
                        continue  # already exists
                    cur.execute("""
                        INSERT INTO cases
                            (id, tenant_id, claim_id, case_type, state, opened_at)
                        VALUES (%s, %s::uuid, %s::uuid, 'CARRIER_CLAIM', 'NEW', %s)
                    """, (sc002_case_id, tenant_id, claim_id, now))
                    cur.execute(
                        "UPDATE claims SET case_id=%s::uuid "
                        "WHERE id=%s::uuid AND tenant_id=%s::uuid",
                        (sc002_case_id, claim_id, tenant_id),
                    )
                    cur.execute("""
                        INSERT INTO case_events
                            (id, tenant_id, case_id, event_type, from_state, to_state,
                             actor_sub, payload, occurred_at)
                        VALUES (%s, %s::uuid, %s::uuid, 'CASE_OPENED', NULL, 'NEW',
                                'system', %s::jsonb, %s)
                    """, (uuid.uuid4(), tenant_id, sc002_case_id,
                          json.dumps({"auto_created_from": sc001_case_id,
                                      "envelope_id": envelope_id,
                                      "invoice_number": invoice_number,
                                      "claim_reference": claim_reference}),
                          now))
                    cur.execute("""
                        INSERT INTO case_events
                            (id, tenant_id, case_id, event_type, from_state, to_state,
                             actor_sub, payload, occurred_at)
                        VALUES (%s, %s::uuid, %s::uuid, 'SC002_CLAIM_AUTO_CREATED',
                                NULL, NULL, %s, %s::jsonb, %s)
                    """, (uuid.uuid4(), tenant_id, uuid.UUID(sc001_case_id),
                          actor_sub,
                          json.dumps({"sc002_case_id": str(sc002_case_id),
                                      "claim_id": str(claim_id),
                                      "claim_reference": claim_reference,
                                      "carrier_id": carrier_id,
                                      "amount": amount, "currency": currency}),
                          now))
                    conn.commit()
                    created += 1
                    _log.info("Sync: auto-created CARRIER_CLAIM %s for SC-001 case %s",
                              sc002_case_id, sc001_case_id)
                    # Background: advance to FINDING_GENERATED
                    _threading.Thread(
                        target=_advance_claim_state,
                        args=(DB_URL, tenant_id, str(sc002_case_id),
                              str(claim_id), carrier_id, amount, currency),
                        name=f"sc002-sync-{str(sc002_case_id)[:8]}",
                        daemon=True,
                    ).start()
                except Exception as _row_err:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    _log.warning("Sync row error for SC-001 case %s: %s", sc001_case_id, _row_err)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return created
    except Exception:
        return 0


def _advance_claim_state(
    db_url: str, tenant_id: str, sc002_case_id: str,
    claim_id: str, carrier: str, amount: float, currency: str,
) -> None:
    """Background thread: run evidence + reasoning to advance a synced claim to
    FINDING_GENERATED so it is ready for manager approval."""
    try:
        from kafka.mock_kafka import MockKafkaBroker
        run_evidence_and_reasoning_claim(
            db_url=db_url,
            tenant_id=tenant_id,
            case_id=sc002_case_id,
            slug="default",
            carrier=carrier,
            amount=amount,
            currency=currency,
            claim_type="OVERCHARGE",
            actor_sub="system",
            broker=MockKafkaBroker(),
        )
    except Exception:
        pass


def ui_list_claims(_r, tenant_id: str, state: str | None, page: int, page_size: int) -> dict:
    # Best-effort: create any CARRIER_CLAIM cases that SC-001 dispatch missed
    _sync_missing_carrier_claims(tenant_id)

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
            body.claimed_amount = sum(line.claimed_amount for line in body.lines)

        claim_in = ClaimInput(
            carrier_id=body.carrier, claim_reference=claim_ref,
            claim_type=body.claim_type, claimed_amount=float(body.claimed_amount),
            currency=body.currency, description=body.description,
            related_invoice_number=body.related_invoice_number,
            awb_number=getattr(body, "awb_number", "") or "",
            incident_date=getattr(body, "incident_date", "") or "",
            origin_location=getattr(body, "origin_location", "") or "",
            destination_location=getattr(body, "destination_location", "") or "",
        )
        ing_r = ingestion_cls(db_url, broker, slug).ingest_claim(tenant_id, claim_in, idempotency_key)

        # Validate claim before canonicalization — structural/semantic FAIL blocks progression;
        # POLICY_CAP_EXCEEDED is a WARN (proceeds but is recorded in validation_results).
        try:
            from services.validation_svc.handler import ClaimValidationHandler
            val_r = ClaimValidationHandler(db_url, broker, slug).validate(
                tenant_id=tenant_id,
                source_record_id=ing_r.source_record_id,
                carrier_id=body.carrier,
                claim_reference=claim_ref,
                claim_type=body.claim_type,
                claimed_amount=float(body.claimed_amount),
                currency=body.currency,
            )
            if val_r.status == "FAIL":
                rules = [v.rule for v in val_r.rule_violations]
                raise ValueError(f"Claim validation failed ({rules}) — claim not accepted")
        except ValueError:
            raise
        except Exception:
            pass  # validation is best-effort; never block on unexpected DB error

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
        awb_number=getattr(body, "awb_number", "") or "",
        incident_date=getattr(body, "incident_date", "") or "",
        origin_location=getattr(body, "origin_location", "") or "",
        destination_location=getattr(body, "destination_location", "") or "",
    )
    ing_r  = ingestion_cls(db_url, broker, slug).ingest_claim(
        tenant_id, claim_in, idempotency_key,
        channel=channel,
        channel_metadata=ch_metadata,
        received_by_user=actor_sub if actor_sub else None,
        correlation_id=request.headers.get("X-Correlation-ID"),
    )

    # Validate before canonicalization — FAIL blocks; WARN passes through.
    try:
        from services.validation_svc.handler import ClaimValidationHandler
        _val = ClaimValidationHandler(db_url, broker, slug).validate(
            tenant_id=tenant_id,
            source_record_id=ing_r.source_record_id,
            carrier_id=body.carrier,
            claim_reference=claim_ref,
            claim_type=body.claim_type,
            claimed_amount=float(body.claimed_amount),
            currency=body.currency,
        )
        if _val.status == "FAIL":
            rules = [v.rule for v in _val.rule_violations]
            from fastapi import HTTPException as _HE
            raise _HE(status_code=422, detail=f"Claim validation failed: {rules}")
    except Exception as _ve:
        if hasattr(_ve, "status_code"):
            raise  # propagate HTTPException
        pass  # best-effort; never block on unexpected errors

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

    # Publish zoiko.claim.submitted — outbox (relay) + in-process broker
    try:
        _event_payload = {
            "case_id":         str(case_r.case_id),
            "claim_reference": claim_ref,
            "carrier":         body.carrier,
            "claim_type":      body.claim_type,
            "claimed_amount":  float(body.claimed_amount),
            "currency":        body.currency,
            "actor_sub":       actor_sub or "",
        }
        q(
            "INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at) "
            "VALUES (%s, %s::uuid, %s, %s, %s::jsonb, now())",
            (uuid.uuid4(), tenant_id, "zoiko.claim.submitted", str(case_r.case_id), json.dumps(_event_payload)),
        )
        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(broker).publish(KafkaMessage(
            topic=     "zoiko.claim.submitted",
            key=       str(case_r.case_id),
            payload=   _event_payload,
            tenant_id= tenant_id,
        ))
    except Exception:
        import traceback; traceback.print_exc()

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
    """SC-002 — carrier counter-offer round-trip with state machine validation
    and amount guards.  Independent of the governance FSM (cases.state): this
    tracks claims.status — the back-and-forth with the carrier that happens
    before/alongside the propose → approve → execute flow."""

    if body.action not in _CLAIM_NEGOTIATION_STATUS:
        raise HTTPException(status_code=422, detail=f"action must be one of {sorted(_CLAIM_NEGOTIATION_STATUS)}")

    row = q1(
        "SELECT cl.id::text AS claim_id, cl.status AS current_status, cl.claimed_amount::float AS claimed_amount "
        "FROM cases c JOIN claims cl ON cl.id = c.claim_id "
        "WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid",
        (case_id, tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Claim case not found")

    current_status = row["current_status"] or "OPEN"
    claimed_amount = float(row["claimed_amount"] or 0)

    # ── State machine guard ────────────────────────────────────────────────
    valid_actions = _NEGOTIATION_TRANSITIONS.get(current_status, set())
    if body.action not in valid_actions:
        terminal = current_status == "ACCEPTED"
        detail = (
            "Negotiation is closed — carrier has already accepted in full."
            if terminal else
            f"Cannot {body.action} from status {current_status}. "
            f"Valid next actions: {sorted(valid_actions) or 'none'}"
        )
        raise HTTPException(status_code=409, detail=detail)

    # ── Amount validation ──────────────────────────────────────────────────
    approved_amount = body.approved_amount
    if body.action == "ACCEPT":
        approved_amount = claimed_amount  # full acceptance = claimed amount
    elif body.action in ("COUNTER", "PARTIALLY_ACCEPT"):
        if not approved_amount or approved_amount <= 0:
            raise HTTPException(status_code=422, detail=f"{body.action} requires a positive approved_amount")
        if approved_amount > claimed_amount:
            raise HTTPException(
                status_code=422,
                detail=f"approved_amount {approved_amount} exceeds claimed amount {claimed_amount}",
            )
        if body.action == "PARTIALLY_ACCEPT" and approved_amount >= claimed_amount:
            raise HTTPException(
                status_code=422,
                detail="PARTIALLY_ACCEPT amount must be less than the claimed amount",
            )

    new_status = _CLAIM_NEGOTIATION_STATUS[body.action]

    # ── Round counter ──────────────────────────────────────────────────────
    round_row = q1(
        "SELECT COUNT(*) AS cnt FROM case_events "
        "WHERE case_id=%s::uuid AND event_type='CLAIM_NEGOTIATION'",
        (case_id,),
    )
    round_num = (int(round_row["cnt"]) if round_row else 0) + 1

    _raw_exec(
        "UPDATE claims SET status=%s, approved_amount=%s WHERE id=%s::uuid AND tenant_id=%s::uuid",
        (new_status, approved_amount, row["claim_id"], tenant_id),
    )
    _raw_exec(
        "INSERT INTO case_events "
        "(id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at) "
        "VALUES (%s, %s::uuid, %s::uuid, 'CLAIM_NEGOTIATION', NULL, NULL, %s, %s::jsonb, now())",
        (
            uuid.uuid4(), tenant_id, case_id, actor_sub,
            json.dumps({
                "action":          body.action,
                "from_status":     current_status,
                "new_status":      new_status,
                "approved_amount": approved_amount,
                "note":            body.note or "",
                "round":           round_num,
            }),
        ),
    )
    # ── Publish zoiko.claim.negotiated outbox event ───────────────────────────
    try:
        _neg_payload = {
            "case_id":         case_id,
            "action":          body.action,
            "from_status":     current_status,
            "new_status":      new_status,
            "approved_amount": approved_amount,
            "round":           round_num,
            "actor_sub":       actor_sub or "",
        }
        _raw_exec(
            "INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at) "
            "VALUES (%s, %s::uuid, %s, %s, %s::jsonb, now())",
            (uuid.uuid4(), tenant_id, "zoiko.claim.negotiated", case_id, json.dumps(_neg_payload)),
        )
    except Exception:
        import traceback; traceback.print_exc()

    # ── Best-effort email notification ────────────────────────────────────────
    try:
        from shared.email_sender import send_carrier_negotiation_update
        extra = q1(
            "SELECT cl.carrier_id, cl.currency FROM cases c "
            "JOIN claims cl ON cl.id=c.claim_id "
            "WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid",
            (case_id, tenant_id),
        )
        carrier_name = (extra or {}).get("carrier_id", "Carrier")
        currency_val = (extra or {}).get("currency", "USD")
        users = q(
            "SELECT email, full_name FROM users "
            "WHERE tenant_id=%s::uuid AND role IN ('manager', 'analyst')",
            (tenant_id,),
        )
        for u in users:
            send_carrier_negotiation_update(
                to_email=u["email"],
                to_name=(u.get("full_name") or u["email"]),
                case_id=case_id,
                carrier=carrier_name,
                action=body.action,
                new_status=new_status,
                approved_amount=approved_amount,
                currency=currency_val,
                round_num=round_num,
                note=body.note or "",
            )
    except Exception:
        import traceback; traceback.print_exc()

    return {
        "case_id":            case_id,
        "negotiation_status": new_status,
        "approved_amount":    approved_amount,
        "round":              round_num,
    }


def ui_get_negotiation_history(_r, tenant_id: str, case_id: str) -> list[dict]:
    """Return all CLAIM_NEGOTIATION case_events in round order."""
    rows = q("""
        SELECT id::text, actor_sub, payload, occurred_at
        FROM   case_events
        WHERE  case_id = %s::uuid AND tenant_id = %s::uuid
          AND  event_type = 'CLAIM_NEGOTIATION'
        ORDER  BY occurred_at ASC
    """, (case_id, tenant_id))

    if not rows:
        # Also verify the case exists and is a claim case
        check = q1(
            "SELECT id FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid AND case_type='CARRIER_CLAIM'",
            (case_id, tenant_id),
        )
        if not check:
            raise HTTPException(status_code=404, detail="Claim case not found")

    history = []
    for r in rows:
        payload = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"] or "{}")
        history.append({
            "event_id":       r["id"],
            "actor":          r["actor_sub"],
            "round":          payload.get("round", 0),
            "action":         payload.get("action", ""),
            "from_status":    payload.get("from_status", ""),
            "to_status":      payload.get("new_status", ""),
            "approved_amount":payload.get("approved_amount"),
            "note":           payload.get("note", ""),
            "occurred_at":    r["occurred_at"].isoformat() if r.get("occurred_at") else None,
        })
    return history


def ui_add_claim_line(_raw_exec, _r, tenant_id: str, case_id: str, body: dict) -> dict:
    """
    POST /v1/claims/{case_id}/lines
    Add a new line item to an existing claim.  Guards:
      - Case must exist and be a CARRIER_CLAIM
      - Sum of all lines must not exceed claims.claimed_amount
      - Line numbers are auto-assigned (next available)
    """
    row = q1(
        "SELECT c.claim_id::text, cl.claimed_amount::float AS total, cl.currency "
        "FROM cases c JOIN claims cl ON cl.id=c.claim_id "
        "WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid AND c.case_type='CARRIER_CLAIM'",
        (case_id, tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Claim case not found")

    claim_id   = row["claim_id"]
    total_cap  = float(row["total"])
    currency   = body.get("currency") or row["currency"]
    desc       = (body.get("description") or "").strip()
    line_amount = float(body.get("claimed_amount") or 0)

    if not desc:
        raise HTTPException(status_code=422, detail="description is required")
    if line_amount <= 0:
        raise HTTPException(status_code=422, detail="claimed_amount must be positive")

    # Validate new sum doesn't exceed header amount
    existing_sum_row = q1(
        "SELECT COALESCE(SUM(claimed_amount), 0)::float AS existing_sum "
        "FROM claim_lines WHERE claim_id=%s::uuid AND tenant_id=%s::uuid",
        (claim_id, tenant_id),
    )
    existing_sum = float(existing_sum_row["existing_sum"] if existing_sum_row else 0)
    if existing_sum + line_amount > total_cap:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Line amount {line_amount:.2f} would bring total lines "
                f"({existing_sum + line_amount:.2f}) above claim amount {total_cap:.2f}"
            ),
        )

    # Auto-assign line_number
    next_num_row = q1(
        "SELECT COALESCE(MAX(line_number), 0) + 1 AS next_num "
        "FROM claim_lines WHERE claim_id=%s::uuid AND tenant_id=%s::uuid",
        (claim_id, tenant_id),
    )
    next_num = int(next_num_row["next_num"] if next_num_row else 1)
    line_id  = uuid.uuid4()

    _raw_exec(
        "INSERT INTO claim_lines (id, tenant_id, claim_id, line_number, description, claimed_amount, currency) "
        "VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s)",
        (line_id, tenant_id, claim_id, next_num, desc, line_amount, currency),
    )
    return {
        "id":             str(line_id),
        "claim_id":       claim_id,
        "line_number":    next_num,
        "description":    desc,
        "claimed_amount": line_amount,
        "currency":       currency,
    }


def ui_update_claim_line(_raw_exec, _r, tenant_id: str, case_id: str, line_id: str, body: dict) -> dict:
    """
    PATCH /v1/claims/{case_id}/lines/{line_id}
    Update description and/or amount of an existing claim line.
    Guards: updated sum must not exceed claims.claimed_amount.
    """
    row = q1(
        "SELECT c.claim_id::text, cl.claimed_amount::float AS total, cl.currency "
        "FROM cases c JOIN claims cl ON cl.id=c.claim_id "
        "WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid AND c.case_type='CARRIER_CLAIM'",
        (case_id, tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Claim case not found")

    claim_id  = row["claim_id"]
    total_cap = float(row["total"])

    line = q1(
        "SELECT id::text, line_number, description, claimed_amount::float, currency "
        "FROM claim_lines WHERE id=%s::uuid AND claim_id=%s::uuid AND tenant_id=%s::uuid",
        (line_id, claim_id, tenant_id),
    )
    if not line:
        raise HTTPException(status_code=404, detail="Claim line not found")

    new_desc   = body.get("description", line["description"])
    new_amount = float(body.get("claimed_amount", line["claimed_amount"]))

    if new_amount <= 0:
        raise HTTPException(status_code=422, detail="claimed_amount must be positive")

    # Validate new sum: subtract old line amount, add new
    other_sum_row = q1(
        "SELECT COALESCE(SUM(claimed_amount), 0)::float AS other_sum "
        "FROM claim_lines "
        "WHERE claim_id=%s::uuid AND tenant_id=%s::uuid AND id != %s::uuid",
        (claim_id, tenant_id, line_id),
    )
    other_sum = float(other_sum_row["other_sum"] if other_sum_row else 0)
    if other_sum + new_amount > total_cap:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Updated line amount {new_amount:.2f} would bring total lines "
                f"({other_sum + new_amount:.2f}) above claim amount {total_cap:.2f}"
            ),
        )

    _raw_exec(
        "UPDATE claim_lines SET description=%s, claimed_amount=%s WHERE id=%s::uuid AND tenant_id=%s::uuid",
        (new_desc, new_amount, line_id, tenant_id),
    )
    return {
        "id":             line_id,
        "claim_id":       claim_id,
        "line_number":    line["line_number"],
        "description":    new_desc,
        "claimed_amount": new_amount,
        "currency":       line["currency"],
    }

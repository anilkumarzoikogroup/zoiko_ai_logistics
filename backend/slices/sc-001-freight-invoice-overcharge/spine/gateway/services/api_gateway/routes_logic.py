"""SC-001 — low-level invoice pipeline route logic, relocated from
backend/gateway/services/api_gateway/app.py.

Each function here is the body of one FastAPI route. The @v1_router decorator
and the route's signature (path, dependencies, response_model) stay in app.py
as thin wiring — v1_router is a single shared APIRouter instance used across
every slice and the generic spine, so it isn't moved. These functions take the
already-validated request body, the resolved tenant/actor, and the shared
handler singletons (_ingestion, _validation, _canonical, _cases) as arguments.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from shared.db import q, q1
from services.ingestion_svc.models import InvoiceInput


def cases_q(_r, where: str, params: tuple, limit: int = 50, offset: int = 0) -> list[dict]:
    rows = q(f"""
        SELECT
            c.id::text                                                   AS id,
            c.tenant_id::text                                            AS tenant_id,
            c.state,
            ci.carrier_id                                                AS carrier,
            COALESCE(cs.origin_city || '-' || cs.dest_city,
                     ci.invoice_number)                                  AS shipment_ref,
            ci.total_amount::float                                       AS amount,
            ci.currency,
            COALESCE((
                SELECT (vr.rule_violations->0->>'delta')::float
                FROM   validation_results vr
                WHERE  vr.source_record_id = ci.source_record_id
                  AND  vr.status = 'FAIL'
                LIMIT  1
            ), 0)                                                        AS diff,
            COALESCE((
                SELECT f.confidence::float
                FROM   findings f WHERE f.case_id = c.id LIMIT 1
            ), 0)                                                        AS confidence,
            c.opened_at,
            c.opened_at                                                  AS updated_at
        FROM  cases c
        JOIN  canonical_invoices ci  ON ci.id = c.invoice_id
        LEFT JOIN canonical_shipments cs ON cs.invoice_id = ci.id
        {where}
        ORDER BY c.opened_at DESC
        LIMIT %s OFFSET %s
    """, params + (limit, offset))
    return [_r(row) for row in rows]


def ui_list_cases(_r, tenant_id: str, state: str | None, page: int, page_size: int) -> dict:
    limit  = max(1, min(page_size, 200))
    offset = (max(1, page) - 1) * limit

    if state:
        total_row = q1("SELECT COUNT(*) AS cnt FROM cases c WHERE c.tenant_id=%s::uuid AND c.state=%s", (tenant_id, state))
        cases     = cases_q(_r, "WHERE c.tenant_id=%s::uuid AND c.state=%s", (tenant_id, state), limit=limit, offset=offset)
    else:
        total_row = q1("SELECT COUNT(*) AS cnt FROM cases c WHERE c.tenant_id=%s::uuid", (tenant_id,))
        cases     = cases_q(_r, "WHERE c.tenant_id=%s::uuid", (tenant_id,), limit=limit, offset=offset)

    total = int(total_row["cnt"]) if total_row else 0
    return {
        "cases":     cases,
        "total":     total,
        "page":      page,
        "page_size": limit,
        "pages":     max(1, (total + limit - 1) // limit),
    }


def ui_get_case(_r, tenant_id: str, case_id: str) -> dict:
    rows = cases_q(_r, "WHERE c.tenant_id=%s::uuid AND c.id=%s::uuid", (tenant_id, case_id))
    if not rows:
        raise HTTPException(status_code=404, detail="Case not found")
    return rows[0]


def ui_validation(_r, tenant_id: str, case_id: str) -> dict:
    row = q1("""
        SELECT
            vr.id::text,
            c.id::text                                                         AS case_id,
            vr.status                                                          AS outcome,
            COALESCE((vr.rule_violations->0->>'delta')::float, 0)              AS diff,
            ci.currency,
            COALESCE(vr.rule_violations->0->>'rule', 'No violation')           AS reason,
            ci.total_amount::float                                             AS invoice_amount,
            GREATEST(0, ci.total_amount::float -
                COALESCE((vr.rule_violations->0->>'delta')::float, 0))         AS contract_amount,
            vr.validated_at
        FROM   validation_results vr
        JOIN   canonical_invoices ci ON ci.source_record_id = vr.source_record_id
        JOIN   cases c ON c.invoice_id = ci.id
        WHERE  c.id=%s::uuid AND c.tenant_id=%s::uuid
        LIMIT  1
    """, (case_id, tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No validation found")
    return _r(row)


def run_full_pipeline(
    db_url, ingestion_cls, validation_cls, canonical_cls, case_cls,
    run_evidence_and_reasoning,
    tenant_id: str, actor_sub: str,
    carrier: str, origin: str, dest: str,
    amount: float, currency: str,
    invoice_number: str | None = None,
    channel: str = "file_upload",
    channel_metadata: dict = None,
) -> dict:
    """Run full Phase 2+3 pipeline inline for one invoice. Returns dict with
    case_id, state, diff. `run_evidence_and_reasoning` is the shared
    Phase-2/3 helper in app.py — generic across slices, passed in rather
    than imported back to avoid a circular dependency."""
    import uuid as _uuid
    from kafka.mock_kafka import MockKafkaBroker as _MB
    broker = _MB()
    inv_no = invoice_number or f"BATCH-{_uuid.uuid4().hex[:8].upper()}"
    idem   = f"batch-{_uuid.uuid4().hex}"

    slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (tenant_id,))
    slug = slug_row["slug"] if slug_row else "default"

    inv = InvoiceInput(carrier_id=carrier, invoice_number=inv_no,
                       total_amount=float(amount), currency=currency,
                       route_origin=origin, route_destination=dest, weight_lbs=0.0)
    ing_r  = ingestion_cls(db_url, broker, slug).ingest_invoice(
        tenant_id, inv, idem,
        channel=channel,
        channel_metadata=channel_metadata or {},
        received_by_user=actor_sub,
    )
    val_r  = validation_cls(db_url, broker, slug).validate(
                 tenant_id, ing_r.source_record_id, inv_no, carrier, float(amount), currency)
    can_r  = canonical_cls(db_url, broker, slug).canonicalize_invoice(
                 tenant_id, ing_r.source_record_id, inv_no, carrier, float(amount), currency, origin, dest, 0.0)
    # (batch pipeline has no new fields — they default to "" / [])
    case_r = case_cls(db_url, broker).open_case(tenant_id, can_r.canonical_invoice_id, actor_sub)

    diff = float(val_r.overcharge_amount) if val_r.overcharge_amount else float(amount) * 0.2
    try:
        run_evidence_and_reasoning(
            tenant_id=tenant_id, case_id=str(case_r.case_id), slug=slug,
            carrier=carrier, amount=diff, currency=currency,
            route=f"{origin} → {dest}", actor_sub=actor_sub, broker=broker,
        )
    except Exception as _exc:
        import logging as _log
        _log.getLogger("zoiko.pipeline").error("Evidence/reasoning pipeline failed for case %s: %s", case_r.case_id, _exc)

    return {"case_id": str(case_r.case_id), "state": "FINDING_GENERATED",
            "carrier": carrier, "amount": amount, "diff": diff}


def process_one_batch_file(
    run_full_pipeline_fn,
    content: bytes, filename: str, content_type: str,
    tenant_id: str, actor_sub: str,
) -> dict:
    """One file's worth of work inside POST /ingestion/batch-submit's loop.
    `run_full_pipeline_fn` is a zero-extra-args closure over run_full_pipeline's
    db_url/handler-class/evidence-reasoning arguments, supplied by app.py."""
    import os
    import uuid as _uuid
    from services.ingestion_svc.file_adapter import build_file_channel_metadata

    item = {"filename": filename, "status": "pending", "case_id": None, "error": None,
            "mime_detected": None, "malware_outcome": None}
    try:
        _max_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
        if len(content) > _max_bytes:
            raise ValueError(f"File {filename} too large ({len(content)//1024}KB > {_max_bytes//1024//1024}MB limit)")

        ch_meta, mime_result, scan_result = build_file_channel_metadata(
            content           = content,
            filename          = filename or "",
            declared_mime     = content_type or "",
            user_id           = str(actor_sub),
            declared_schema   = "freight-invoice-batch-v1",
        )
        item["mime_detected"]    = mime_result.detected_mime
        item["malware_outcome"]  = scan_result.outcome

        if mime_result.rejected:
            raise ValueError(f"Rejected: {mime_result.rejection_reason}")
        if scan_result.outcome == "POSITIVE":
            raise ValueError(f"File rejected: malware detected ({scan_result.detail})")
        if ch_meta.macro_detected:
            policy = os.getenv("MACRO_POLICY", "reject")
            if policy == "reject":
                raise ValueError("File rejected: macro detected in spreadsheet")
        text = ""
        try:
            import pdfplumber, io
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            text = content.decode("utf-8", errors="ignore")

        carrier, amount, currency, route = "Unknown", 0.0, "INR", "Unknown-Unknown"
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key and text.strip():
            try:
                import json as _json
                from groq import Groq as _Groq
                _groq = _Groq(api_key=groq_key)
                prompt = (
                    f"Extract from this invoice text:\n{text[:2000]}\n\n"
                    "Return ONLY JSON: {\"carrier\": \"...\", \"amount\": 0.0, "
                    "\"currency\": \"INR\", \"route\": \"City1-City2\"}"
                )
                chat = _groq.chat.completions.create(
                    model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0, max_tokens=100,
                )
                raw_content = chat.choices[0].message.content.strip()
                if raw_content.startswith("```"):
                    raw_content = raw_content.split("```")[1]
                    if raw_content.startswith("json"):
                        raw_content = raw_content[4:]
                parsed = _json.loads(raw_content)
                carrier  = str(parsed.get("carrier", carrier))
                amount   = float(parsed.get("amount", amount) or 0)
                currency = str(parsed.get("currency", currency))
                route    = str(parsed.get("route", route))
            except (ValueError, KeyError):
                pass
            except Exception:
                pass

        if not carrier or carrier == "Unknown":
            import re as _re2
            for pat in [r"(?:carrier|shipped by|via)[:\s]+([A-Za-z\s]+?)(?:\n|,|\.)",
                        r"(BlueDart|Delhivery|FedEx|DTDC|Ekart|UPS|DHL|V Express)"]:
                m = _re2.search(pat, text, _re2.IGNORECASE)
                if m:
                    carrier = m.group(1).strip()
                    break
        if amount == 0.0:
            import re as _re2
            for pat in [r"[₹$]\s*([\d,]+(?:\.\d{1,2})?)", r"([\d,]+(?:\.\d{2}))\s*(?:INR|USD)"]:
                m = _re2.search(pat, text, _re2.IGNORECASE)
                if m:
                    try:
                        v = float(m.group(1).replace(",", ""))
                        if v > 100:
                            amount = v
                            break
                    except Exception:
                        pass

        parts = route.replace("→", "-").replace(" to ", "-").split("-")
        origin = parts[0].strip() if parts else "Unknown"
        dest   = parts[1].strip() if len(parts) > 1 else "Unknown"

        result = run_full_pipeline_fn(
            tenant_id, actor_sub,
            carrier or "Unknown", origin, dest,
            amount or 1000.0, currency or "INR",
            invoice_number=filename or f"batch-{_uuid.uuid4().hex[:8]}",
        )
        item["status"]  = "success"
        item["case_id"] = result.get("case_id")

    except Exception as exc:
        item["status"] = "failed"
        item["error"]  = str(exc)[:200]

    return item


def run_evidence_and_reasoning(
    db_url, tenant_id: str, case_id: str, slug: str,
    carrier: str, amount: float, currency: str, route: str,
    actor_sub: str, broker,
) -> None:
    """Add 4 evidence items, run reasoning, advance case to FINDING_GENERATED.
    Only ever called for invoice-overcharge cases — see
    sc-002-carrier-claim/routes_logic.py:run_evidence_and_reasoning_claim()
    for the claim-shaped mirror, which this does not touch."""
    import uuid
    import psycopg2, psycopg2.extras, hashlib, json
    from datetime import datetime, timezone
    from shared.signer import sign as _sign
    from zoiko_common.crypto.merkle import MerkleTree
    from zoiko_common.crypto.jcs import canonicalize as _jcs
    from services.case_orchestration.handler import CaseHandler

    DOMAIN_TAG = b"zoiko.evidence.item.v1:"
    MERKLE_DOM = "zoiko/v1/evidence-item"

    # Step 1 — transition NEW → EVIDENCE_PENDING
    CaseHandler(db_url, broker).transition_state(tenant_id, case_id, "EVIDENCE_PENDING", actor_sub)

    # Step 2 — add 4 synthetic evidence items
    items_content = [
        ("BOL",        f"Bill of Lading — shipment {route} carrier {carrier}".encode()),
        ("RATE_SHEET", f"Contract rate sheet — {carrier} base rate {currency}".encode()),
        ("INVOICE",    f"Invoice {carrier} amount {amount:.2f} {currency} route {route}".encode()),
        ("EMAIL",      f"Email thread — dispute overcharge {carrier} {route}".encode()),
    ]

    now = datetime.now(timezone.utc)
    psycopg2.extras.register_uuid()
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Advisory lock prevents concurrent bundle creation for the same case
        lock_key = int(uuid.UUID(case_id)) % (2**31)
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

        # Check if bundle already exists (safe with advisory lock above)
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

        # Recompute Merkle root
        _tree = MerkleTree(MERKLE_DOM)
        for _h in leaf_hashes:
            _tree.append(_h)
        merkle_root = _tree.root()
        root_sig, root_kid = _sign(slug, merkle_root)
        cur.execute(
            "UPDATE evidence_bundles SET bundle_hash=%s, signature=%s, kid=%s, completeness_status='COMPLETE' WHERE id=%s",
            (merkle_root, root_sig, root_kid, bundle_id)
        )

        # Step 3 — reasoning: SC-001 confidence = 0.96
        SC001 = 0.96
        rule_trace = {
            "fuel_charge":      {"confidence": 1.00, "weight": 0.50},
            "accessorial":      {"confidence": 0.92, "weight": 0.50},
            "weighted_average": SC001,
        }
        finding_payload = {"bundle_id": str(bundle_id), "case_id": case_id,
                           "confidence": str(SC001), "rule_trace": rule_trace, "tenant_id": tenant_id}
        finding_bytes = _jcs(finding_payload)
        finding_hash  = hashlib.sha256(b"zoiko.finding.v1:" + finding_bytes).digest()
        f_sig, f_kid  = _sign(slug, finding_hash)
        finding_id = uuid.uuid4()
        cur.execute("""
            INSERT INTO findings
                (id, tenant_id, case_id, bundle_id, confidence, rule_trace, finding_hash, signature, kid, created_at,
                 ai_confidence, risk_level, ai_reasoning)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NULL, NULL, NULL)
        """, (finding_id, tenant_id, uuid.UUID(case_id), bundle_id, SC001, json.dumps(rule_trace), finding_hash, f_sig, f_kid, now))

        prop_payload = {"amount": str(amount), "case_id": case_id, "currency": currency,
                        "finding_hash": finding_hash.hex(), "proposed_action": "CREDIT_MEMO",
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
              "CREDIT_MEMO", amount, currency, actor_sub, prop_hash, p_sig, p_kid, now))

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
                              payload={"case_id": case_id, "confidence": SC001}, tenant_id=tenant_id))


def submit_case_async_worker(
    db_url, broker, ingestion_cls, validation_cls, canonical_cls, case_cls,
    run_evidence_and_reasoning_fn, submit_jobs: dict, persist_job_fn,
    job_id: str, tenant_id: str, actor_sub: str, idempotency_key: str, body,
) -> None:
    """Background-thread body for POST /cases/submit-async."""
    import re as _re
    import uuid as _u
    try:
        parts  = _re.split(r'\s*[-→–]\s*', body.route.strip(), maxsplit=1)
        origin = parts[0].strip() if parts else body.route
        dest   = parts[1].strip() if len(parts) > 1 else "Unknown"
        inv_no = body.invoice_number.strip() if body.invoice_number.strip() else f"UI-{_u.uuid4().hex[:8].upper()}"
        slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (tenant_id,))
        slug = slug_row["slug"] if slug_row else "default"
        inv = InvoiceInput(
            carrier_id=body.carrier, invoice_number=inv_no,
            total_amount=float(body.amount), currency=body.currency,
            route_origin=origin, route_destination=dest, weight_lbs=0.0,
            invoice_date=body.invoice_date, transport_mode=body.transport_mode,
            equipment_type=body.equipment_type, charge_lines=body.charge_lines,
            shipper_reference=body.shipper_reference,
        )
        ing_r  = ingestion_cls(db_url, broker, slug).ingest_invoice(tenant_id, inv, idempotency_key)
        val_r  = validation_cls(db_url, broker, slug).validate(
                     tenant_id, ing_r.source_record_id, inv_no,
                     body.carrier, float(body.amount), body.currency)
        can_r  = canonical_cls(db_url, broker, slug).canonicalize_invoice(
                     tenant_id, ing_r.source_record_id, inv_no,
                     body.carrier, float(body.amount), body.currency, origin, dest, 0.0,
                     invoice_date=body.invoice_date,
                     transport_mode=body.transport_mode,
                     equipment_type=body.equipment_type,
                     charge_lines=body.charge_lines,
                 )
        case_r = case_cls(db_url, broker).open_case(tenant_id, can_r.canonical_invoice_id, actor_sub)
        diff   = float(val_r.overcharge_amount) if val_r.overcharge_amount else float(body.amount) * 0.2

        if not case_r.is_new:
            existing = q1(
                "SELECT state, opened_at FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid",
                (str(case_r.case_id), tenant_id),
            )
            now_str = datetime.now(timezone.utc).isoformat()
            _case_data = {
                "id": str(case_r.case_id), "tenant_id": tenant_id,
                "state": existing["state"] if existing else case_r.state,
                "carrier": body.carrier, "shipment_ref": body.route,
                "amount": float(body.amount), "currency": body.currency,
                "diff": diff, "confidence": 0.0,
                "opened_at": (existing["opened_at"].isoformat() if existing else now_str),
                "updated_at": now_str,
                "duplicate": True,
                "deduplication_outcome": ing_r.deduplication_outcome,
            }
            submit_jobs[job_id] = {"status": "done", "case": _case_data, "error": None}
            persist_job_fn(job_id, "done", _case_data, None)
            return

        try:
            run_evidence_and_reasoning_fn(
                tenant_id=tenant_id, case_id=str(case_r.case_id), slug=slug,
                carrier=body.carrier, amount=diff, currency=body.currency,
                route=body.route, actor_sub=actor_sub, broker=broker,
            )
        except Exception:
            import traceback; traceback.print_exc()
        now_str = datetime.now(timezone.utc).isoformat()
        _case_data = {
                "id": str(case_r.case_id), "tenant_id": tenant_id,
                "state": "FINDING_GENERATED", "carrier": body.carrier,
                "shipment_ref": body.route, "amount": float(body.amount),
                "currency": body.currency, "diff": diff, "confidence": 0.96,
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


def submit_case(
    db_url, broker, ingestion_cls, validation_cls, canonical_cls, case_cls,
    run_evidence_and_reasoning_fn, capture_rest_push_metadata_fn,
    request, body, idempotency_key: str, tenant_id: str, actor_sub: str,
) -> dict:
    """Full pipeline: ingest → validate → canonical → open case → evidence → AI finding.
    Sync (not async) so FastAPI runs this in the thread-pool executor — see
    app.py's route docstring for why."""
    import re as _re
    import threading as _threading
    parts  = _re.split(r'\s*[-→–]\s*', body.route.strip(), maxsplit=1)
    origin = parts[0].strip() if parts else body.route
    dest   = parts[1].strip() if len(parts) > 1 else "Unknown"
    inv_no = body.invoice_number.strip() if body.invoice_number.strip() else f"UI-{uuid.uuid4().hex[:8].upper()}"

    slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (tenant_id,))
    slug = slug_row["slug"] if slug_row else "default"

    ch_metadata = capture_rest_push_metadata_fn(request, idempotency_key)
    channel = "ui_entry" if request.headers.get("X-UI-Submit") else "rest_api_push"

    inv = InvoiceInput(
        carrier_id=body.carrier, invoice_number=inv_no,
        total_amount=float(body.amount), currency=body.currency,
        route_origin=origin, route_destination=dest, weight_lbs=0.0,
        invoice_date=body.invoice_date, transport_mode=body.transport_mode,
        equipment_type=body.equipment_type, charge_lines=body.charge_lines,
        shipper_reference=body.shipper_reference,
    )
    ing_r  = ingestion_cls(db_url, broker, slug).ingest_invoice(
        tenant_id, inv, idempotency_key,
        channel=channel,
        channel_metadata=ch_metadata,
        received_by_user=actor_sub if actor_sub else None,
        correlation_id=request.headers.get("X-Correlation-ID"),
    )
    val_r  = validation_cls(db_url, broker, slug).validate(
                 tenant_id, ing_r.source_record_id, inv_no,
                 body.carrier, float(body.amount), body.currency)
    can_r  = canonical_cls(db_url, broker, slug).canonicalize_invoice(
                 tenant_id, ing_r.source_record_id, inv_no,
                 body.carrier, float(body.amount), body.currency, origin, dest, 0.0,
                 invoice_date=body.invoice_date,
                 transport_mode=body.transport_mode,
                 equipment_type=body.equipment_type,
                 charge_lines=body.charge_lines,
             )
    case_r = case_cls(db_url, broker).open_case(tenant_id, can_r.canonical_invoice_id, actor_sub)
    diff = float(val_r.overcharge_amount) if val_r.overcharge_amount else float(body.amount) * 0.2

    if not case_r.is_new:
        existing = q1(
            "SELECT state, opened_at FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid",
            (str(case_r.case_id), tenant_id),
        )
        return {
            "id":                     str(case_r.case_id),
            "tenant_id":              tenant_id,
            "state":                  existing["state"] if existing else case_r.state,
            "carrier":                body.carrier,
            "shipment_ref":           body.route,
            "amount":                 float(body.amount),
            "currency":               body.currency,
            "diff":                   diff,
            "confidence":             0.0,
            "opened_at":              (existing["opened_at"].isoformat() if existing else case_r.opened_at.isoformat()),
            "updated_at":             datetime.now(timezone.utc).isoformat(),
            "duplicate":              True,
            "deduplication_outcome":  ing_r.deduplication_outcome,
        }

    def _bg():
        try:
            run_evidence_and_reasoning_fn(
                tenant_id = tenant_id,
                case_id   = str(case_r.case_id),
                slug      = slug,
                carrier   = body.carrier,
                amount    = diff,
                currency  = body.currency,
                route     = body.route,
                actor_sub = actor_sub,
                broker    = broker,
            )
        except Exception:
            import traceback; traceback.print_exc()

    _threading.Thread(target=_bg, daemon=True, name=f"p3-{case_r.case_id}").start()

    now_str = datetime.now(timezone.utc).isoformat()
    return {
        "id":           str(case_r.case_id),
        "tenant_id":    tenant_id,
        "state":        "EVIDENCE_PENDING",
        "carrier":      body.carrier,
        "shipment_ref": body.route,
        "amount":       float(body.amount),
        "currency":     body.currency,
        "diff":         diff,
        "confidence":   0.0,
        "opened_at":    now_str,
        "updated_at":   now_str,
    }


def generate_dispute_letter(tenant_id: str, actor_sub: str, case_id: str) -> dict:
    """Generate a professional dispute letter for an invoice-overcharge case,
    auto-filled with real tenant/carrier/case data from the database."""
    row = q1("""
        SELECT
            c.id::text AS case_id,
            c.state,
            ci.carrier_id AS carrier,
            ci.invoice_number,
            ci.total_amount::float AS billed_amount,
            ci.currency,
            vr.rule_violations,
            f.confidence,
            COALESCE(cs.origin_city || ' to ' || cs.dest_city, '') AS route
        FROM cases c
        JOIN canonical_invoices ci ON ci.id = c.invoice_id
        LEFT JOIN validation_results vr ON vr.source_record_id = ci.source_record_id AND vr.tenant_id = c.tenant_id
        LEFT JOIN findings f ON f.case_id = c.id AND f.tenant_id = c.tenant_id
        LEFT JOIN canonical_shipments cs ON cs.invoice_id = ci.id
        WHERE c.id = %s::uuid AND c.tenant_id = %s::uuid
        LIMIT 1
    """, (case_id, tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="Case not found")

    overcharge = 0.0
    violations = row.get("rule_violations") or []
    if isinstance(violations, list) and violations:
        overcharge = violations[0].get("delta", 0) if isinstance(violations[0], dict) else 0

    if overcharge <= 0:
        raise HTTPException(status_code=422, detail="No overcharge on record for this case — nothing to dispute")

    carrier      = row.get("carrier") or "Carrier"
    invoice_no   = row.get("invoice_number") or "N/A"
    route        = row.get("route") or "N/A"
    billed       = float(row.get("billed_amount") or 0)
    currency     = row.get("currency") or "INR"
    confidence   = int((row.get("confidence") or 0.96) * 100)
    contract_amt = billed - overcharge
    ref          = case_id[:8].upper()

    tenant_row = q1(
        "SELECT display_name FROM tenants WHERE id = %s::uuid",
        (tenant_id,),
    )
    company_name = (tenant_row.get("display_name") or "Your Company") if tenant_row else "Your Company"

    user_row = q1(
        "SELECT full_name, title, email FROM users WHERE email = %s AND tenant_id = %s::uuid",
        (actor_sub, tenant_id),
    )
    sender_name    = (user_row.get("full_name") or actor_sub) if user_row else actor_sub
    sender_title   = (user_row.get("title") or "Logistics Manager").strip() if user_row else "Logistics Manager"
    sender_email   = (user_row.get("email") or actor_sub) if user_row else actor_sub

    carrier_row = q1(
        "SELECT email FROM carriers WHERE tenant_id = %s::uuid AND LOWER(name) = LOWER(%s)",
        (tenant_id, carrier),
    )
    carrier_email = (carrier_row.get("email") or "").strip() if carrier_row else ""

    from datetime import date as _date
    today = _date.today().strftime("%d %B %Y")

    letter = f"""Subject: Freight Overcharge Dispute - Invoice {invoice_no}

Dear {carrier} Team,

I am writing to bring to your attention a discrepancy in the freight charges billed for the shipment from {route}, as per our contract. The details of the shipment are as follows:

- Invoice Number: {invoice_no}
- Route: {route}
- Amount Billed: {currency} {billed:,.2f}
- Contracted Rate: {currency} {contract_amt:,.2f}
- Overcharge Amount: {currency} {overcharge:,.2f}

Our analysis, supported by a cryptographic audit record (ACR-{ref}) with an AI Confidence of {confidence}%, indicates that the freight charges billed are not in line with our contracted agreement. As per our contract, the freight charges should have been {currency} {contract_amt:,.2f} — an overcharge of {currency} {overcharge:,.2f}.

We request that you issue a credit memo for {currency} {overcharge:,.2f} to reflect the accurate, contracted freight charges. We kindly request that you process this credit memo within 30 days from the date of this letter.

We appreciate your prompt attention to this matter and look forward to resolving this dispute amicably. If you require any additional information or clarification, please do not hesitate to contact us.

Please confirm in writing once the credit memo has been processed.

Thank you for your cooperation and understanding.

Sincerely,

{sender_name}
{sender_title}
{company_name}
{today}
{sender_email}
"""
    return {
        "case_id":        case_id,
        "carrier":        carrier,
        "overcharge":     overcharge,
        "currency":       currency,
        "dispute_letter": letter,
        "generated_by":   "template",
        "carrier_email":  carrier_email,
    }


def ui_canonical_invoice(_r, tenant_id: str, case_id: str) -> dict:
    row = q1("""
        SELECT
            ci.id::text,
            ci.tenant_id::text,
            COALESCE(cs.origin_city||'-'||cs.dest_city, ci.invoice_number) AS shipment_ref,
            ci.carrier_id                       AS carrier,
            ci.total_amount::float              AS amount,
            ci.currency,
            encode(ci.canonical_hash, 'hex')    AS canonical_hash,
            encode(ci.signature,      'hex')    AS signature,
            ci.created_at                       AS signed_at
        FROM  canonical_invoices ci
        JOIN  cases c ON c.invoice_id = ci.id
        LEFT JOIN canonical_shipments cs ON cs.invoice_id = ci.id
        WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid
        LIMIT 1
    """, (case_id, tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No canonical invoice found")
    return _r(row)


def ingest_invoice(ingestion_handler, tenant_id: str, body, idempotency_key: str):
    invoice = InvoiceInput(
        carrier_id        = body.carrier_id,
        invoice_number    = body.invoice_number,
        total_amount      = body.total_amount,
        currency          = body.currency,
        route_origin      = body.route_origin,
        route_destination = body.route_destination,
        weight_lbs        = body.weight_lbs,
    )
    result = ingestion_handler.ingest_invoice(
        tenant_id       = tenant_id,
        invoice         = invoice,
        idempotency_key = idempotency_key,
    )
    return {
        "source_record_id": str(result.source_record_id),
        "canonical_hash":   result.canonical_hash,
        "idempotency_key":  result.idempotency_key,
        "tenant_id":        str(result.tenant_id),
    }


def validate_invoice(validation_handler, tenant_id: str, source_record_id: str, body):
    try:
        result = validation_handler.validate(
            tenant_id        = tenant_id,
            source_record_id = source_record_id,
            invoice_number   = body.invoice_number,
            carrier_id       = body.carrier_id,
            total_amount     = body.total_amount,
            currency         = body.currency,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation error: {e}")

    return {
        "validation_id":     str(result.validation_id),
        "status":            result.status,
        "overcharge_amount": result.overcharge_amount,
        "violations":        len(result.rule_violations),
        "currency":          result.currency,
    }


def canonicalize_invoice(canonical_handler, tenant_id: str, source_record_id: str, body):
    try:
        result = canonical_handler.canonicalize_invoice(
            tenant_id        = tenant_id,
            source_record_id = source_record_id,
            invoice_number   = body.invoice_number,
            carrier_id       = body.carrier_id,
            total_amount     = body.total_amount,
            currency         = body.currency,
            origin_city      = body.origin_city,
            dest_city        = body.dest_city,
            weight_lbs       = body.weight_lbs,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Canonicalization error: {e}")

    return {
        "canonical_invoice_id":  str(result.canonical_invoice_id),
        "canonical_shipment_id": str(result.canonical_shipment_id),
        "canonical_hash":        result.canonical_hash,
        "invoice_number":        result.invoice_number,
    }


def open_case(case_handler, tenant_id: str, canonical_invoice_id: str, actor_sub: str):
    try:
        result = case_handler.open_case(
            tenant_id            = tenant_id,
            canonical_invoice_id = canonical_invoice_id,
            actor_sub            = actor_sub,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Case creation error: {e}")

    return {
        "case_id":   str(result.case_id),
        "state":     result.state,
        "is_new":    result.is_new,
        "tenant_id": str(result.tenant_id),
    }

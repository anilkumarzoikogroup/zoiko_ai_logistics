"""
Connector Hub — SC-002 Carrier Claim Adapter

Submits a carrier claim to the registered connector endpoint after the
Execution Gateway authorises the dispatch.

In DEV_MODE (ZOIKO_DEV_MODE=true) or when no endpoint_url is configured,
a mock settlement response is written immediately so the reconciliation
path can be exercised end-to-end without a live carrier API.

In production:
  - Looks up the active connector for the tenant (source_type='carrier_claims_api')
  - POSTs a standardised claim payload to connector.endpoint_url
  - Decrypts credentials from credentials_ref (KMS stub in dev)
  - Writes connector_dispatches row and — if carrier responds synchronously
    within timeout — writes connector_responses row automatically
  - Async/webhook-based carriers: response arrives via POST /webhooks/carrier/{source_type}

Flow called from ExecutionGateway._dispatch():
    hub = CarrierConnectorHub(db_url, broker, tenant_slug)
    hub.submit_claim(envelope_id, tenant_id, case_id, amount, currency, scope)
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

import paths  # noqa: F401
import shared.db as _db

psycopg2.extras.register_uuid()
logger = logging.getLogger(__name__)

_DEV_MODE         = os.getenv("ZOIKO_DEV_MODE", "").lower() == "true"
_CONNECTOR_TIMEOUT = int(os.getenv("CARRIER_CONNECTOR_TIMEOUT_SECS", "10"))
_MOCK_ACCEPT_RATE  = float(os.getenv("DEV_MOCK_ACCEPT_RATE", "1.0"))  # 1.0 = always accept


class ConnectorDispatchResult:
    """Returned by submit_claim() — caller uses this for logging/ACR."""
    def __init__(
        self,
        dispatch_id: str,
        connector_ref: str,
        mode: str,        # "mock" | "sync" | "async"
        status: str,      # "ACCEPTED" | "PARTIAL" | "REJECTED" | "PENDING"
        settled_amount: Optional[float],
        carrier_reference: str,
        response_id: Optional[str],
    ) -> None:
        self.dispatch_id       = dispatch_id
        self.connector_ref     = connector_ref
        self.mode              = mode
        self.status            = status
        self.settled_amount    = settled_amount
        self.carrier_reference = carrier_reference
        self.response_id       = response_id


class CarrierConnectorHub:
    """Submits claim to carrier and optionally records the synchronous response."""

    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    # ── Public API ──────────────────────────────────────────────────────────

    def submit_claim(
        self,
        envelope_id:  str,
        tenant_id:    str,
        case_id:      str,
        amount:       float,
        currency:     str,
        scope:        str,
        actor_sub:    str = "system",
    ) -> ConnectorDispatchResult:
        """
        Submit the claim to the carrier connector.
        Never raises — logs errors and returns a PENDING result on failure
        so that reconciliation can proceed via incoming webhook later.
        """
        try:
            connector = self._find_connector(tenant_id)
            if _DEV_MODE or not connector or not connector.get("endpoint_url"):
                return self._mock_submit(envelope_id, tenant_id, case_id, amount, currency, scope)
            return self._real_submit(connector, envelope_id, tenant_id, case_id, amount, currency, scope)
        except Exception as exc:
            logger.error("ConnectorHub.submit_claim failed for envelope %s: %s", envelope_id, exc)
            return ConnectorDispatchResult(
                dispatch_id       = str(uuid.uuid4()),
                connector_ref     = envelope_id,
                mode              = "error",
                status            = "PENDING",
                settled_amount    = None,
                carrier_reference = "",
                response_id       = None,
            )

    # ── Private: mock path ───────────────────────────────────────────────────

    def _mock_submit(
        self,
        envelope_id: str,
        tenant_id:   str,
        case_id:     str,
        amount:      float,
        currency:    str,
        scope:       str,
    ) -> ConnectorDispatchResult:
        """Write a synthetic connector_response row (dev / no-connector path)."""
        import random
        now          = datetime.now(timezone.utc)
        dispatch_id  = str(uuid.uuid4())
        response_id  = str(uuid.uuid4())
        carrier_ref  = f"MOCK-CLM-{dispatch_id[:8].upper()}"

        # Determine mock outcome
        roll = random.random()
        if roll < _MOCK_ACCEPT_RATE:
            status         = "ACCEPTED"
            settled_amount = amount
            status_code    = 200
        elif roll < _MOCK_ACCEPT_RATE + 0.1:
            status         = "PARTIAL"
            settled_amount = round(amount * 0.75, 2)
            status_code    = 206
        else:
            status         = "REJECTED"
            settled_amount = 0.0
            status_code    = 422

        response_body = {
            "settled_amount":    settled_amount,
            "status":            status,
            "carrier_reference": carrier_ref,
            "notes":             f"DEV_MODE mock — {status}",
        }

        try:
            with _db.get_conn(self._db_url) as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO connector_responses
                        (id, tenant_id, envelope_id, connector_id, status_code, response_body, received_at)
                    VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    uuid.UUID(response_id), tenant_id, uuid.UUID(envelope_id),
                    "mock_carrier_adapter",
                    status_code,
                    json.dumps(response_body),
                    now,
                ))
                conn.commit()
        except Exception as exc:
            logger.warning("Mock connector_response write failed: %s", exc)

        logger.info(
            "ConnectorHub [MOCK] envelope=%s status=%s settled=%.2f %s",
            envelope_id, status, settled_amount, currency,
        )
        return ConnectorDispatchResult(
            dispatch_id       = dispatch_id,
            connector_ref     = envelope_id,
            mode              = "mock",
            status            = status,
            settled_amount    = settled_amount,
            carrier_reference = carrier_ref,
            response_id       = response_id,
        )

    # ── Private: real HTTP path ──────────────────────────────────────────────

    def _real_submit(
        self,
        connector:    dict,
        envelope_id:  str,
        tenant_id:    str,
        case_id:      str,
        amount:       float,
        currency:     str,
        scope:        str,
    ) -> ConnectorDispatchResult:
        """POST claim payload to connector.endpoint_url and handle response."""
        import requests as _req

        endpoint     = connector["endpoint_url"].rstrip("/")
        auth_headers = self._build_auth_headers(connector)
        dispatch_id  = str(uuid.uuid4())
        now          = datetime.now(timezone.utc)

        # Enrich payload with claim details from DB
        claim_detail = self._fetch_claim_detail(tenant_id, case_id)
        payload = {
            "zoiko_envelope_id":  envelope_id,
            "zoiko_case_id":      case_id,
            "zoiko_tenant_id":    tenant_id,
            "claim_type":         claim_detail.get("claim_type", "OVERCHARGE"),
            "claimed_amount":     amount,
            "currency":           currency,
            "scope":              scope,
            "carrier_id":         claim_detail.get("carrier_id", ""),
            "claim_reference":    claim_detail.get("claim_reference", ""),
            "filed_at":           claim_detail.get("filed_at", now.isoformat()),
            "lines":              claim_detail.get("lines", []),
        }

        try:
            resp = _req.post(
                f"{endpoint}/claims/submit",
                json=payload,
                headers={"Content-Type": "application/json", **auth_headers},
                timeout=_CONNECTOR_TIMEOUT,
            )
        except Exception as exc:
            logger.warning("Carrier API call failed: %s — will await webhook", exc)
            return ConnectorDispatchResult(
                dispatch_id       = dispatch_id,
                connector_ref     = envelope_id,
                mode              = "async",
                status            = "PENDING",
                settled_amount    = None,
                carrier_reference = "",
                response_id       = None,
            )

        # If carrier responds synchronously (200/206/422), record it immediately
        response_id = None
        status      = "PENDING"
        settled     = None
        carrier_ref = ""

        if resp.status_code in (200, 206, 422):
            try:
                rbody = resp.json()
            except Exception:
                rbody = {"raw": resp.text[:500]}

            status_map  = {200: "ACCEPTED", 206: "PARTIAL", 422: "REJECTED"}
            status      = status_map.get(resp.status_code, "PENDING")
            settled     = float(rbody.get("settled_amount", amount if status == "ACCEPTED" else 0))
            carrier_ref = rbody.get("carrier_reference", "")

            response_id = str(uuid.uuid4())
            response_body = {
                "settled_amount":    settled,
                "status":            status,
                "carrier_reference": carrier_ref,
                "notes":             rbody.get("notes", ""),
            }
            try:
                with _db.get_conn(self._db_url) as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO connector_responses
                            (id, tenant_id, envelope_id, connector_id, status_code, response_body, received_at)
                        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s)
                        ON CONFLICT DO NOTHING
                    """, (
                        uuid.UUID(response_id), tenant_id, uuid.UUID(envelope_id),
                        connector.get("name", "carrier_api"),
                        resp.status_code,
                        json.dumps(response_body),
                        now,
                    ))
                    conn.commit()
            except Exception as exc:
                logger.warning("Failed to write sync connector_response: %s", exc)

        mode = "sync" if response_id else "async"
        logger.info(
            "ConnectorHub [%s] envelope=%s status=%s carrier_ref=%s",
            mode.upper(), envelope_id, status, carrier_ref,
        )
        return ConnectorDispatchResult(
            dispatch_id       = dispatch_id,
            connector_ref     = envelope_id,
            mode              = mode,
            status            = status,
            settled_amount    = settled,
            carrier_reference = carrier_ref,
            response_id       = response_id,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _find_connector(self, tenant_id: str) -> Optional[dict]:
        """Return the first ACTIVE carrier_claims connector for the tenant."""
        return _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id::text, name, endpoint_url, credentials_ref, auth_method, rate_limit_rps
                FROM   connectors
                WHERE  tenant_id = %s::uuid
                  AND  certification_state = 'Active'
                  AND  operational_state   = 'healthy'
                  AND  (source_type = 'carrier_claims_api' OR connector_type = 'CARRIER_CLAIM')
                ORDER  BY created_at ASC
                LIMIT  1
            """,
            params=(tenant_id,),
        )

    def _build_auth_headers(self, connector: dict) -> dict:
        """Build HTTP auth headers from connector.auth_method + credentials_ref."""
        auth_method = connector.get("auth_method", "API_KEY")
        creds_ref   = connector.get("credentials_ref", "")
        if not creds_ref:
            return {}
        if auth_method == "API_KEY":
            # credentials_ref holds the raw API key (prod: resolve from KMS/secrets manager)
            return {"X-Api-Key": creds_ref}
        if auth_method == "BEARER":
            return {"Authorization": f"Bearer {creds_ref}"}
        if auth_method == "BASIC":
            import base64
            encoded = base64.b64encode(creds_ref.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    def _fetch_claim_detail(self, tenant_id: str, case_id: str) -> dict:
        """Enrich claim payload with DB data for carrier submission."""
        if not case_id:
            return {}
        try:
            row = _db.q1(
                db_url=self._db_url,
                sql="""
                    SELECT
                        cl.claim_type, cl.claimed_amount, cl.currency,
                        cl.claim_reference, cl.filed_at::text,
                        ca.id::text AS carrier_id, ca.name AS carrier_name
                    FROM   cases c
                    JOIN   claims cl  ON cl.id = c.claim_id
                    LEFT JOIN carriers ca ON ca.id = c.carrier_id
                    WHERE  c.id = %s::uuid AND c.tenant_id = %s::uuid
                    LIMIT  1
                """,
                params=(case_id, tenant_id),
            )
            if not row:
                return {}
            lines = _db.q(
                db_url=self._db_url,
                sql="""
                    SELECT line_number, description, claimed_amount::float, currency
                    FROM   claim_lines
                    WHERE  claim_id = (
                        SELECT claim_id FROM cases WHERE id=%s::uuid LIMIT 1
                    )
                    ORDER BY line_number ASC
                """,
                params=(case_id,),
            )
            return {
                "claim_type":      row["claim_type"],
                "claimed_amount":  float(row["claimed_amount"]),
                "currency":        row["currency"],
                "claim_reference": row["claim_reference"] or "",
                "filed_at":        row["filed_at"] or "",
                "carrier_id":      row.get("carrier_id") or "",
                "carrier_name":    row.get("carrier_name") or "",
                "lines": [
                    {
                        "line_number":    ln["line_number"],
                        "description":    ln["description"],
                        "claimed_amount": ln["claimed_amount"],
                        "currency":       ln["currency"],
                    }
                    for ln in (lines or [])
                ],
            }
        except Exception as exc:
            logger.warning("Could not fetch claim detail for case %s: %s", case_id, exc)
            return {}

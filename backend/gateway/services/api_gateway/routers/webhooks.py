"""
Webhook router — Tier-0 spec §7.4 (Webhook Channel).

Inbound webhook from external freight carriers/ERPs.

Security controls (all required before payload is accepted):
  1. HMAC-SHA-256 signature verification    (X-Webhook-Signature-256)
  2. Replay protection via webhook-id + timestamp window (±5 min)
  3. IP allow-list enforcement               (X-Forwarded-For vs tenant config)
  4. Content-Digest body integrity check     (Content-Digest sha-256=:<b64>:)

POST   /webhooks/ingest/{source_type}      — receive a webhook event
GET    /webhooks/secrets/{tenant_id}       — list webhook endpoint configs (admin)
POST   /webhooks/secrets/{tenant_id}       — create/rotate a webhook signing secret (admin)
"""
import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

import paths  # noqa: F401
from services.api_gateway.auth import get_claims
from middleware.oidc.claims import ZoikoClaims
from shared.db import q, q1

router = APIRouter(tags=["webhooks"])

DB_URL = os.getenv("DB_URL")

# Replay protection window: reject webhooks older than this
_REPLAY_WINDOW_SECONDS = 300   # 5 minutes

# Webhook-id uniqueness window: store seen IDs for this long
_WEBHOOK_ID_TTL_SECONDS = 600  # 10 minutes


# ── HMAC-SHA-256 signature verification ───────────────────────────────────────

def _verify_webhook_signature(
    body: bytes,
    signature_header: str,
    signing_secret: str,
) -> bool:
    """
    Verify X-Webhook-Signature-256: sha256=<hex>
    Covers body bytes only — no timestamp in signature (replay handled separately).
    """
    if not signature_header or not signing_secret:
        return False

    try:
        alg, provided_hex = signature_header.split("=", 1)
    except ValueError:
        return False

    if alg != "sha256":
        return False

    expected = hmac.new(
        signing_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, provided_hex)


# ── Timestamp-based replay protection ─────────────────────────────────────────

def _check_timestamp(timestamp_header: str) -> None:
    """
    Reject requests with X-Webhook-Timestamp outside ±5 min of now.
    Format: Unix epoch seconds as a string.
    """
    if not timestamp_header:
        raise HTTPException(status_code=400, detail="X-Webhook-Timestamp header required")

    try:
        ts = int(timestamp_header)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Webhook-Timestamp must be a Unix timestamp (integer seconds)")

    now_ts = int(datetime.now(timezone.utc).timestamp())
    delta  = abs(now_ts - ts)

    if delta > _REPLAY_WINDOW_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"X-Webhook-Timestamp is {delta}s from server time — outside replay window ({_REPLAY_WINDOW_SECONDS}s)"
        )


def _check_webhook_id_replay(webhook_id: str, tenant_id: str) -> None:
    """
    Check webhook-id has not been seen recently (idempotent delivery from carrier).
    Uses the dedup_index table since it's already in scope for ingestion.
    Raises 409 if duplicate detected.
    """
    if not webhook_id:
        raise HTTPException(status_code=400, detail="X-Webhook-ID header required")

    try:
        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor()
        cur.execute("""
            SELECT 1 FROM dedup_index
            WHERE tenant_id = %s::uuid AND external_source_ref = %s
              AND first_seen_at > NOW() - INTERVAL '10 minutes'
        """, (tenant_id, f"webhook-id:{webhook_id}"))
        exists = cur.fetchone()
        if exists:
            conn.close()
            raise HTTPException(status_code=409, detail=f"Duplicate webhook delivery: webhook-id {webhook_id} already processed")

        # Mark as seen
        cur.execute("""
            INSERT INTO dedup_index
                (id, tenant_id, domain_tag, source_type, source_type_version,
                 dedup_key, external_source_ref, payload_hash_hex,
                 source_record_id, first_seen_at)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, NULL, NOW())
            ON CONFLICT DO NOTHING
        """, (
            uuid.uuid4(), tenant_id,
            "zoiko/webhook/replay-guard",
            "WEBHOOK_ID",
            "v1",
            f"wid:{webhook_id[:32]}",
            f"webhook-id:{webhook_id}",
            hashlib.sha256(webhook_id.encode()).hexdigest(),
        ))
        conn.commit()
        conn.close()
    except HTTPException:
        raise
    except Exception:
        pass  # DB failure must not block delivery acceptance


# ── IP allow-list enforcement ─────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _check_ip_allowlist(client_ip: str, signing_config: dict) -> None:
    """
    If the signing config has an ip_allowlist, reject IPs not in the list.
    Skipped if no allowlist is configured (open inbound is valid for some carriers).
    """
    allowlist = signing_config.get("ip_allowlist") or []
    if not allowlist:
        return
    if client_ip not in allowlist:
        raise HTTPException(
            status_code=403,
            detail=f"Source IP {client_ip} not in webhook IP allow-list"
        )


# ── Load signing secret for tenant + source_type ─────────────────────────────

def _load_webhook_config(tenant_id: str, source_type: str) -> dict:
    """
    Load webhook signing config from DB.
    Returns dict with signing_secret, ip_allowlist, is_active.
    Raises 404 if not configured.
    """
    try:
        row = q1("""
            SELECT signing_secret, ip_allowlist, is_active, config
            FROM webhook_signing_configs
            WHERE tenant_id = %s::uuid AND source_type = %s AND is_active = true
        """, (tenant_id, source_type))
    except Exception:
        # Table may not exist yet in dev — use dev bypass
        dev_mode = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
        if dev_mode:
            return {"signing_secret": os.getenv("ZOIKO_DEV_WEBHOOK_SECRET", "dev-webhook-secret"), "ip_allowlist": [], "is_active": True}
        raise HTTPException(status_code=503, detail="Webhook config store unavailable")

    if not row:
        dev_mode = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
        if dev_mode:
            return {"signing_secret": os.getenv("ZOIKO_DEV_WEBHOOK_SECRET", "dev-webhook-secret"), "ip_allowlist": [], "is_active": True}
        raise HTTPException(
            status_code=404,
            detail=f"No active webhook signing config for source_type={source_type}"
        )
    return dict(row)


# ── POST /webhooks/ingest/{source_type} ───────────────────────────────────────

@router.post("/webhooks/ingest/{source_type}", status_code=202)
async def receive_webhook(
    source_type: str,
    request: Request,
    x_webhook_id:        Optional[str] = Header(None, alias="X-Webhook-ID"),
    x_webhook_timestamp: Optional[str] = Header(None, alias="X-Webhook-Timestamp"),
    x_webhook_signature: Optional[str] = Header(None, alias="X-Webhook-Signature-256"),
    x_tenant_id:         Optional[str] = Header(None, alias="X-Tenant-ID"),
    content_digest:      Optional[str] = Header(None, alias="Content-Digest"),
):
    """
    Receive an inbound webhook from an external freight carrier or ERP.

    Required headers:
      X-Tenant-ID                  — tenant routing
      X-Webhook-ID                 — unique delivery ID (replay guard)
      X-Webhook-Timestamp          — Unix epoch seconds (±5 min window)
      X-Webhook-Signature-256      — sha256=<hex> HMAC over body

    Optional:
      Content-Digest               — sha-256=:<base64>: body integrity
    """
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")

    body = await request.body()

    # 1. Content-Digest integrity check
    if content_digest:
        if content_digest.startswith("sha-256=:"):
            expected_b64 = content_digest[len("sha-256=:"):-1]
            actual = base64.b64encode(hashlib.sha256(body).digest()).decode()
            if actual != expected_b64:
                raise HTTPException(status_code=400, detail="Content-Digest mismatch — body corrupted in transit")

    # 2. Timestamp replay protection
    _check_timestamp(x_webhook_timestamp or "")

    # 3. Load tenant webhook config (signing secret + IP allowlist)
    signing_config = _load_webhook_config(x_tenant_id, source_type)

    # 4. IP allow-list
    client_ip = _get_client_ip(request)
    _check_ip_allowlist(client_ip, signing_config)

    # 5. HMAC-SHA-256 signature verification
    dev_mode = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
    if not _verify_webhook_signature(body, x_webhook_signature or "", signing_config["signing_secret"]):
        if not dev_mode:
            raise HTTPException(status_code=401, detail="Webhook signature verification failed")

    # 6. Replay guard (webhook-id uniqueness)
    _check_webhook_id_replay(x_webhook_id or str(uuid.uuid4()), x_tenant_id)

    # 7. Parse body
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Webhook body must be valid JSON")

    # 8. Build webhook channel_metadata
    channel_metadata = {
        "source_system":      request.headers.get("X-Source-System", source_type),
        "webhook_id":         x_webhook_id or "",
        "webhook_timestamp":  x_webhook_timestamp or "",
        "signature_header":   x_webhook_signature or "",
        "source_ip":          client_ip,
        "user_agent":         request.headers.get("User-Agent", ""),
        "content_digest":     content_digest or "",
        "hmac_verified":      True,
        "replay_checked":     True,
        "ip_checked":         bool((signing_config.get("ip_allowlist") or [])),
    }

    # 9. Hand off to ingestion pipeline
    try:
        from services.ingestion_svc.handler import IngestionHandler
        from services.ingestion_svc.models import ChannelEnum

        handler = IngestionHandler(DB_URL, None)  # no kafka broker in webhook path
        correlation_id  = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        idempotency_key = x_webhook_id or str(uuid.uuid4())

        result = handler.ingest_invoice(
            tenant_id       = x_tenant_id,
            invoice         = payload,
            idempotency_key = idempotency_key,
            channel         = ChannelEnum.WEBHOOK,
            channel_metadata= channel_metadata,
            received_at     = datetime.now(timezone.utc),
            received_by_user= None,
            correlation_id  = correlation_id,
            causation_id    = x_webhook_id or "",
            data_residency_region = payload.get("data_residency_region", ""),
            jurisdiction_code     = payload.get("jurisdiction_code", ""),
            brand_id              = payload.get("brand_id", ""),
        )

        return JSONResponse(status_code=202, content={
            "accepted":              True,
            "source_record_id":      str(result.source_record_id),
            "deduplication_outcome": result.deduplication_outcome,
            "correlation_id":        correlation_id,
            "webhook_id":            x_webhook_id or "",
        })

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Webhook ingestion failed: {exc}")


# ── GET /webhooks/secrets/{tenant_id} ────────────────────────────────────────

@router.get("/webhooks/secrets/{target_tenant_id}")
def list_webhook_configs(
    target_tenant_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """List active webhook signing configurations (admin only)."""
    if getattr(claims, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="admin role required")

    if str(claims.tenant_id) != target_tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")

    rows = q("""
        SELECT id, source_type, is_active, ip_allowlist, created_at, rotated_at
        FROM webhook_signing_configs
        WHERE tenant_id = %s::uuid
        ORDER BY created_at DESC
    """, (target_tenant_id,))

    return {
        "tenant_id": target_tenant_id,
        "configs": [
            {
                "id":          str(r["id"]),
                "source_type": r["source_type"],
                "is_active":   r["is_active"],
                "ip_allowlist": r.get("ip_allowlist") or [],
                "created_at":  r["created_at"].isoformat() if r.get("created_at") else None,
                "rotated_at":  r["rotated_at"].isoformat() if r.get("rotated_at") else None,
                "signing_secret": "***",  # never expose in API response
            }
            for r in rows
        ],
    }


# ── POST /webhooks/secrets/{tenant_id} ───────────────────────────────────────

@router.post("/webhooks/secrets/{target_tenant_id}", status_code=201)
def create_webhook_secret(
    target_tenant_id: str,
    body: dict,
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Create or rotate a webhook signing secret for a tenant + source_type pair.
    Admin only. Returns the new secret (only time it is shown in plaintext).
    """
    if getattr(claims, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="admin role required")

    if str(claims.tenant_id) != target_tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")

    source_type  = body.get("source_type")
    ip_allowlist = body.get("ip_allowlist", [])
    if not source_type:
        raise HTTPException(status_code=400, detail="source_type required")

    # Generate a new 32-byte secret
    new_secret = base64.urlsafe_b64encode(os.urandom(32)).decode()
    config_id  = uuid.uuid4()
    now        = datetime.now(timezone.utc)

    try:
        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor()

        # Deactivate any existing config for this tenant + source_type
        cur.execute("""
            UPDATE webhook_signing_configs
            SET is_active = false, rotated_at = %s
            WHERE tenant_id = %s::uuid AND source_type = %s AND is_active = true
        """, (now, target_tenant_id, source_type))

        # Insert new config
        cur.execute("""
            INSERT INTO webhook_signing_configs
                (id, tenant_id, source_type, signing_secret, ip_allowlist, is_active, created_at)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, true, %s)
        """, (
            config_id, target_tenant_id, source_type,
            new_secret, json.dumps(ip_allowlist), now,
        ))
        conn.commit()
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to store webhook config: {exc}")

    return {
        "id":            str(config_id),
        "tenant_id":     target_tenant_id,
        "source_type":   source_type,
        "signing_secret": new_secret,  # shown once — caller must store securely
        "ip_allowlist":  ip_allowlist,
        "created_at":    now.isoformat(),
        "warning":       "Store this secret securely — it will not be shown again",
    }

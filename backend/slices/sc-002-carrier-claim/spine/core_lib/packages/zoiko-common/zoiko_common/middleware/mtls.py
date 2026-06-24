"""
mTLS / SPIFFE service-to-service authentication dependency (FR-025).

In a service mesh (Istio/Envoy), mTLS is terminated by the sidecar proxy which
injects the verified peer SPIFFE URI into the X-Forwarded-Client-Cert (XFCC)
header before forwarding to the application.

Usage (FastAPI):
  from zoiko_common.middleware.mtls import require_mtls
  @router.post("/internal/execute")
  def execute(claims=Depends(get_claims), _=Depends(require_mtls)):
      ...

In dev (ZOIKO_DEV_MODE=true or ZOIKO_MTLS_ENABLED not set): always passes.
In prod: validates that XFCC header is present and URI matches allowed patterns.
"""
from __future__ import annotations

import os
import re
import logging

logger = logging.getLogger(__name__)

_MTLS_ENABLED = os.getenv("ZOIKO_MTLS_ENABLED", "false").lower() == "true"

# Allowed SPIFFE URI prefixes — all Zoiko services within the same trust domain
_ALLOWED_SPIFFE_PATTERN = re.compile(
    r"spiffe://zoiko\.internal/service/",
    re.IGNORECASE,
)


def _extract_spiffe_uri(xfcc_header: str) -> str | None:
    """Extract the SPIFFE URI from an XFCC header value."""
    for part in xfcc_header.split(";"):
        part = part.strip()
        if part.lower().startswith("uri=spiffe://"):
            return part[4:]   # strip "URI="
    return None


def require_mtls(
    x_forwarded_client_cert: str | None = None,
) -> str:
    """
    FastAPI dependency that validates mTLS peer identity.

    Returns the peer SPIFFE URI on success.
    Raises HTTP 401 if mTLS is enabled and the peer cert is missing or untrusted.
    """
    if not _MTLS_ENABLED:
        return "spiffe://zoiko.internal/service/dev"

    from fastapi import Header as _Header, HTTPException as _HTTPException

    if not x_forwarded_client_cert:
        logger.warning("mTLS: missing X-Forwarded-Client-Cert header")
        raise _HTTPException(
            status_code=401,
            detail={"error": "MTLS_REQUIRED", "detail": "Missing client certificate"},
        )

    spiffe_uri = _extract_spiffe_uri(x_forwarded_client_cert)
    if not spiffe_uri or not _ALLOWED_SPIFFE_PATTERN.match(spiffe_uri):
        logger.warning("mTLS: rejected peer URI=%s", spiffe_uri)
        raise _HTTPException(
            status_code=403,
            detail={"error": "MTLS_PEER_UNTRUSTED", "detail": f"Peer URI not allowed: {spiffe_uri}"},
        )

    logger.debug("mTLS: accepted peer %s", spiffe_uri)
    return spiffe_uri

"""
JWT token verifier — supports RS256 and ES256.

In dev: accepts tokens signed with a local HMAC secret (HS256) for test simplicity.
In staging/prod: fetches JWKS from the OIDC provider and validates RS256/ES256.
"""
from __future__ import annotations

import time
import hmac
import hashlib
import base64
import json
from typing import Optional

from .claims import ZoikoClaims


class TokenExpiredError(Exception):
    pass


class TokenInvalidError(Exception):
    pass


def _b64_decode(s: str) -> bytes:
    """URL-safe base64 decode with padding."""
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


class TokenVerifier:
    """
    Verifies JWTs for Zoiko services.

    dev_secret: if set, accepts HS256 tokens signed with this secret (dev/test only).
    jwks_url:   OIDC provider JWKS endpoint for RS256/ES256 (staging/prod).
    """

    def __init__(
        self,
        dev_secret: Optional[bytes] = None,
        jwks_url:   Optional[str]   = None,
        audience:   str = "*",
        issuer:     str = "https://auth.zoikotech.com",
    ):
        self._secret   = dev_secret
        self._jwks_url = jwks_url
        self._audience = audience
        self._issuer   = issuer

    def verify(self, token: str, expected_audience: str = "*") -> ZoikoClaims:
        """
        Verify and decode a JWT. Returns ZoikoClaims on success.
        Raises TokenExpiredError or TokenInvalidError on failure.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise TokenInvalidError("Token must have exactly 3 parts")

        header_b64, payload_b64, sig_b64 = parts

        try:
            header  = json.loads(_b64_decode(header_b64))
            payload = json.loads(_b64_decode(payload_b64))
        except Exception as e:
            raise TokenInvalidError(f"Cannot decode token: {e}")

        alg = header.get("alg", "")

        if alg == "HS256":
            self._verify_hs256(header_b64, payload_b64, sig_b64)
        elif alg in ("RS256", "ES256"):
            self._verify_asymmetric(header_b64, payload_b64, sig_b64, alg)
        else:
            raise TokenInvalidError(f"Unsupported algorithm: {alg}")

        # Validate standard claims
        now = int(time.time())
        if payload.get("exp", 0) < now:
            raise TokenExpiredError("Token has expired")

        iss = payload.get("iss", "")
        if self._issuer and iss != self._issuer:
            raise TokenInvalidError(f"Issuer mismatch: got {iss!r}, expected {self._issuer!r}")

        aud = payload.get("aud", "")
        if expected_audience != "*" and aud != expected_audience:
            raise TokenInvalidError(f"Audience mismatch: got {aud!r}, expected {expected_audience!r}")

        try:
            return ZoikoClaims.from_dict(payload)
        except ValueError as e:
            raise TokenInvalidError(str(e))

    # ── Signature verification ─────────────────────────────────────────────

    def _verify_hs256(self, header_b64: str, payload_b64: str, sig_b64: str) -> None:
        if not self._secret:
            raise TokenInvalidError("HS256 requires dev_secret to be set")
        msg      = f"{header_b64}.{payload_b64}".encode()
        expected = hmac.new(self._secret, msg, hashlib.sha256).digest()
        got      = _b64_decode(sig_b64)
        if not hmac.compare_digest(expected, got):
            raise TokenInvalidError("HS256 signature mismatch")

    def _verify_asymmetric(self, header_b64: str, payload_b64: str, sig_b64: str, alg: str) -> None:
        # In Phase 1 this is a stub — real JWKS fetch wired in Phase 2
        raise TokenInvalidError(
            f"{alg} verification requires JWKS endpoint — not yet wired in Phase 1 dev mode. "
            "Use HS256 with dev_secret for local testing."
        )

    # ── Token factory (dev / test helper) ─────────────────────────────────

    def make_dev_token(
        self,
        sub:       str,
        tenant_id: str,
        roles:     list[str] | None = None,
        ttl_sec:   int = 3600,
        audience:  str = "zoiko-dev",
    ) -> str:
        """Generate a signed HS256 token for local dev and tests."""
        if not self._secret:
            raise RuntimeError("dev_secret required to issue dev tokens")

        now     = int(time.time())
        header  = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub":       sub,
            "iss":       self._issuer,
            "aud":       audience,
            "exp":       now + ttl_sec,
            "iat":       now,
            "tenant_id": tenant_id,
            "roles":     roles or [],
            "zoiko_env": "dev",
        }

        h_b64 = base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode()).rstrip(b"=").decode()
        p_b64 = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
        msg   = f"{h_b64}.{p_b64}".encode()
        sig   = hmac.new(self._secret, msg, hashlib.sha256).digest()
        s_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
        return f"{h_b64}.{p_b64}.{s_b64}"

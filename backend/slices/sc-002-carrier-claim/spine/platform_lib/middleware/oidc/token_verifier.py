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

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric import utils as asym_utils

from .claims import ZoikoClaims

_JWKS_CACHE_TTL_SECONDS = 600  # re-fetch JWKS at most every 10 minutes


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
        self._jwks_cache:    dict  = {}
        self._jwks_cache_at: float = 0.0

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
        """Verify RS256/ES256 against the OIDC provider's JWKS (fail-closed)."""
        try:
            header = json.loads(_b64_decode(header_b64))
        except Exception as e:
            raise TokenInvalidError(f"Cannot decode header for {alg} verification: {e}")

        kid = header.get("kid")
        if not kid:
            raise TokenInvalidError(f"Token header missing 'kid' — required for {alg} verification")

        jwk        = self._find_jwk(kid)
        public_key = self._jwk_to_public_key(jwk)
        message    = f"{header_b64}.{payload_b64}".encode()
        signature  = _b64_decode(sig_b64)

        try:
            if alg == "RS256":
                public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
            elif alg == "ES256":
                # JWS encodes ECDSA signatures as raw r||s (32 bytes each for
                # P-256) — cryptography's verify() expects DER, so re-encode.
                if len(signature) != 64:
                    raise TokenInvalidError(f"ES256 signature must be 64 bytes (r||s), got {len(signature)}")
                r = int.from_bytes(signature[:32], "big")
                s = int.from_bytes(signature[32:], "big")
                public_key.verify(asym_utils.encode_dss_signature(r, s), message, ec.ECDSA(hashes.SHA256()))
            else:
                raise TokenInvalidError(f"Unsupported asymmetric algorithm: {alg}")
        except InvalidSignature:
            raise TokenInvalidError(f"{alg} signature verification failed")

    # ── JWKS fetch + cache ──────────────────────────────────────────────────

    def _fetch_jwks(self) -> dict:
        """Fetch the JWKS document, cached for _JWKS_CACHE_TTL_SECONDS.
        Fail-closed: no jwks_url configured or fetch failure (with no usable
        stale cache) raises rather than silently permitting the token."""
        now = time.time()
        if self._jwks_cache and (now - self._jwks_cache_at) < _JWKS_CACHE_TTL_SECONDS:
            return self._jwks_cache

        if not self._jwks_url:
            raise TokenInvalidError("RS256/ES256 verification requires jwks_url to be configured")

        try:
            resp = requests.get(self._jwks_url, timeout=5)
            resp.raise_for_status()
            jwks = resp.json()
        except Exception as e:
            if self._jwks_cache:
                return self._jwks_cache  # serve stale rather than hard-fail on a transient outage
            raise TokenInvalidError(f"Failed to fetch JWKS from {self._jwks_url}: {e}")

        self._jwks_cache    = jwks
        self._jwks_cache_at = now
        return jwks

    def _find_jwk(self, kid: str) -> dict:
        jwks = self._fetch_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key

        # kid not found — could be key rotation; force one refresh before giving up
        self._jwks_cache = {}
        jwks = self._fetch_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key

        raise TokenInvalidError(f"No JWK found for kid={kid!r}")

    @staticmethod
    def _jwk_to_public_key(jwk: dict):
        kty = jwk.get("kty")
        if kty == "RSA":
            n = int.from_bytes(_b64_decode(jwk["n"]), "big")
            e = int.from_bytes(_b64_decode(jwk["e"]), "big")
            return rsa.RSAPublicNumbers(e, n).public_key()
        if kty == "EC":
            curve = {
                "P-256": ec.SECP256R1(), "P-384": ec.SECP384R1(), "P-521": ec.SECP521R1(),
            }.get(jwk.get("crv"))
            if curve is None:
                raise TokenInvalidError(f"Unsupported EC curve: {jwk.get('crv')!r}")
            x = int.from_bytes(_b64_decode(jwk["x"]), "big")
            y = int.from_bytes(_b64_decode(jwk["y"]), "big")
            return ec.EllipticCurvePublicNumbers(x, y, curve).public_key()
        raise TokenInvalidError(f"Unsupported JWK key type: {kty!r}")

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

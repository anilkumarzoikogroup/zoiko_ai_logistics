"""
AES-256-GCM symmetric encryption for Zoiko payload storage (FR-001).

Format: nonce (12 bytes) || ciphertext || tag (16 bytes)

Usage:
  ciphertext = encrypt(dek, plaintext)
  plaintext  = decrypt(dek, ciphertext)

DEK derivation:
  Dev  — HKDF-SHA256 from ZOIKO_DEV_ENCRYPTION_KEY env var (or hardcoded dev seed).
  Prod — pass the raw DEK bytes obtained from Cloud KMS; never derive in-process.

Rule: hash BEFORE encrypt. The caller (ingestion handler) must compute
SHA-256(domain_tag + plaintext) BEFORE passing plaintext to encrypt().
"""
from __future__ import annotations

import os
import hashlib
import hmac

_DEV_MASTER = os.getenv(
    "ZOIKO_DEV_ENCRYPTION_KEY",
    "zoiko-dev-aes-master-key-not-for-production-use",
).encode()


def _derive_dek(tenant_id: str) -> bytes:
    """Derive a 32-byte AES-256 DEK for a tenant (dev only)."""
    return hmac.new(_DEV_MASTER, f"dek:{tenant_id}".encode(), hashlib.sha256).digest()


def get_dek(tenant_id: str) -> bytes:
    """
    Return the AES-256 DEK for tenant_id.
    Dev: deterministically derived from master key.
    Prod: call Cloud KMS to unwrap the tenant DEK blob.
    """
    kms_url = os.getenv("KMS_URL", "")
    if kms_url:
        return _fetch_from_kms(tenant_id, kms_url)
    return _derive_dek(tenant_id)


def encrypt(dek: bytes, plaintext: bytes, *, aad: bytes | None = None) -> tuple[bytes, bytes]:
    """
    AES-256-GCM encrypt.
    Returns: (ciphertext_without_nonce, nonce)
    The nonce (IV) is returned separately for external storage.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(dek) != 32:
        raise ValueError(f"DEK must be 32 bytes, got {len(dek)}")
    nonce = os.urandom(12)
    aesgcm = AESGCM(dek)
    ct_and_tag = aesgcm.encrypt(nonce, plaintext, aad)
    return ct_and_tag, nonce


def decrypt(dek: bytes, ciphertext: bytes, *, iv: bytes | None = None, aad: bytes | None = None) -> bytes:
    """
    AES-256-GCM decrypt.
    Supports two input formats:
      - Combined: ciphertext = nonce(12) + ciphertext + tag(16), iv=None
      - Split:    ciphertext = ciphertext_without_nonce + tag(16), iv=nonce
    Raises ValueError on authentication failure.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(dek) != 32:
        raise ValueError(f"DEK must be 32 bytes, got {len(dek)}")
    if iv is not None:
        nonce      = iv
        ct_and_tag = ciphertext
    else:
        if len(ciphertext) < 28:
            raise ValueError("Ciphertext too short")
        nonce      = ciphertext[:12]
        ct_and_tag = ciphertext[12:]
    aesgcm = AESGCM(dek)
    try:
        return aesgcm.decrypt(nonce, ct_and_tag, aad)
    except Exception as e:
        raise ValueError(f"AES-GCM authentication failed: {e}") from e


def _fetch_from_kms(tenant_id: str, kms_url: str) -> bytes:
    """Prod stub — POST to KMS to get unwrapped DEK."""
    import urllib.request, json
    req = urllib.request.Request(
        f"{kms_url}/v1/tenants/{tenant_id}/dek",
        headers={"Content-Type": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read())
    return bytes.fromhex(body["dek_hex"])

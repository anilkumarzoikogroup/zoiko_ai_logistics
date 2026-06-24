"""
Local KMS backend for dev — no GCP required.

Generates real Ed25519 key material in memory.
Key material is ephemeral (lost on restart) — intentional for dev.
"""
from __future__ import annotations

import os
import hashlib
import hmac
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat
)



class LocalKMSBackend:
    """
    In-process key store for local dev.

    Each kms_resource string maps to a deterministically derived Ed25519 key
    (HKDF-like derivation from a master seed so keys are stable within a process).
    """

    def __init__(self, master_seed: bytes | None = None):
        # Previously defaulted to os.urandom(32) — a fresh random seed on
        # every instantiation. Since keys are derived as HMAC(seed,
        # kms_resource), that meant the *same* kid produced a *different*
        # key every time a new LocalKMSBackend() was created — including in
        # a different process, or a second instance in the same process.
        # A KMS's entire contract is that the same key id always resolves to
        # the same key; signatures made by one instance could never be
        # verified by another, which silently broke every offline/
        # cross-process verification path (ACR verifier, transparency log).
        # ZOIKO_KMS_DEV_SEED lets a deployment pin its own seed; otherwise
        # fall back to a fixed (not random) dev constant so all instances
        # within this codebase agree by default.
        if master_seed is not None:
            self._seed = master_seed
        else:
            env_seed = os.getenv("ZOIKO_KMS_DEV_SEED", "")
            self._seed = hashlib.sha256(
                env_seed.encode() if env_seed else b"zoiko-local-kms-dev-fixed-seed-v1"
            ).digest()
        self._cache: dict[str, Ed25519PrivateKey] = {}

    # ── Signing ──────────────────────────────────────────────────────────────

    def sign(self, kms_resource: str, payload: bytes) -> bytes:
        """Sign payload with the Ed25519 key for this resource. Returns 64-byte sig."""
        key = self._get_or_create(kms_resource)
        return key.sign(payload)

    def verify(self, kms_resource: str, payload: bytes, signature: bytes) -> bool:
        """Return True if signature is valid for this resource's public key."""
        try:
            key = self._get_or_create(kms_resource)
            key.public_key().verify(signature, payload)
            return True
        except Exception:
            return False

    # ── Key material ─────────────────────────────────────────────────────────

    def public_key_der(self, kms_resource: str) -> bytes:
        key = self._get_or_create(kms_resource)
        return key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)

    def encrypt(self, kms_resource: str, plaintext: bytes) -> bytes:
        """
        Symmetric encryption for DEK_ENCRYPT purpose.
        Uses XOR with a derived key (dev only — not production-grade).
        In prod this would be AES-256-GCM via Cloud KMS.
        """
        derived = self._derive_symmetric(kms_resource, len(plaintext))
        return bytes(a ^ b for a, b in zip(plaintext, derived))

    def decrypt(self, kms_resource: str, ciphertext: bytes) -> bytes:
        """XOR decryption (symmetric — same as encrypt)."""
        return self.encrypt(kms_resource, ciphertext)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _get_or_create(self, kms_resource: str) -> Ed25519PrivateKey:
        if kms_resource not in self._cache:
            seed_material = hmac.new(self._seed, kms_resource.encode(), hashlib.sha256).digest()
            self._cache[kms_resource] = Ed25519PrivateKey.from_private_bytes(seed_material)
        return self._cache[kms_resource]

    def _derive_symmetric(self, kms_resource: str, length: int) -> bytes:
        result = b""
        counter = 0
        while len(result) < length:
            block = hmac.new(self._seed, f"{kms_resource}:{counter}".encode(), hashlib.sha256).digest()
            result += block
            counter += 1
        return result[:length]

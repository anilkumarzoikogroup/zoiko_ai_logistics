"""COSE Sign1 / GCP KMS signing abstraction for Zoiko services.

Each service has its own EC_SIGN_ED25519 key in GCP KMS.  In dev/test we use
a local ephemeral Ed25519 key so no GCP dependency is required.

The signer produces COSE_Sign1 structures (RFC 9052) with:
  - alg: EdDSA  (COSE label -8)
  - kid: KMS key version resource name (or "local:<fingerprint>" in dev)
  - payload: caller-supplied bytes (JCS canonical form in production)

Verification is intentionally symmetric: given the public key bytes (DER),
any party can verify without GCP access — enabling offline ACR verification.
"""
from __future__ import annotations

import abc
import hashlib
import os
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PublicFormat,
    PrivateFormat,
)

# COSE algorithm label for EdDSA (RFC 9053 §2.2)
COSE_ALG_EDDSA = -8

# COSE header labels (RFC 9052 §3.1)
COSE_LABEL_ALG = 1
COSE_LABEL_KID = 4


@dataclass(frozen=True)
class SignedEnvelope:
    """Minimal COSE_Sign1 envelope representation (serialization-agnostic)."""

    payload: bytes          # The signed bytes (JCS canonical form)
    signature: bytes        # Raw Ed25519 signature (64 bytes)
    kid: str                # Key identifier (KMS resource name or "local:…")
    alg: int = COSE_ALG_EDDSA

    def to_dict(self) -> dict:
        return {
            "alg": self.alg,
            "kid": self.kid,
            "payload": self.payload.hex(),
            "signature": self.signature.hex(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SignedEnvelope":
        return cls(
            alg=d["alg"],
            kid=d["kid"],
            payload=bytes.fromhex(d["payload"]),
            signature=bytes.fromhex(d["signature"]),
        )


class SignerBackend(Protocol):
    """Interface all signing backends must satisfy."""

    @property
    def kid(self) -> str: ...

    def sign(self, payload: bytes) -> bytes: ...

    def public_key_der(self) -> bytes: ...


class LocalEd25519Backend:
    """Ephemeral Ed25519 key for dev/test.  Never use in staging or prod."""

    def __init__(self, private_key: Ed25519PrivateKey | None = None) -> None:
        self._key = private_key or Ed25519PrivateKey.generate()
        pub_der = self._key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        self._kid = "local:" + hashlib.sha256(pub_der).hexdigest()[:16]

    @property
    def kid(self) -> str:
        return self._kid

    def sign(self, payload: bytes) -> bytes:
        return self._key.sign(payload)

    def public_key_der(self) -> bytes:
        return self._key.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )

    def private_key_pem(self) -> bytes:
        """Export private key PEM — test/dev only."""
        return self._key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())


class ZoikoSigner:
    """High-level signer used by all Zoiko services.

    In production inject a GcpKmsBackend (implemented in P1 after KMS keys
    are provisioned).  In dev/test inject LocalEd25519Backend.
    """

    def __init__(self, backend: SignerBackend) -> None:
        self._backend = backend

    def sign(self, payload: bytes) -> SignedEnvelope:
        """Sign *payload* and return a :class:`SignedEnvelope`."""
        signature = self._backend.sign(payload)
        return SignedEnvelope(
            payload=payload,
            signature=signature,
            kid=self._backend.kid,
        )

    @property
    def kid(self) -> str:
        return self._backend.kid

    @property
    def public_key_der(self) -> bytes:
        return self._backend.public_key_der()


def verify_envelope(envelope: SignedEnvelope, public_key_der: bytes) -> bool:
    """Return True iff *envelope.signature* is a valid Ed25519 signature over
    *envelope.payload* by the key encoded in *public_key_der* (SubjectPublicKeyInfo DER).

    This function is intentionally side-effect-free so it can be called from
    the offline ACR verifier with zero network access.
    """
    from cryptography.hazmat.primitives.serialization import load_der_public_key

    try:
        pub: Ed25519PublicKey = load_der_public_key(public_key_der)  # type: ignore[assignment]
        pub.verify(envelope.signature, envelope.payload)
        return True
    except Exception:  # noqa: BLE001
        return False

"""
GCP Cloud KMS stub — placeholder for staging/prod.

In Phase 1 this is a typed stub that documents the interface.
Phase 4+ wires in the real google-cloud-kms client.

GCP resource path format:
  projects/{project}/locations/{location}/keyRings/{ring}/cryptoKeys/{key}/cryptoKeyVersions/{version}
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GcpKmsConfig:
    project:   str         # e.g. "zoiko-logistics-staging"
    location:  str = "us-central1"
    key_ring:  str = "zoiko-keyring"


class GcpKMSStub:
    """
    Interface contract for the real GCP KMS backend.
    Raises NotImplementedError in all methods — swap in real implementation in Phase 4.
    """

    def __init__(self, config: GcpKmsConfig):
        self._cfg = config

    def _resource(self, key_name: str, version: int = 1) -> str:
        return (
            f"projects/{self._cfg.project}"
            f"/locations/{self._cfg.location}"
            f"/keyRings/{self._cfg.key_ring}"
            f"/cryptoKeys/{key_name}"
            f"/cryptoKeyVersions/{version}"
        )

    def sign(self, key_name: str, payload: bytes, version: int = 1) -> bytes:
        """Sign with Cloud KMS Ed25519 key. Raises NotImplementedError until Phase 4."""
        raise NotImplementedError(
            f"GCP KMS not wired yet. Resource would be: {self._resource(key_name, version)}"
        )

    def verify(self, key_name: str, payload: bytes, signature: bytes, version: int = 1) -> bool:
        raise NotImplementedError("GCP KMS verify not wired yet.")

    def encrypt(self, key_name: str, plaintext: bytes) -> bytes:
        """AES-256-GCM encrypt via Cloud KMS DEK."""
        raise NotImplementedError("GCP KMS encrypt not wired yet.")

    def decrypt(self, key_name: str, ciphertext: bytes) -> bytes:
        raise NotImplementedError("GCP KMS decrypt not wired yet.")

    def get_public_key(self, key_name: str, version: int = 1) -> bytes:
        """Returns DER-encoded public key from Cloud KMS."""
        raise NotImplementedError("GCP KMS get_public_key not wired yet.")

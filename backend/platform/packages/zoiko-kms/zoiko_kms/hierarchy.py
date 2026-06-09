"""
Key hierarchy model for Zoiko AI Logistics.

Three-tier hierarchy:
  Root CA Key  →  Tenant DEK (Data Encryption Key)  →  Tenant Signing Key

Rules:
- Root CA key is HSM-backed in staging/prod (never SOFTWARE in prod)
- DEKs are derived per tenant and rotated every 90 days
- Signing keys are Ed25519; used for JCS + Merkle signatures
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class KeyPurpose(str, Enum):
    ROOT_CA      = "ROOT_CA"       # HSM root — never leaves KMS
    DEK_ENCRYPT  = "DEK_ENCRYPT"   # AES-256-GCM data encryption key
    SIGNING      = "SIGNING"        # Ed25519 signing key


class KeyBackend(str, Enum):
    SOFTWARE = "SOFTWARE"   # dev only
    HSM      = "HSM"        # staging / prod


@dataclass
class KeyRecord:
    """Represents one key in the hierarchy."""
    id:          str
    tenant_id:   str
    purpose:     KeyPurpose
    backend:     KeyBackend
    kms_resource: str           # e.g. "local/dev/tenant-slug-dek"  or GCP resource path
    version:     int = 1
    created_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rotates_at:  Optional[datetime] = None
    is_active:   bool = True

    def __post_init__(self):
        if self.rotates_at is None:
            self.rotates_at = self.created_at + timedelta(days=90)

    @property
    def days_until_rotation(self) -> int:
        delta = self.rotates_at - datetime.now(timezone.utc)
        return max(0, delta.days)

    @property
    def needs_rotation(self) -> bool:
        return self.days_until_rotation == 0

    def fingerprint(self) -> str:
        """SHA-256 of tenant_id + purpose + version — used in token tenant_binding."""
        data = f"{self.tenant_id}:{self.purpose}:{self.version}".encode()
        return hashlib.sha256(data).hexdigest()[:16]


class KeyHierarchy:
    """
    Manages the three-tier key hierarchy for a tenant.

    dev:     SOFTWARE backend,  local key material
    staging/prod: HSM backend,  GCP Cloud KMS
    """

    def __init__(self, env: str = "dev"):
        self._env     = env
        self._backend = KeyBackend.SOFTWARE if env == "dev" else KeyBackend.HSM
        self._store:  dict[str, KeyRecord] = {}   # key_id → KeyRecord

    # ── Public API ────────────────────────────────────────────────────────────

    def provision_tenant(self, tenant_id: str, tenant_slug: str) -> list[KeyRecord]:
        """Create ROOT_CA, DEK_ENCRYPT, and SIGNING keys for a new tenant."""
        self._assert_not_prod_software()
        records = []
        for purpose in [KeyPurpose.ROOT_CA, KeyPurpose.DEK_ENCRYPT, KeyPurpose.SIGNING]:
            rec = self._make_key(tenant_id, tenant_slug, purpose)
            self._store[rec.id] = rec
            records.append(rec)
        return records

    def get_active_key(self, tenant_id: str, purpose: KeyPurpose) -> Optional[KeyRecord]:
        """Return the active key for this tenant + purpose."""
        matches = [
            k for k in self._store.values()
            if k.tenant_id == tenant_id and k.purpose == purpose and k.is_active
        ]
        return max(matches, key=lambda k: k.version, default=None)

    def rotate_key(self, tenant_id: str, purpose: KeyPurpose) -> KeyRecord:
        """Issue a new key version; mark the old one inactive."""
        old = self.get_active_key(tenant_id, purpose)
        if old:
            old.is_active = False
            slug = old.kms_resource.split("/")[-1].rsplit("-", 2)[0]
        else:
            slug = tenant_id[:8]
        new_key = self._make_key(tenant_id, slug, purpose, version=(old.version + 1 if old else 1))
        self._store[new_key.id] = new_key
        return new_key

    def list_keys(self, tenant_id: str) -> list[KeyRecord]:
        return [k for k in self._store.values() if k.tenant_id == tenant_id]

    def keys_needing_rotation(self) -> list[KeyRecord]:
        return [k for k in self._store.values() if k.is_active and k.needs_rotation]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_key(self, tenant_id: str, slug: str, purpose: KeyPurpose, version: int = 1) -> KeyRecord:
        return KeyRecord(
            id           = str(uuid.uuid4()),
            tenant_id    = tenant_id,
            purpose      = purpose,
            backend      = self._backend,
            kms_resource = f"{self._env}/{slug}-{purpose.value.lower()}-v{version}",
            version      = version,
        )

    def _assert_not_prod_software(self):
        if self._env == "prod" and self._backend == KeyBackend.SOFTWARE:
            raise RuntimeError("SOFTWARE KMS keys are not allowed in prod. Use HSM.")

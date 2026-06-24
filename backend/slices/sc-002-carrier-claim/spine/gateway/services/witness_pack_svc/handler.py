"""
Witness Pack Service — pins the exact content of reference data (e.g. a
contract rate) at the moment it was actually used in validation.

Distinct from rate-version-binding (0038): that detects tampering on the
*current* row. A witness pack survives even if the row is later legitimately
superseded — it's an independent, signed record of "this exact content
existed and was relied upon at this exact time," usable for replay/audit
long after the live row has moved on to a new version.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from shared.signer import sign
from zoiko_common.crypto.jcs import canonicalize

psycopg2.extras.register_uuid()

_DOMAIN_TAG = b"zoiko.witness_pack.v1:"


@dataclass
class WitnessPackResult:
    witness_pack_id:  str
    tenant_id:        str
    source_record_id: str
    subject_type:     str
    subject_id:       str
    snapshot_hash:    str  # hex
    created_at:        datetime


class WitnessPackHandler:
    def __init__(self, db_url: str, tenant_slug: str = "default"):
        self._db_url      = db_url
        self._tenant_slug = tenant_slug

    def create(
        self,
        tenant_id:        str,
        source_record_id: str,
        subject_type:     str,
        subject_id:       str,
        snapshot_payload: dict,
    ) -> WitnessPackResult:
        tenant_id        = str(tenant_id)
        source_record_id = str(source_record_id)
        subject_id        = str(subject_id)
        now              = datetime.now(timezone.utc)

        snapshot_bytes = canonicalize(snapshot_payload)
        snapshot_hash  = hashlib.sha256(_DOMAIN_TAG + snapshot_bytes).digest()
        signature, kid = sign(self._tenant_slug, snapshot_hash)

        pack_id = uuid.uuid4()
        conn = psycopg2.connect(self._db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO witness_packs
                    (id, tenant_id, source_record_id, subject_type, subject_id,
                     snapshot_payload, snapshot_hash, signature, kid, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s::uuid, %s::jsonb, %s, %s, %s, %s)
            """, (
                pack_id, tenant_id, source_record_id, subject_type, subject_id,
                json.dumps(snapshot_payload), snapshot_hash, signature, kid, now,
            ))
            conn.commit()
        finally:
            conn.close()

        return WitnessPackResult(
            witness_pack_id  = str(pack_id),
            tenant_id        = tenant_id,
            source_record_id = source_record_id,
            subject_type     = subject_type,
            subject_id       = subject_id,
            snapshot_hash    = snapshot_hash.hex(),
            created_at       = now,
        )

    def verify(self, witness_pack_id: str, tenant_id: str) -> bool:
        """Re-hash the stored snapshot_payload and compare to snapshot_hash —
        proves the pack itself hasn't been altered since creation. Independent
        of whether the live subject row (e.g. contract_rates) still matches."""
        conn = psycopg2.connect(self._db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT snapshot_payload, snapshot_hash FROM witness_packs "
                "WHERE id=%s::uuid AND tenant_id=%s::uuid",
                (witness_pack_id, str(tenant_id)),
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            raise ValueError(f"Witness pack '{witness_pack_id}' not found")

        payload = row["snapshot_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        recomputed = hashlib.sha256(_DOMAIN_TAG + canonicalize(payload)).digest()
        return recomputed == bytes(row["snapshot_hash"])

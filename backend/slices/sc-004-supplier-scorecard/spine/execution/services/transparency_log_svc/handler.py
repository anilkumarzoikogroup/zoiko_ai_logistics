"""
SC-004 Transparency Log Service — append-only Merkle log over issued ACRs.

Every ACR appended is batched per-tenant into a Merkle tree whose root is
signed and persisted as a commit. Inclusion proof allows independent
verification without live DB access.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401

from shared.signer import sign
from zoiko_common.crypto.merkle import MerkleTree, MerkleProof, hash_leaf

psycopg2.extras.register_uuid()

_DOMAIN_TAG = "zoiko/v1/transparency-log"


@dataclass
class InclusionProof:
    acr_id:             str
    tenant_id:          str
    leaf_hash:          str
    root_hash:          str
    commit_id:          str
    proof:              dict
    witness_signature:  str
    witness_kid:        str


class TransparencyLogHandler:
    def __init__(self, db_url: str, tenant_slug: str = "default"):
        self._db_url      = db_url
        self._tenant_slug = tenant_slug

    def append(self, tenant_id: str, acr_id: str, acr_merkle_root_hex: str) -> str:
        tenant_id = str(tenant_id)
        acr_id    = str(acr_id)

        leaf_hash = hash_leaf(_DOMAIN_TAG, f"{acr_id}:{acr_merkle_root_hex}".encode())

        conn = psycopg2.connect(self._db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            lock_key = int(uuid.UUID(tenant_id)) % (2**31)
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

            cur.execute(
                "SELECT COALESCE(MAX(log_index), -1) + 1 AS next_index "
                "FROM transparency_log_entries WHERE tenant_id=%s",
                (tenant_id,),
            )
            log_index = cur.fetchone()["next_index"]

            entry_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO transparency_log_entries
                    (id, tenant_id, acr_id, log_index, leaf_hash, appended_at)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s)
            """, (entry_id, tenant_id, acr_id, log_index, leaf_hash, datetime.now(timezone.utc)))
            conn.commit()
        finally:
            conn.close()

        self._commit_pending(tenant_id)
        return str(entry_id)

    def _commit_pending(self, tenant_id: str) -> Optional[str]:
        tenant_id = str(tenant_id)
        conn = psycopg2.connect(self._db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            lock_key = int(uuid.UUID(tenant_id)) % (2**31)
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

            cur.execute(
                "SELECT id, leaf_hash FROM transparency_log_entries "
                "WHERE tenant_id=%s AND commit_id IS NULL ORDER BY log_index ASC",
                (tenant_id,),
            )
            pending = cur.fetchall()
            if not pending:
                conn.commit()
                return None

            tree = MerkleTree(_DOMAIN_TAG)
            tree._leaves = [bytes(r["leaf_hash"]) for r in pending]
            root_hash = tree.root()

            witness_sig, witness_kid = sign(self._tenant_slug, root_hash)

            commit_id = uuid.uuid4()
            now       = datetime.now(timezone.utc)
            cur.execute("""
                INSERT INTO transparency_log_commits
                    (id, tenant_id, root_hash, leaf_count, witness_signature, witness_kid, committed_at)
                VALUES (%s, %s::uuid, %s, %s, %s, %s, %s)
            """, (commit_id, tenant_id, root_hash, len(pending), witness_sig, witness_kid, now))

            ids = [r["id"] for r in pending]
            cur.execute(
                "UPDATE transparency_log_entries SET commit_id=%s WHERE id = ANY(%s)",
                (commit_id, ids),
            )
            conn.commit()
            return str(commit_id)
        finally:
            conn.close()

    def get_inclusion_proof(self, tenant_id: str, acr_id: str) -> InclusionProof:
        tenant_id, acr_id = str(tenant_id), str(acr_id)
        conn = psycopg2.connect(self._db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, log_index, leaf_hash, commit_id FROM transparency_log_entries "
                "WHERE tenant_id=%s AND acr_id=%s",
                (tenant_id, acr_id),
            )
            entry = cur.fetchone()
            if not entry:
                raise ValueError(f"No transparency log entry for ACR '{acr_id}'")
            if not entry["commit_id"]:
                raise ValueError(f"Transparency log entry for ACR '{acr_id}' not yet committed")

            cur.execute(
                "SELECT root_hash, witness_signature, witness_kid "
                "FROM transparency_log_commits WHERE id=%s",
                (entry["commit_id"],),
            )
            commit = cur.fetchone()

            cur.execute(
                "SELECT log_index, leaf_hash FROM transparency_log_entries "
                "WHERE commit_id=%s ORDER BY log_index ASC",
                (entry["commit_id"],),
            )
            siblings = cur.fetchall()
        finally:
            conn.close()

        leaf_hashes = [bytes(r["leaf_hash"]) for r in siblings]
        local_index = next(i for i, r in enumerate(siblings) if r["log_index"] == entry["log_index"])

        tree = MerkleTree(_DOMAIN_TAG)
        tree._leaves = leaf_hashes
        proof = tree.proof(local_index)

        return InclusionProof(
            acr_id            = acr_id,
            tenant_id         = tenant_id,
            leaf_hash         = bytes(entry["leaf_hash"]).hex(),
            root_hash         = bytes(commit["root_hash"]).hex(),
            commit_id         = str(entry["commit_id"]),
            proof             = proof.to_dict(),
            witness_signature = bytes(commit["witness_signature"]).hex(),
            witness_kid       = commit["witness_kid"],
        )

    @staticmethod
    def verify_inclusion(root_hash_hex: str, leaf_hash_hex: str, proof_dict: dict) -> bool:
        root  = bytes.fromhex(root_hash_hex)
        leaf  = bytes.fromhex(leaf_hash_hex)
        proof = MerkleProof.from_dict(proof_dict)
        return MerkleTree.verify(root, leaf, proof)

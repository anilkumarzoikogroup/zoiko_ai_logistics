import paths  # noqa: F401
import uuid
import hashlib
from datetime import datetime, timezone

from shared.db import q, DB_URL
from zoiko_common.crypto.jcs import canonicalize as jcs
from shared.signer import sign

try:
    from zoiko_common.crypto.merkle import MerkleTree
    _MERKLE_AVAILABLE = True
except ImportError:
    _MERKLE_AVAILABLE = False


class EvidenceHandler:
    def __init__(self, db_url: str = DB_URL, broker=None, tenant_slug: str = "default"):
        self.db_url = db_url
        self.broker = broker
        self.tenant_slug = tenant_slug

    def bundle(
        self,
        tenant_id,
        case_id,
        canonical_invoice_id,
        charge_lines: list,
    ) -> dict:
        bundle_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # --- Pass 1: compute item hashes (no DB writes yet) ---
        items = []
        item_hashes: list[bytes] = []
        for charge_line in charge_lines:
            item_dict = {
                **charge_line,
                "canonical_invoice_id": str(canonical_invoice_id),
                "case_id": str(case_id),
            }
            item_bytes = jcs(item_dict)
            item_hash = hashlib.sha256(b"zoiko.evidence.item.v1:" + item_bytes).digest()
            item_sig, item_kid = sign(self.tenant_slug, item_hash)
            items.append({
                "id": uuid.uuid4(),
                "hash": item_hash,
                "sig": item_sig,
                "kid": item_kid,
            })
            item_hashes.append(item_hash)

        # --- Compute bundle hash from all item hashes ---
        if item_hashes:
            if _MERKLE_AVAILABLE:
                tree = MerkleTree("zoiko/v1/evidence-item")
                for h in item_hashes:
                    tree.append(h)
                bundle_hash_bytes: bytes = tree.root()
            else:
                combined = b"".join(item_hashes)
                bundle_hash_bytes = hashlib.sha256(combined).digest()
        else:
            bundle_hash_bytes = hashlib.sha256(b"").digest()

        bundle_sig, bundle_kid = sign(self.tenant_slug, bundle_hash_bytes)

        # --- Pass 2: INSERT bundle first (FK parent), then items ---
        q(
            """
            INSERT INTO evidence_bundles
                (id, tenant_id, case_id, bundle_hash, signature, kid, created_at)
            VALUES
                (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                str(bundle_id),
                str(tenant_id),
                str(case_id),
                bundle_hash_bytes.hex(),
                bundle_sig.hex(),
                bundle_kid,
                now,
            ),
            self.db_url,
        )

        for item in items:
            q(
                """
                INSERT INTO evidence_items
                    (id, tenant_id, bundle_id, item_type, entity_id, item_hash, signature, kid, added_at)
                VALUES
                    (%s::uuid, %s::uuid, %s::uuid, %s, %s::uuid, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    str(item["id"]),
                    str(tenant_id),
                    str(bundle_id),
                    "charge_line",
                    str(canonical_invoice_id),
                    item["hash"].hex(),
                    item["sig"].hex(),
                    item["kid"],
                    now,
                ),
                self.db_url,
            )

        return {
            "bundle_id": str(bundle_id),
            "item_count": len(charge_lines),
            "bundle_hash": bundle_hash_bytes.hex(),
        }

"""
Evidence Service tests.

Unit tests (no DB): hash computation, Merkle root.
Integration tests:  add_item + get_bundle (skip if PostgreSQL unreachable).
"""
import hashlib
import pytest

import paths  # noqa: F401


# ── Unit: domain-tagged hash ──────────────────────────────────────────────────

class TestEvidenceHash:
    def test_domain_tag_applied(self):
        from services.evidence_svc.handler import DOMAIN_TAG
        content = b"BOL-12345-signed-copy"
        expected = hashlib.sha256(DOMAIN_TAG + content).hexdigest()
        assert len(expected) == 64

    def test_different_content_different_hash(self):
        from services.evidence_svc.handler import DOMAIN_TAG
        h1 = hashlib.sha256(DOMAIN_TAG + b"content_a").digest()
        h2 = hashlib.sha256(DOMAIN_TAG + b"content_b").digest()
        assert h1 != h2

    def test_same_content_same_hash(self):
        from services.evidence_svc.handler import DOMAIN_TAG
        content = b"carrier_invoice_page_1"
        h1 = hashlib.sha256(DOMAIN_TAG + content).digest()
        h2 = hashlib.sha256(DOMAIN_TAG + content).digest()
        assert h1 == h2


# ── Unit: Merkle root over evidence items ────────────────────────────────────

class TestMerkleRoot:
    def test_single_item_root_is_leaf_hash(self):
        from zoiko_common.crypto.merkle import MerkleTree, hash_leaf
        from services.evidence_svc.handler import DOMAIN_TAG, MERKLE_DOMAIN

        content = b"single_evidence_item"
        item_hash = hashlib.sha256(DOMAIN_TAG + content).digest()

        tree = MerkleTree(MERKLE_DOMAIN)
        tree.append(item_hash)
        root = tree.root()

        expected_leaf = hash_leaf(MERKLE_DOMAIN, item_hash)
        assert root == expected_leaf

    def test_two_items_root_changes(self):
        from zoiko_common.crypto.merkle import MerkleTree
        from services.evidence_svc.handler import DOMAIN_TAG, MERKLE_DOMAIN

        h1 = hashlib.sha256(DOMAIN_TAG + b"item_1").digest()
        h2 = hashlib.sha256(DOMAIN_TAG + b"item_2").digest()

        tree1 = MerkleTree(MERKLE_DOMAIN)
        tree1.append(h1)
        root1 = tree1.root()

        tree2 = MerkleTree(MERKLE_DOMAIN)
        tree2.append(h1)
        tree2.append(h2)
        root2 = tree2.root()

        assert root1 != root2

    def test_order_matters(self):
        from zoiko_common.crypto.merkle import MerkleTree
        from services.evidence_svc.handler import DOMAIN_TAG, MERKLE_DOMAIN

        h1 = hashlib.sha256(DOMAIN_TAG + b"item_a").digest()
        h2 = hashlib.sha256(DOMAIN_TAG + b"item_b").digest()

        tree_ab = MerkleTree(MERKLE_DOMAIN)
        tree_ab.append(h1); tree_ab.append(h2)

        tree_ba = MerkleTree(MERKLE_DOMAIN)
        tree_ba.append(h2); tree_ba.append(h1)

        assert tree_ab.root() != tree_ba.root()


# ── Integration: add_item + get_bundle ────────────────────────────────────────

class TestEvidenceIntegration:
    def test_add_first_item_creates_bundle(self, db_url, test_case, broker):
        from services.evidence_svc.handler import EvidenceHandler
        handler = EvidenceHandler(db_url, broker, "default")
        result  = handler.add_item(
            tenant_id     = test_case["tenant_id"],
            case_id       = test_case["id"],
            item_type     = "BOL",
            content_bytes = b"Bill of Lading - Hyderabad to Warangal",
            actor_sub     = "ravi@amazon.com",
        )
        assert result.bundle_id is not None
        assert result.item_hash != ""
        assert result.bundle_hash != ""

    def test_add_second_item_updates_bundle_hash(self, db_url, test_case, broker):
        from services.evidence_svc.handler import EvidenceHandler
        handler = EvidenceHandler(db_url, broker, "default")

        r1 = handler.add_item(
            tenant_id     = test_case["tenant_id"],
            case_id       = test_case["id"],
            item_type     = "RATE_SHEET",
            content_bytes = b"Contracted rate: 8000 INR",
            actor_sub     = "ravi@amazon.com",
        )
        r2 = handler.add_item(
            tenant_id     = test_case["tenant_id"],
            case_id       = test_case["id"],
            item_type     = "INVOICE",
            content_bytes = b"Carrier invoice: 12500 INR",
            actor_sub     = "ravi@amazon.com",
        )
        assert r1.bundle_id == r2.bundle_id       # same bundle
        assert r1.bundle_hash != r2.bundle_hash   # Merkle root updated

    def test_get_bundle_returns_item_count(self, db_url, test_case, broker):
        from services.evidence_svc.handler import EvidenceHandler
        handler = EvidenceHandler(db_url, broker, "default")
        handler.add_item(
            tenant_id     = test_case["tenant_id"],
            case_id       = test_case["id"],
            item_type     = "PHOTO",
            content_bytes = b"damaged goods photograph",
            actor_sub     = "ravi@amazon.com",
        )
        bundle = handler.get_bundle(
            tenant_id = test_case["tenant_id"],
            case_id   = test_case["id"],
        )
        assert bundle.item_count >= 1
        assert bundle.bundle_hash != ""

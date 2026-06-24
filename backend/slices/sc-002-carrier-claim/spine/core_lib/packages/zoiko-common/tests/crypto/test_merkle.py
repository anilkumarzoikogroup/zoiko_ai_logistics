"""Merkle tree test vectors — CI hard block (must be 100% green).

All tests marked `merkle_vector` run via `make test-vectors` and block
CI merge if any fail.

Vector construction:
  leaf_i = hash_leaf("zoiko/v1/test", b"item-<i>")
  internal(a,b) = SHA-256(0x01 || a || b)
"""
from __future__ import annotations

import hashlib

import pytest

from zoiko_common.crypto.merkle import (
    MerkleProof,
    MerkleTree,
    hash_internal,
    hash_leaf,
)

DOMAIN = "zoiko/v1/test"


def _leaf(i: int) -> bytes:
    return hash_leaf(DOMAIN, f"item-{i}".encode())


# ---------------------------------------------------------------------------
# Primitive hashing
# ---------------------------------------------------------------------------


@pytest.mark.merkle_vector
def test_leaf_hash_deterministic():
    a = hash_leaf(DOMAIN, b"data")
    b = hash_leaf(DOMAIN, b"data")
    assert a == b
    assert len(a) == 32


@pytest.mark.merkle_vector
def test_leaf_hash_domain_separated():
    a = hash_leaf("zoiko/v1/source-record", b"data")
    b = hash_leaf("zoiko/v1/canonical-invoice", b"data")
    assert a != b


@pytest.mark.merkle_vector
def test_leaf_hash_prefix_byte():
    """Leaf must use 0x00 prefix — not the same as an internal node over same data."""
    data = b"same"
    leaf = hash_leaf(DOMAIN, data)
    internal = hash_internal(
        hashlib.sha256(b"\x00" + DOMAIN.encode() + b"sam").digest(),
        hashlib.sha256(b"e").digest(),
    )
    assert leaf != internal


@pytest.mark.merkle_vector
def test_internal_hash_deterministic():
    left = b"\x01" * 32
    right = b"\x02" * 32
    assert hash_internal(left, right) == hash_internal(left, right)
    assert hash_internal(left, right) != hash_internal(right, left)


@pytest.mark.merkle_vector
def test_internal_hash_known_value():
    left = b"\xaa" * 32
    right = b"\xbb" * 32
    expected = hashlib.sha256(b"\x01" + left + right).digest()
    assert hash_internal(left, right) == expected


# ---------------------------------------------------------------------------
# MerkleTree.root — known vector roots
# ---------------------------------------------------------------------------


@pytest.mark.merkle_vector
def test_single_leaf_root_equals_leaf_hash():
    tree = MerkleTree(DOMAIN)
    tree.append(b"item-0")
    assert tree.root() == hash_leaf(DOMAIN, b"item-0")


@pytest.mark.merkle_vector
def test_two_leaf_root():
    l0, l1 = _leaf(0), _leaf(1)
    expected_root = hash_internal(l0, l1)
    tree = MerkleTree(DOMAIN)
    tree.append(b"item-0")
    tree.append(b"item-1")
    assert tree.root() == expected_root


@pytest.mark.merkle_vector
def test_four_leaf_root():
    l0, l1, l2, l3 = _leaf(0), _leaf(1), _leaf(2), _leaf(3)
    n01 = hash_internal(l0, l1)
    n23 = hash_internal(l2, l3)
    expected_root = hash_internal(n01, n23)

    tree = MerkleTree(DOMAIN)
    for i in range(4):
        tree.append(f"item-{i}".encode())
    assert tree.root() == expected_root


@pytest.mark.merkle_vector
def test_three_leaf_root_odd_promotion():
    """Odd leaf count: last leaf is duplicated at next level per our scheme."""
    l0, l1, l2 = _leaf(0), _leaf(1), _leaf(2)
    n01 = hash_internal(l0, l1)
    n22 = hash_internal(l2, l2)  # l2 promoted with itself
    expected_root = hash_internal(n01, n22)

    tree = MerkleTree(DOMAIN)
    for i in range(3):
        tree.append(f"item-{i}".encode())
    assert tree.root() == expected_root


@pytest.mark.merkle_vector
def test_root_deterministic():
    def build():
        t = MerkleTree(DOMAIN)
        for i in range(8):
            t.append(f"item-{i}".encode())
        return t.root()

    assert build() == build()


# ---------------------------------------------------------------------------
# Inclusion proofs
# ---------------------------------------------------------------------------


@pytest.mark.merkle_vector
def test_proof_verify_all_leaves_four_tree():
    tree = MerkleTree(DOMAIN)
    leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(4)]
    root = tree.root()

    for i in range(4):
        proof = tree.proof(i)
        assert MerkleTree.verify(root, leaf_hashes[i], proof), (
            f"Proof failed for leaf {i}"
        )


@pytest.mark.merkle_vector
def test_proof_verify_all_leaves_eight_tree():
    tree = MerkleTree(DOMAIN)
    leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(8)]
    root = tree.root()

    for i in range(8):
        proof = tree.proof(i)
        assert MerkleTree.verify(root, leaf_hashes[i], proof), (
            f"Proof failed for leaf {i}"
        )


@pytest.mark.merkle_vector
def test_proof_wrong_leaf_fails():
    tree = MerkleTree(DOMAIN)
    leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(4)]
    root = tree.root()

    proof = tree.proof(0)
    # Use the wrong leaf hash
    assert not MerkleTree.verify(root, leaf_hashes[1], proof)


@pytest.mark.merkle_vector
def test_proof_wrong_root_fails():
    tree = MerkleTree(DOMAIN)
    leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(4)]

    proof = tree.proof(0)
    wrong_root = b"\xff" * 32
    assert not MerkleTree.verify(wrong_root, leaf_hashes[0], proof)


# ---------------------------------------------------------------------------
# MerkleProof serialization round-trip
# ---------------------------------------------------------------------------


@pytest.mark.merkle_vector
def test_proof_round_trip_dict():
    tree = MerkleTree(DOMAIN)
    leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(4)]
    root = tree.root()

    original = tree.proof(2)
    restored = MerkleProof.from_dict(original.to_dict())

    assert MerkleTree.verify(root, leaf_hashes[2], restored)
    assert restored.leaf_index == original.leaf_index
    assert restored.tree_size == original.tree_size


# ---------------------------------------------------------------------------
# ACR-pattern: 8-leaf tree (the real SC-001 ACR has 8 artifact leaves)
# ---------------------------------------------------------------------------


@pytest.mark.merkle_vector
def test_acr_eight_artifact_tree():
    """Simulate the 8-artifact ACR Merkle tree from the SC-001 spec."""
    artifacts = [
        ("zoiko/v1/source-record", b"source-record-hash"),
        ("zoiko/v1/validation-result", b"validation-result-hash"),
        ("zoiko/v1/canonical-invoice", b"canonical-invoice-hash"),
        ("zoiko/v1/finding", b"finding-hash"),
        ("zoiko/v1/decision-proposal", b"decision-proposal-hash"),
        ("zoiko/v1/governance-decision", b"governance-decision-hash"),
        ("zoiko/v1/governance-token", b"governance-token-hash"),
        ("zoiko/v1/outcome", b"outcome-hash"),
    ]

    # Build tree using each artifact's domain-tagged leaf hash
    tree = MerkleTree("zoiko/v1/acr")
    leaf_hashes = []
    for domain, data in artifacts:
        # In production: data is the SHA-256 of the artifact's canonical bytes
        artifact_hash = hashlib.sha256(data).digest()
        leaf_hash = tree.append(artifact_hash)
        leaf_hashes.append(leaf_hash)

    root = tree.root()
    assert len(root) == 32

    # Every artifact must have a valid inclusion proof
    for i, lh in enumerate(leaf_hashes):
        proof = tree.proof(i)
        assert MerkleTree.verify(root, lh, proof), f"ACR proof failed for artifact {i}"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_empty_tree_root_raises():
    with pytest.raises(ValueError, match="empty"):
        MerkleTree(DOMAIN).root()


def test_proof_out_of_range_raises():
    tree = MerkleTree(DOMAIN)
    tree.append(b"x")
    with pytest.raises(IndexError):
        tree.proof(5)

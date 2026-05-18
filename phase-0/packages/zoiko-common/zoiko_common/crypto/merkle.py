"""Domain-separated Merkle tree for Zoiko audit trail.

Leaf hash:     SHA-256(0x00 || domain_tag_bytes || leaf_data)
Internal hash: SHA-256(0x01 || left_hash || right_hash)

Domain separation prevents second-preimage attacks (RFC 6962 §2.1 pattern).
Domain tag format: b"zoiko/v1/<entity-type>"  e.g. b"zoiko/v1/source-record"

Usage:
    tree = MerkleTree("zoiko/v1/acr")
    tree.append(sha256_bytes_of_artifact_1)
    tree.append(sha256_bytes_of_artifact_2)
    root = tree.root()
    proof = tree.proof(0)
    assert MerkleTree.verify(root, sha256_bytes_of_artifact_1, proof, 0, len(tree))
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Sequence

# Prefix bytes for domain separation
_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"


def _sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.digest()


def hash_leaf(domain_tag: str, data: bytes) -> bytes:
    """Return domain-tagged leaf hash: SHA-256(0x00 || tag_bytes || data)."""
    return _sha256(_LEAF_PREFIX, domain_tag.encode("utf-8"), data)


def hash_internal(left: bytes, right: bytes) -> bytes:
    """Return internal node hash: SHA-256(0x01 || left || right)."""
    return _sha256(_NODE_PREFIX, left, right)


@dataclass
class MerkleProof:
    """Inclusion proof for a single leaf."""

    leaf_index: int
    tree_size: int
    # Each entry: (sibling_hash, side) where side=True means sibling is on the right
    path: list[tuple[bytes, bool]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "leaf_index": self.leaf_index,
            "tree_size": self.tree_size,
            "path": [
                {"hash": h.hex(), "right_sibling": right} for h, right in self.path
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MerkleProof":
        return cls(
            leaf_index=d["leaf_index"],
            tree_size=d["tree_size"],
            path=[(bytes.fromhex(e["hash"]), e["right_sibling"]) for e in d["path"]],
        )


class MerkleTree:
    """Append-only Merkle tree with domain separation.

    *domain_tag* is baked into every leaf hash so trees of different entity
    types cannot be confused even if they contain identical raw data.
    """

    def __init__(self, domain_tag: str) -> None:
        self._domain_tag = domain_tag
        self._leaves: list[bytes] = []

    def append(self, data: bytes) -> bytes:
        """Append *data*, return its leaf hash."""
        leaf_hash = hash_leaf(self._domain_tag, data)
        self._leaves.append(leaf_hash)
        return leaf_hash

    def __len__(self) -> int:
        return len(self._leaves)

    def root(self) -> bytes:
        """Return the current Merkle root.  Raises if tree is empty."""
        if not self._leaves:
            raise ValueError("MerkleTree: cannot compute root of empty tree")
        return _compute_root(self._leaves)

    def proof(self, index: int) -> MerkleProof:
        """Return an inclusion proof for the leaf at *index*."""
        n = len(self._leaves)
        if not 0 <= index < n:
            raise IndexError(f"MerkleTree: index {index} out of range [0, {n})")
        path = _build_proof(self._leaves, index)
        return MerkleProof(leaf_index=index, tree_size=n, path=path)

    @staticmethod
    def verify(
        root: bytes,
        leaf_hash: bytes,
        proof: MerkleProof,
    ) -> bool:
        """Return True iff *proof* demonstrates *leaf_hash* is at *proof.leaf_index*
        in a tree of size *proof.tree_size* with root *root*.
        """
        current = leaf_hash
        idx = proof.leaf_index
        for sibling, right_sibling in proof.path:
            if right_sibling:
                current = hash_internal(current, sibling)
            else:
                current = hash_internal(sibling, current)
            idx >>= 1
        return current == root


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_root(leaves: Sequence[bytes]) -> bytes:
    nodes = list(leaves)
    while len(nodes) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            # If odd number of nodes, promote the last one without hashing
            right = nodes[i + 1] if i + 1 < len(nodes) else left
            next_level.append(hash_internal(left, right))
        nodes = next_level
    return nodes[0]


def _build_proof(leaves: Sequence[bytes], index: int) -> list[tuple[bytes, bool]]:
    path: list[tuple[bytes, bool]] = []
    nodes = list(leaves)
    idx = index
    while len(nodes) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else left
            if i == idx - (idx % 2):
                sibling_idx = i + 1 if idx % 2 == 0 else i
                if sibling_idx < len(nodes):
                    sibling = nodes[sibling_idx]
                else:
                    sibling = left  # duplicate promotion
                right_sibling = idx % 2 == 0
                path.append((sibling, right_sibling))
            next_level.append(hash_internal(left, right))
        nodes = next_level
        idx >>= 1
    return path

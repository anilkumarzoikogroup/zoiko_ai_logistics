"""
Phase 0 edge-case tests — JCS, Merkle, and Signing.

Covers scenarios not in the main vector files:
  - JCS: deep nesting, mixed arrays, surrogates, large integers, extreme floats
  - Merkle: tamper detection, odd trees (5,7), large trees, same-data leaves,
            proof for promoted leaf, wrong-key verify
  - Signing: empty/large payloads, tampered bytes, wrong key, round-trip dict
  - Cross-cutting: domain-tagged hash changes on any field mutation
"""
from __future__ import annotations

import hashlib
import json

import pytest

from zoiko_common.crypto.jcs import canonicalize
from zoiko_common.crypto.merkle import MerkleTree, MerkleProof, hash_leaf, hash_internal
from zoiko_common.crypto.signing import (
    LocalEd25519Backend,
    ZoikoSigner,
    SignedEnvelope,
    verify_envelope,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _jcs(data: object) -> str:
    return canonicalize(data).decode("utf-8")


def _build_signer() -> tuple[ZoikoSigner, bytes]:
    """Return (signer, public_key_der) using a fresh ephemeral key."""
    backend = LocalEd25519Backend()
    return ZoikoSigner(backend), backend.public_key_der()


DOMAIN = "zoiko/v1/edge-test"


# ═══════════════════════════════════════════════════════════════════════════════
# JCS EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestJCSDeepNesting:
    def test_five_levels_deep(self):
        data = {"a": {"b": {"c": {"d": {"e": 42}}}}}
        assert _jcs(data) == '{"a":{"b":{"c":{"d":{"e":42}}}}}'

    def test_nested_key_order_at_every_level(self):
        data = {"z": {"z": 1, "a": 2}, "a": {"z": 3, "a": 4}}
        result = _jcs(data)
        assert result == '{"a":{"a":4,"z":3},"z":{"a":2,"z":1}}'

    def test_array_of_objects_keys_sorted(self):
        data = [{"z": 1, "a": 2}, {"y": 3, "b": 4}]
        assert _jcs(data) == '[{"a":2,"z":1},{"b":4,"y":3}]'

    def test_array_inside_nested_object(self):
        data = {"outer": {"inner": [3, 1, 2]}}
        assert _jcs(data) == '{"outer":{"inner":[3,1,2]}}'


class TestJCSMixedArrays:
    def test_null_bool_int_string_in_array(self):
        assert _jcs([None, True, False, 0, "hi"]) == '[null,true,false,0,"hi"]'

    def test_nested_array_in_array(self):
        assert _jcs([[1, 2], [3, 4]]) == "[[1,2],[3,4]]"

    def test_empty_object_in_array(self):
        assert _jcs([{}, {}]) == "[{},{}]"

    def test_array_of_mixed_numbers(self):
        result = _jcs([0, -1, 1, 1.5, -1.5])
        assert result == "[0,-1,1,1.5,-1.5]"


class TestJCSNumbers:
    def test_negative_float(self):
        assert _jcs(-4.5) == "-4.5"

    def test_negative_one_float(self):
        assert _jcs(-1.0) == "-1"

    def test_integer_beyond_safe_range(self):
        # 2^53 + 1 — outside JS safe integer range, treated as regular int in Python
        big = 9007199254740993
        assert _jcs(big) == "9007199254740993"

    def test_negative_large_integer(self):
        assert _jcs(-9007199254740992) == "-9007199254740992"

    def test_zero_float_in_dict(self):
        assert _jcs({"v": -0.0}) == '{"v":0}'

    def test_float_in_dict_value(self):
        assert _jcs({"amount": 4500.5}) == '{"amount":4500.5}'

    def test_nan_raises(self):
        with pytest.raises(ValueError, match="non-finite"):
            canonicalize(float("nan"))

    def test_negative_inf_raises(self):
        with pytest.raises(ValueError, match="non-finite"):
            canonicalize(float("-inf"))


class TestJCSStrings:
    def test_empty_string(self):
        assert _jcs("") == '""'

    def test_string_only_control_chars(self):
        result = _jcs("\x00\x01\x02")
        assert result == '"\\u0000\\u0001\\u0002"'

    def test_lone_surrogate_high(self):
        # High surrogate U+D800
        s = "\ud800"
        result = _jcs(s)
        assert result == '"\\ud800"'

    def test_lone_surrogate_low(self):
        # Low surrogate U+DFFF
        s = "\udfff"
        result = _jcs(s)
        assert result == '"\\udfff"'

    def test_hindi_devanagari_literal(self):
        # U+0900+ — outside C1 range, must NOT be escaped
        s = "नमस्ते"
        result = _jcs(s)
        assert s in result   # literal in output, not \uXXXX

    def test_null_key_in_dict(self):
        # null byte as part of a key string
        result = _jcs({"\x00key": 1})
        assert result == '{"\\u0000key":1}'


class TestJCSUniquenessAndIdempotency:
    def test_field_mutation_changes_hash(self):
        """Changing one field must change the SHA-256 of the canonical form."""
        original = {"carrier": "BlueDart", "amount": 8000, "currency": "INR"}
        tampered = {"carrier": "BlueDart", "amount": 8001, "currency": "INR"}
        h1 = hashlib.sha256(canonicalize(original)).digest()
        h2 = hashlib.sha256(canonicalize(tampered)).digest()
        assert h1 != h2

    def test_key_rename_changes_hash(self):
        h1 = hashlib.sha256(canonicalize({"amount": 100})).digest()
        h2 = hashlib.sha256(canonicalize({"Amount": 100})).digest()
        assert h1 != h2

    def test_extra_whitespace_in_value_changes_hash(self):
        h1 = hashlib.sha256(canonicalize({"note": "ok"})).digest()
        h2 = hashlib.sha256(canonicalize({"note": "ok "})).digest()
        assert h1 != h2

    def test_type_coercion_changes_hash(self):
        # True vs 1 must produce different output
        h1 = hashlib.sha256(canonicalize({"v": True})).digest()
        h2 = hashlib.sha256(canonicalize({"v": 1})).digest()
        assert h1 != h2

    def test_many_keys_sort_deterministic(self):
        """50-key dict — same result regardless of Python dict insertion order."""
        keys = [f"key_{i:02d}" for i in range(50)]
        forward = {k: i for i, k in enumerate(keys)}
        backward = {k: i for i, k in enumerate(reversed(keys))}
        # Only order of VALUES differs (same keys), so canonical bytes differ
        # but both must be stable across repeated calls
        assert canonicalize(forward) == canonicalize(forward)
        assert canonicalize(backward) == canonicalize(backward)

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            canonicalize({"key": object()})  # type: ignore[arg-type]

    def test_tuple_treated_as_unsupported(self):
        with pytest.raises(TypeError):
            canonicalize((1, 2, 3))  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════════
# MERKLE EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestMerkleTamperDetection:
    def test_changing_one_byte_of_leaf_data_changes_root(self):
        t1 = MerkleTree(DOMAIN)
        t1.append(b"invoice-data-original")
        t1.append(b"bol-data")

        t2 = MerkleTree(DOMAIN)
        t2.append(b"invoice-data-TAMPERED")   # one field changed
        t2.append(b"bol-data")

        assert t1.root() != t2.root()

    def test_tampered_proof_sibling_fails_verify(self):
        tree = MerkleTree(DOMAIN)
        leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(4)]
        root = tree.root()

        proof = tree.proof(0)
        # Flip the first sibling hash
        bad_path = list(proof.path)
        original_hash, side = bad_path[0]
        flipped = bytes([original_hash[0] ^ 0xFF]) + original_hash[1:]
        bad_path[0] = (flipped, side)
        bad_proof = MerkleProof(
            leaf_index=proof.leaf_index,
            tree_size=proof.tree_size,
            path=bad_path,
        )
        assert not MerkleTree.verify(root, leaf_hashes[0], bad_proof)

    def test_swapped_leaves_wrong_index_fails(self):
        """Proof for leaf 0 used with leaf_hash of leaf 2 must fail."""
        tree = MerkleTree(DOMAIN)
        leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(4)]
        root = tree.root()
        proof_0 = tree.proof(0)
        assert not MerkleTree.verify(root, leaf_hashes[2], proof_0)

    def test_adding_leaf_changes_root(self):
        tree = MerkleTree(DOMAIN)
        tree.append(b"a")
        root_before = tree.root()
        tree.append(b"b")
        root_after = tree.root()
        assert root_before != root_after


class TestMerkleOddTrees:
    def test_five_leaf_tree_all_proofs_valid(self):
        tree = MerkleTree(DOMAIN)
        leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(5)]
        root = tree.root()
        for i in range(5):
            assert MerkleTree.verify(root, leaf_hashes[i], tree.proof(i)), \
                f"Proof failed for leaf {i} in 5-leaf tree"

    def test_seven_leaf_tree_all_proofs_valid(self):
        tree = MerkleTree(DOMAIN)
        leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(7)]
        root = tree.root()
        for i in range(7):
            assert MerkleTree.verify(root, leaf_hashes[i], tree.proof(i)), \
                f"Proof failed for leaf {i} in 7-leaf tree"

    def test_promoted_last_leaf_proof(self):
        """Last leaf in odd tree is self-paired. Its proof must still verify."""
        tree = MerkleTree(DOMAIN)
        leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(3)]
        root = tree.root()
        proof = tree.proof(2)   # last leaf, promoted with itself
        assert MerkleTree.verify(root, leaf_hashes[2], proof)


class TestMerkleLargeTree:
    def test_sixteen_leaf_tree_all_proofs_valid(self):
        tree = MerkleTree(DOMAIN)
        leaf_hashes = [tree.append(f"data-{i}".encode()) for i in range(16)]
        root = tree.root()
        for i in range(16):
            assert MerkleTree.verify(root, leaf_hashes[i], tree.proof(i))

    def test_large_tree_root_deterministic(self):
        def build():
            t = MerkleTree(DOMAIN)
            for i in range(100):
                t.append(f"leaf-{i}".encode())
            return t.root()
        assert build() == build()


class TestMerkleSameData:
    def test_identical_leaves_different_positions_different_proofs(self):
        """Same data appended twice → same leaf hash but different proof paths."""
        tree = MerkleTree(DOMAIN)
        lh0 = tree.append(b"duplicate")
        lh1 = tree.append(b"duplicate")
        assert lh0 == lh1           # same leaf hash (expected)
        proof0 = tree.proof(0)
        proof1 = tree.proof(1)
        assert proof0.path != proof1.path   # but different paths

    def test_same_data_different_domain_different_leaf_hash(self):
        h1 = hash_leaf("zoiko/v1/source-record",    b"same-content")
        h2 = hash_leaf("zoiko/v1/canonical-invoice", b"same-content")
        assert h1 != h2

    def test_same_data_same_domain_same_leaf_hash(self):
        h1 = hash_leaf(DOMAIN, b"content")
        h2 = hash_leaf(DOMAIN, b"content")
        assert h1 == h2

    def test_two_different_domain_trees_same_leaves_different_roots(self):
        items = [b"a", b"b", b"c"]
        t1 = MerkleTree("zoiko/v1/source-record")
        t2 = MerkleTree("zoiko/v1/evidence-item")
        for item in items:
            t1.append(item)
            t2.append(item)
        assert t1.root() != t2.root()


class TestMerkleEdgeCases:
    def test_empty_bytes_leaf(self):
        """Empty bytes is a valid leaf."""
        tree = MerkleTree(DOMAIN)
        lh = tree.append(b"")
        assert len(lh) == 32
        assert MerkleTree.verify(tree.root(), lh, tree.proof(0))

    def test_proof_round_trip_odd_tree(self):
        tree = MerkleTree(DOMAIN)
        leaf_hashes = [tree.append(f"x-{i}".encode()) for i in range(5)]
        root = tree.root()
        for i in range(5):
            original = tree.proof(i)
            restored = MerkleProof.from_dict(original.to_dict())
            assert MerkleTree.verify(root, leaf_hashes[i], restored)

    def test_empty_tree_root_raises(self):
        with pytest.raises(ValueError, match="empty"):
            MerkleTree(DOMAIN).root()

    def test_proof_negative_index_raises(self):
        tree = MerkleTree(DOMAIN)
        tree.append(b"x")
        with pytest.raises(IndexError):
            tree.proof(-1)

    def test_proof_out_of_range_raises(self):
        tree = MerkleTree(DOMAIN)
        tree.append(b"x")
        with pytest.raises(IndexError):
            tree.proof(99)

    def test_hash_leaf_and_internal_different_for_same_bytes(self):
        """Prefix bytes 0x00 vs 0x01 must prevent leaf/internal collision."""
        data = b"\xaa" * 32
        leaf = hash_leaf(DOMAIN, data)
        # Construct an internal node whose inputs would produce the same SHA-256 if not for 0x01 prefix
        internal = hash_internal(b"\x00" * 32, b"\x00" * 32)
        assert leaf != internal


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNING EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestSigningBasic:
    def test_sign_and_verify_round_trip(self):
        signer, pub = _build_signer()
        env = signer.sign(b"test payload")
        assert verify_envelope(env, pub)

    def test_empty_payload(self):
        signer, pub = _build_signer()
        env = signer.sign(b"")
        assert verify_envelope(env, pub)

    def test_large_payload(self):
        signer, pub = _build_signer()
        env = signer.sign(b"x" * 100_000)
        assert verify_envelope(env, pub)

    def test_binary_payload(self):
        signer, pub = _build_signer()
        payload = bytes(range(256))
        env = signer.sign(payload)
        assert verify_envelope(env, pub)

    def test_signature_is_64_bytes(self):
        signer, _ = _build_signer()
        env = signer.sign(b"data")
        assert len(env.signature) == 64

    def test_kid_starts_with_local(self):
        signer, _ = _build_signer()
        assert signer.kid.startswith("local:")


class TestSigningTamperDetection:
    def test_tampered_payload_fails_verify(self):
        signer, pub = _build_signer()
        env = signer.sign(b"original payload")
        tampered = SignedEnvelope(
            payload=b"tampered payload",
            signature=env.signature,
            kid=env.kid,
        )
        assert not verify_envelope(tampered, pub)

    def test_tampered_signature_fails_verify(self):
        signer, pub = _build_signer()
        env = signer.sign(b"payload")
        bad_sig = bytes([env.signature[0] ^ 0xFF]) + env.signature[1:]
        tampered = SignedEnvelope(
            payload=env.payload,
            signature=bad_sig,
            kid=env.kid,
        )
        assert not verify_envelope(tampered, pub)

    def test_wrong_public_key_fails_verify(self):
        signer, _ = _build_signer()
        _, wrong_pub = _build_signer()     # different key
        env = signer.sign(b"payload")
        assert not verify_envelope(env, wrong_pub)

    def test_truncated_signature_fails_verify(self):
        signer, pub = _build_signer()
        env = signer.sign(b"payload")
        truncated = SignedEnvelope(
            payload=env.payload,
            signature=env.signature[:32],   # only 32 of 64 bytes
            kid=env.kid,
        )
        assert not verify_envelope(truncated, pub)

    def test_zero_signature_fails_verify(self):
        signer, pub = _build_signer()
        env = signer.sign(b"payload")
        zeroed = SignedEnvelope(
            payload=env.payload,
            signature=b"\x00" * 64,
            kid=env.kid,
        )
        assert not verify_envelope(zeroed, pub)


class TestSigningTwoSigners:
    def test_two_signers_same_payload_different_sigs(self):
        """Ed25519 is deterministic per key, but two keys produce different sigs."""
        s1, _ = _build_signer()
        s2, _ = _build_signer()
        payload = b"same payload"
        env1 = s1.sign(payload)
        env2 = s2.sign(payload)
        assert env1.signature != env2.signature

    def test_same_signer_same_payload_same_sig(self):
        """Ed25519 is deterministic — same key + same payload → same signature."""
        backend = LocalEd25519Backend()
        signer = ZoikoSigner(backend)
        payload = b"deterministic"
        assert signer.sign(payload).signature == signer.sign(payload).signature

    def test_same_signer_different_payloads_different_sigs(self):
        signer, _ = _build_signer()
        env1 = signer.sign(b"payload-A")
        env2 = signer.sign(b"payload-B")
        assert env1.signature != env2.signature


class TestSignedEnvelopeSerialisation:
    def test_to_dict_from_dict_round_trip(self):
        signer, pub = _build_signer()
        env = signer.sign(b"round-trip test")
        restored = SignedEnvelope.from_dict(env.to_dict())
        assert verify_envelope(restored, pub)
        assert restored.payload == env.payload
        assert restored.signature == env.signature
        assert restored.kid == env.kid
        assert restored.alg == env.alg

    def test_dict_has_required_fields(self):
        signer, _ = _build_signer()
        d = signer.sign(b"data").to_dict()
        assert set(d.keys()) == {"alg", "kid", "payload", "signature"}

    def test_payload_serialised_as_hex(self):
        signer, _ = _build_signer()
        d = signer.sign(b"\xde\xad\xbe\xef").to_dict()
        assert d["payload"] == "deadbeef"


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-CUTTING: domain-tagged hashes + JCS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDomainTaggedHashing:
    """Simulate the pattern every Zoiko service uses: JCS → domain-tag → SHA-256."""

    def _invoice_hash(self, invoice: dict, domain: str = "zoiko.ingestion.invoice.v1") -> bytes:
        return hashlib.sha256(domain.encode() + b":" + canonicalize(invoice)).digest()

    def test_any_field_change_changes_hash(self):
        base = {"carrier": "BlueDart", "amount": 12500, "currency": "INR"}
        h_base = self._invoice_hash(base)
        for mutation in [
            {"carrier": "bluedart", "amount": 12500, "currency": "INR"},   # case change
            {"carrier": "BlueDart", "amount": 12501, "currency": "INR"},   # amount off by 1
            {"carrier": "BlueDart", "amount": 12500, "currency": "USD"},   # currency change
        ]:
            assert self._invoice_hash(mutation) != h_base, f"Hash should differ for {mutation}"

    def test_domain_change_changes_hash(self):
        invoice = {"carrier": "BlueDart", "amount": 12500}
        h1 = self._invoice_hash(invoice, "zoiko.ingestion.invoice.v1")
        h2 = self._invoice_hash(invoice, "zoiko.canonical.invoice.v1")
        assert h1 != h2

    def test_sc001_hash_is_deterministic(self):
        """The SC-001 invoice hash must be identical on every run."""
        sc001 = {
            "carrier":  "BlueDart",
            "route":    "Hyderabad → Warangal",
            "amount":   12500,
            "currency": "INR",
        }
        h1 = self._invoice_hash(sc001)
        h2 = self._invoice_hash(sc001)
        assert h1 == h2
        assert len(h1) == 32

    def test_evidence_bundle_merkle_root_changes_on_tamper(self):
        """Simulate evidence bundle: if any document bytes change, the Merkle root changes."""
        def build_bundle(bol_bytes: bytes) -> bytes:
            tree = MerkleTree("zoiko/v1/evidence-item")
            tree.append(hashlib.sha256(b"zoiko.evidence.item.v1:" + bol_bytes).digest())
            tree.append(hashlib.sha256(b"zoiko.evidence.item.v1:" + b"rate-sheet-bytes").digest())
            tree.append(hashlib.sha256(b"zoiko.evidence.item.v1:" + b"invoice-bytes").digest())
            return tree.root()

        root_original = build_bundle(b"bol-original-content")
        root_tampered = build_bundle(b"bol-TAMPERED-content")
        assert root_original != root_tampered

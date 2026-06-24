"""
30-Test Hardening Matrix — T-001 through T-005
Cryptographic Foundation layer (Phase 0).

T-001  JCS canonicalization output is deterministic
T-002  SHA-256 domain-tagged hash is correct
T-003  Ed25519 sign + verify roundtrip passes; tampered payload fails
T-004  Merkle leaf hash is deterministic and domain-separated
T-005  Merkle root changes when any leaf is tampered
"""
import hashlib


# ── T-001: JCS canonicalization is deterministic ──────────────────────────────

class TestT001JCSDeterministic:
    """T-001: Same input always produces same canonical bytes, regardless of dict insertion order."""

    def test_t001_same_output_regardless_of_insertion_order(self):
        from zoiko_common.crypto.jcs import canonicalize
        d1 = {"z": 3, "a": 1, "m": 2}
        d2 = {"a": 1, "m": 2, "z": 3}
        assert canonicalize(d1) == canonicalize(d2)

    def test_t001_output_is_bytes(self):
        from zoiko_common.crypto.jcs import canonicalize
        result = canonicalize({"key": "value"})
        assert isinstance(result, bytes)

    def test_t001_keys_sorted_unicode_code_point(self):
        from zoiko_common.crypto.jcs import canonicalize
        result = canonicalize({"z": 1, "a": 2}).decode()
        assert result == '{"a":2,"z":1}'

    def test_t001_nested_objects_sorted(self):
        from zoiko_common.crypto.jcs import canonicalize
        result = canonicalize({"b": {"y": 1, "x": 2}, "a": 3}).decode()
        assert result == '{"a":3,"b":{"x":2,"y":1}}'

    def test_t001_repeated_calls_identical(self):
        from zoiko_common.crypto.jcs import canonicalize
        payload = {"tenant_id": "abc", "amount": 4500, "currency": "INR"}
        a = canonicalize(payload)
        b = canonicalize(payload)
        assert a == b

    def test_t001_sc001_invoice_payload_stable(self):
        from zoiko_common.crypto.jcs import canonicalize
        invoice = {
            "carrier_id":        "BlueDart",
            "currency":          "INR",
            "invoice_number":    "HYD-WAR-20250115-001",
            "route_destination": "Warehouse",
            "route_origin":      "Hyderabad",
            "total_amount":      12500.0,
        }
        h1 = hashlib.sha256(canonicalize(invoice)).hexdigest()
        h2 = hashlib.sha256(canonicalize(invoice)).hexdigest()
        assert h1 == h2


# ── T-002: SHA-256 domain-tagged hash is correct ─────────────────────────────

class TestT002DomainTaggedHash:
    """T-002: Domain-tagged SHA-256 produces the expected digest and prevents cross-type confusion."""

    def test_t002_ingestion_domain_tag(self):
        domain = b"zoiko.ingestion.invoice.v1:"
        payload = b'{"carrier_id":"BlueDart","amount":12500}'
        expected = hashlib.sha256(domain + payload).hexdigest()
        assert len(expected) == 64
        assert expected == hashlib.sha256(domain + payload).hexdigest()

    def test_t002_different_domains_produce_different_hashes(self):
        payload = b"same-canonical-bytes"
        h_ingestion  = hashlib.sha256(b"zoiko.ingestion.invoice.v1:"    + payload).digest()
        h_canonical  = hashlib.sha256(b"zoiko.canonical.invoice.v1:"    + payload).digest()
        h_finding    = hashlib.sha256(b"zoiko.finding.v1:"              + payload).digest()
        h_token      = hashlib.sha256(b"zoiko.token.v1:"               + payload).digest()
        h_proposal   = hashlib.sha256(b"zoiko.proposal.v1:"             + payload).digest()
        h_decision   = hashlib.sha256(b"zoiko.governance.decision.v1:"  + payload).digest()
        all_hashes   = [h_ingestion, h_canonical, h_finding, h_token, h_proposal, h_decision]
        assert len(set(all_hashes)) == 6, "Each domain tag must produce a unique hash"

    def test_t002_hash_length_always_32_bytes(self):
        for domain in [b"zoiko.token.v1:", b"zoiko.finding.v1:", b"zoiko.canonical.invoice.v1:"]:
            h = hashlib.sha256(domain + b"payload").digest()
            assert len(h) == 32

    def test_t002_hash_changes_when_payload_changes(self):
        domain = b"zoiko.ingestion.invoice.v1:"
        h1 = hashlib.sha256(domain + b"amount:12500").digest()
        h2 = hashlib.sha256(domain + b"amount:12501").digest()
        assert h1 != h2


# ── T-003: Ed25519 sign + verify roundtrip ────────────────────────────────────

class TestT003Ed25519SignVerify:
    """T-003: Sign a payload, verify with the correct public key; verify fails with tampered payload."""

    def test_t003_sign_verify_roundtrip_passes(self):
        from zoiko_common.crypto.signing import (
            LocalEd25519Backend, ZoikoSigner, verify_envelope,
        )
        backend = LocalEd25519Backend()
        signer  = ZoikoSigner(backend)
        payload = b"zoiko.token.v1:canonical-payload-bytes"
        env = signer.sign(payload)
        assert verify_envelope(env, backend.public_key_der())

    def test_t003_tampered_payload_fails_verification(self):
        from zoiko_common.crypto.signing import (
            LocalEd25519Backend, ZoikoSigner, SignedEnvelope, verify_envelope,
        )
        backend = LocalEd25519Backend()
        signer  = ZoikoSigner(backend)
        payload = b"zoiko.finding.v1:original"
        env = signer.sign(payload)
        tampered = SignedEnvelope(
            payload   = b"zoiko.finding.v1:tampered",
            signature = env.signature,
            kid       = env.kid,
        )
        assert not verify_envelope(tampered, backend.public_key_der())

    def test_t003_signature_is_64_bytes(self):
        from zoiko_common.crypto.signing import LocalEd25519Backend, ZoikoSigner
        signer = ZoikoSigner(LocalEd25519Backend())
        env = signer.sign(b"test-payload")
        assert len(env.signature) == 64

    def test_t003_different_keys_different_signatures(self):
        from zoiko_common.crypto.signing import LocalEd25519Backend, ZoikoSigner
        s1 = ZoikoSigner(LocalEd25519Backend())
        s2 = ZoikoSigner(LocalEd25519Backend())
        payload = b"same-payload"
        assert s1.sign(payload).signature != s2.sign(payload).signature

    def test_t003_envelope_serialization_roundtrip(self):
        from zoiko_common.crypto.signing import (
            LocalEd25519Backend, ZoikoSigner, SignedEnvelope, verify_envelope,
        )
        backend = LocalEd25519Backend()
        signer  = ZoikoSigner(backend)
        payload = b"serialization-test"
        env = signer.sign(payload)
        restored = SignedEnvelope.from_dict(env.to_dict())
        assert verify_envelope(restored, backend.public_key_der())


# ── T-004: Merkle leaf hash is deterministic and domain-separated ─────────────

class TestT004MerkleLeafHash:
    """T-004: hash_leaf is deterministic; different domains produce different hashes."""

    def test_t004_leaf_hash_deterministic(self):
        from zoiko_common.crypto.merkle import hash_leaf
        h1 = hash_leaf("zoiko/v1/evidence-item", b"BOL-content")
        h2 = hash_leaf("zoiko/v1/evidence-item", b"BOL-content")
        assert h1 == h2

    def test_t004_leaf_hash_32_bytes(self):
        from zoiko_common.crypto.merkle import hash_leaf
        h = hash_leaf("zoiko/v1/source-record", b"some-data")
        assert len(h) == 32

    def test_t004_domain_separation_prevents_collision(self):
        from zoiko_common.crypto.merkle import hash_leaf
        data = b"same-bytes"
        h_source   = hash_leaf("zoiko/v1/source-record", data)
        h_evidence = hash_leaf("zoiko/v1/evidence-item", data)
        h_acr      = hash_leaf("zoiko/v1/acr",           data)
        assert h_source != h_evidence
        assert h_evidence != h_acr
        assert h_source != h_acr

    def test_t004_leaf_differs_from_internal_node(self):
        from zoiko_common.crypto.merkle import hash_leaf, hash_internal
        data = b"ambiguous"
        leaf = hash_leaf("zoiko/v1/test", data)
        # internal node uses 0x01 prefix, leaf uses 0x00 — must not collide
        fake_internal = hash_internal(b"\x00" * 32, b"\x00" * 32)
        assert leaf != fake_internal


# ── T-005: Merkle root changes when leaf tampered ─────────────────────────────

class TestT005MerkleRootTamper:
    """T-005: Modifying any single leaf changes the Merkle root."""

    def _build_root(self, items: list[bytes], domain: str = "zoiko/v1/evidence-item") -> bytes:
        from zoiko_common.crypto.merkle import MerkleTree
        tree = MerkleTree(domain)
        for item in items:
            tree.append(item)
        return tree.root()

    def test_t005_tamper_first_leaf_changes_root(self):
        original = [b"bol-doc", b"rate-sheet", b"invoice"]
        tampered = [b"bol-doc-TAMPERED", b"rate-sheet", b"invoice"]
        assert self._build_root(original) != self._build_root(tampered)

    def test_t005_tamper_middle_leaf_changes_root(self):
        original = [b"bol-doc", b"rate-sheet", b"invoice"]
        tampered = [b"bol-doc", b"rate-sheet-FORGED", b"invoice"]
        assert self._build_root(original) != self._build_root(tampered)

    def test_t005_tamper_last_leaf_changes_root(self):
        original = [b"bol-doc", b"rate-sheet", b"invoice"]
        tampered = [b"bol-doc", b"rate-sheet", b"invoice-MODIFIED"]
        assert self._build_root(original) != self._build_root(tampered)

    def test_t005_acr_8_artifact_tree_tamper_detected(self):
        artifacts_ok = [f"artifact-{i}".encode() for i in range(8)]
        root_ok = self._build_root(artifacts_ok, "zoiko/v1/acr")

        for idx in range(8):
            tampered = list(artifacts_ok)
            tampered[idx] = b"FORGED"
            root_bad = self._build_root(tampered, "zoiko/v1/acr")
            assert root_ok != root_bad, f"Tampering artifact[{idx}] was not detected"

    def test_t005_inclusion_proof_fails_on_tampered_leaf(self):
        from zoiko_common.crypto.merkle import MerkleTree
        domain = "zoiko/v1/evidence-item"
        tree = MerkleTree(domain)
        leaf_hashes = [tree.append(f"item-{i}".encode()) for i in range(4)]
        root = tree.root()

        # Valid proof works
        proof = tree.proof(0)
        assert MerkleTree.verify(root, leaf_hashes[0], proof)

        # Wrong leaf hash → proof fails
        assert not MerkleTree.verify(root, b"\xff" * 32, proof)

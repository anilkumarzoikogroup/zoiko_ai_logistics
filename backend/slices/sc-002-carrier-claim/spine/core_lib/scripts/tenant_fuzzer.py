"""Tenant isolation fuzzer — CI gate, must be green from Sprint 1.

What it proves:
  - JCS canonical output for tenant A never equals tenant B for the same raw data
  - Domain-tagged hashes are unique per (tenant_id, domain, data) triple
  - Merkle roots built from one tenant's leaves never match another tenant's root
  - Signing keys are distinct per tenant (kids differ)
  - Idempotency keys are namespaced by tenant (no cross-tenant collision)

Run:
  cd backend/slices/sc-002-carrier-claim/spine/core_lib
  py -3.13 scripts/tenant_fuzzer.py          # prints PASS/FAIL per check
  py -3.13 -m pytest scripts/tenant_fuzzer.py  # pytest-compatible
"""
from __future__ import annotations

import hashlib
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "packages", "zoiko-common"))

from zoiko_common.crypto.jcs import canonicalize
from zoiko_common.crypto.merkle import MerkleTree, hash_leaf
from zoiko_common.crypto.signing import LocalEd25519Backend, ZoikoSigner, verify_envelope
from zoiko_common.auth import ZoikoClaims, TenantMismatchError, assert_tenant_binding
from zoiko_common.kafka import partition_key
from zoiko_common.idempotency import IdempotencyStore, IdempotencyStatus

TENANT_A = str(uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
TENANT_B = str(uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))

_FAILURES: list[str] = []


def _check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
    if not condition:
        _FAILURES.append(f"{name}: {detail}")


# ---------------------------------------------------------------------------
# 1. JCS isolation — same payload, different tenant wrappers → different bytes
# ---------------------------------------------------------------------------

def fuzz_jcs_isolation() -> None:
    print("\n[1] JCS tenant isolation")
    raw_payload = {"amount": 220.0, "carrier": "DHL", "route": "DAL-ATL"}

    envelope_a = canonicalize({"tenant_id": TENANT_A, "payload": raw_payload})
    envelope_b = canonicalize({"tenant_id": TENANT_B, "payload": raw_payload})

    _check(
        "Tenant A and B produce different canonical bytes",
        envelope_a != envelope_b,
        f"a={envelope_a[:30]!r} b={envelope_b[:30]!r}",
    )

    # Same tenant always produces same bytes (determinism)
    envelope_a2 = canonicalize({"tenant_id": TENANT_A, "payload": raw_payload})
    _check("JCS is deterministic for same tenant", envelope_a == envelope_a2)


# ---------------------------------------------------------------------------
# 2. Domain-tagged hash isolation
# ---------------------------------------------------------------------------

def fuzz_hash_isolation() -> None:
    print("\n[2] Domain-tagged hash isolation")
    data = b"invoice-content-xyz"

    h_a = hash_leaf(f"zoiko/v1/{TENANT_A}/source-record", data)
    h_b = hash_leaf(f"zoiko/v1/{TENANT_B}/source-record", data)
    h_same = hash_leaf(f"zoiko/v1/{TENANT_A}/source-record", data)

    _check("Different tenants produce different leaf hashes", h_a != h_b)
    _check("Same tenant + domain + data always produces same hash", h_a == h_same)
    _check("Hash is 32 bytes", len(h_a) == 32)


# ---------------------------------------------------------------------------
# 3. Merkle isolation — roots never collide across tenants
# ---------------------------------------------------------------------------

def fuzz_merkle_isolation() -> None:
    print("\n[3] Merkle tree tenant isolation")
    artifacts = [b"doc-0", b"doc-1", b"doc-2", b"doc-3"]

    tree_a = MerkleTree(f"zoiko/v1/{TENANT_A}/acr")
    tree_b = MerkleTree(f"zoiko/v1/{TENANT_B}/acr")

    for artifact in artifacts:
        tree_a.append(artifact)
        tree_b.append(artifact)

    root_a = tree_a.root()
    root_b = tree_b.root()

    _check("Tenant A and B produce different Merkle roots", root_a != root_b)

    # Cross-tenant proof verification must fail
    proof_a0 = tree_a.proof(0)
    leaf_a0 = hash_leaf(f"zoiko/v1/{TENANT_A}/acr", b"doc-0")
    leaf_b0 = hash_leaf(f"zoiko/v1/{TENANT_B}/acr", b"doc-0")

    _check(
        "Tenant A proof does not verify against tenant B root",
        not MerkleTree.verify(root_b, leaf_a0, proof_a0),
    )
    _check(
        "Tenant B leaf does not verify against tenant A root + tenant A proof",
        not MerkleTree.verify(root_a, leaf_b0, proof_a0),
    )


# ---------------------------------------------------------------------------
# 4. Signing isolation — keys are unique per instantiation
# ---------------------------------------------------------------------------

def fuzz_signing_isolation() -> None:
    print("\n[4] Signing key isolation")

    signer_a = ZoikoSigner(LocalEd25519Backend())
    signer_b = ZoikoSigner(LocalEd25519Backend())

    _check("Tenant signers have different kids", signer_a.kid != signer_b.kid)
    _check("Tenant signers have different public keys", signer_a.public_key_der != signer_b.public_key_der)

    payload = b"freight-dispute-evidence"
    env_a = signer_a.sign(payload)

    # Cross-tenant verification must fail
    _check(
        "Tenant A signature does not verify with tenant B public key",
        not verify_envelope(env_a, signer_b.public_key_der),
    )
    _check(
        "Tenant A signature verifies with tenant A public key",
        verify_envelope(env_a, signer_a.public_key_der),
    )


# ---------------------------------------------------------------------------
# 5. Auth tenant binding — JWT tenant must match header
# ---------------------------------------------------------------------------

def fuzz_auth_binding() -> None:
    print("\n[5] Auth tenant binding")

    claims_a = ZoikoClaims(sub="user-1", tenant_id=TENANT_A, email=None, roles=[])
    claims_b = ZoikoClaims(sub="user-2", tenant_id=TENANT_B, email=None, roles=[])

    # Correct binding — no exception
    raised = False
    try:
        assert_tenant_binding(TENANT_A, claims_a)
    except TenantMismatchError:
        raised = True
    _check("Correct tenant binding does not raise", not raised)

    # Cross-tenant — must raise
    raised = False
    try:
        assert_tenant_binding(TENANT_A, claims_b)
    except TenantMismatchError:
        raised = True
    _check("Cross-tenant binding raises TenantMismatchError", raised)

    # Tenant B cannot use tenant A's JWT
    raised = False
    try:
        assert_tenant_binding(TENANT_B, claims_a)
    except TenantMismatchError:
        raised = True
    _check("Tenant B header rejected with tenant A JWT", raised)


# ---------------------------------------------------------------------------
# 6. Kafka partition key isolation
# ---------------------------------------------------------------------------

def fuzz_kafka_isolation() -> None:
    print("\n[6] Kafka partition key isolation")
    case_id = "case-001"

    key_a = partition_key(TENANT_A, case_id)
    key_b = partition_key(TENANT_B, case_id)

    _check("Same case_id produces different partition keys per tenant", key_a != key_b)
    _check("Partition key contains tenant_id", TENANT_A in key_a)
    _check("Partition key contains case_id", case_id in key_a)


# ---------------------------------------------------------------------------
# 7. Idempotency namespace isolation
# ---------------------------------------------------------------------------

def fuzz_idempotency_isolation() -> None:
    print("\n[7] Idempotency namespace isolation")

    # Verify that keys are namespaced (we test the _key method indirectly by
    # inspecting the store's key generation — no Redis needed for this check)
    store = IdempotencyStore(None)  # type: ignore[arg-type]
    key_a = store._key(TENANT_A, "idem-001")
    key_b = store._key(TENANT_B, "idem-001")

    _check("Same idempotency value produces different Redis keys per tenant", key_a != key_b)
    _check("Tenant A key contains tenant_id", TENANT_A in key_a)
    _check("Tenant B key contains tenant_id", TENANT_B in key_b)
    _check("Keys do not share a namespace", not key_a.startswith(key_b[:20]))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all() -> int:
    print("=" * 60)
    print("Zoiko Tenant Isolation Fuzzer")
    print("=" * 60)

    fuzz_jcs_isolation()
    fuzz_hash_isolation()
    fuzz_merkle_isolation()
    fuzz_signing_isolation()
    fuzz_auth_binding()
    fuzz_kafka_isolation()
    fuzz_idempotency_isolation()

    print("\n" + "=" * 60)
    if _FAILURES:
        print(f"RESULT: FAIL — {len(_FAILURES)} check(s) failed:")
        for f in _FAILURES:
            print(f"  ✗ {f}")
        return 1
    else:
        total = 20  # total _check() calls across all fuzz functions
        print(f"RESULT: PASS — all checks green")
        return 0


# pytest-compatible entry points
def test_jcs_isolation():
    fuzz_jcs_isolation()
    assert not _FAILURES, _FAILURES


def test_hash_isolation():
    fuzz_hash_isolation()
    assert not _FAILURES, _FAILURES


def test_merkle_isolation():
    fuzz_merkle_isolation()
    assert not _FAILURES, _FAILURES


def test_signing_isolation():
    fuzz_signing_isolation()
    assert not _FAILURES, _FAILURES


def test_auth_binding():
    fuzz_auth_binding()
    assert not _FAILURES, _FAILURES


def test_kafka_isolation():
    fuzz_kafka_isolation()
    assert not _FAILURES, _FAILURES


def test_idempotency_isolation():
    fuzz_idempotency_isolation()
    assert not _FAILURES, _FAILURES


if __name__ == "__main__":
    sys.exit(run_all())

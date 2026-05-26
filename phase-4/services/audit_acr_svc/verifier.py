"""
Offline ACR verifier (FR-013).

Accepts the JSON verify bundle produced by AuditACRHandler._build_verify_bundle()
and cryptographically proves:
  1. Each artifact hash is well-formed (64-char hex SHA-256).
  2. The Merkle root recomputed from artifact hashes matches the bundle's merkle_root.
  3. The ACR Ed25519 signature is valid over SHA-256(domain_tag + JCS(payload)).

Can be used:
  - In-process: VerifyResult = verify_bundle(bundle_dict)
  - HTTP:        POST /v1/verifier/acrs/verify
  - Shell:       python verifier.py acr.json
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


_DOMAIN_TAG = b"zoiko/v1/acr"


@dataclass
class VerifyResult:
    passed:            bool
    acr_id:            str
    case_id:           str
    merkle_root_match: bool
    signature_valid:   bool
    artifact_count:    int
    errors:            list[str] = field(default_factory=list)


def verify_bundle(bundle: dict) -> VerifyResult:
    """
    Verify an ACR verify bundle offline.

    bundle must have: acr_id, case_id, merkle_root, artifacts, public_keys,
                      acr_signature, acr_kid, issued_at.
    """
    errors: list[str] = []

    acr_id   = bundle.get("acr_id", "")
    case_id  = bundle.get("case_id", "")
    artifacts= bundle.get("artifacts", [])

    # ── Step 1: artifact hashes well-formed ────────────────────────────────────
    for a in artifacts:
        h = a.get("hash", "")
        if len(h) != 64:
            errors.append(f"Artifact '{a.get('name')}' has malformed hash (len={len(h)})")

    # ── Step 2: recompute Merkle root ──────────────────────────────────────────
    merkle_root_match = False
    try:
        import paths  # noqa: F401
        from zoiko_common.crypto.merkle import MerkleTree
        tree = MerkleTree(_DOMAIN_TAG.decode())
        for a in artifacts:
            tree.append(bytes.fromhex(a["hash"]))
        computed_root = tree.root().hex()
        expected_root = bundle.get("merkle_root", "")
        if computed_root == expected_root:
            merkle_root_match = True
        else:
            errors.append(f"Merkle root mismatch: computed={computed_root}, expected={expected_root}")
    except Exception as e:
        errors.append(f"Merkle verification error: {e}")

    # ── Step 3: verify Ed25519 signature ───────────────────────────────────────
    signature_valid = False
    try:
        from zoiko_common.crypto.jcs import canonicalize as _jcs
        payload_dict = {
            "artifacts":   [{"name": a["name"], "hash": a["hash"]} for a in artifacts],
            "case_id":     case_id,
            "merkle_root": bundle.get("merkle_root", ""),
            "tenant_id":   bundle.get("tenant_id", ""),
        }
        acr_payload = _jcs(payload_dict)
        acr_hash    = hashlib.sha256(_DOMAIN_TAG + acr_payload).digest()
        sig_hex     = bundle.get("acr_signature", "")
        kid         = bundle.get("acr_kid", "")
        pub_keys    = bundle.get("public_keys", {})

        if sig_hex and kid and kid in pub_keys:
            sig     = bytes.fromhex(sig_hex)
            pub_b64 = pub_keys[kid]
            if pub_b64:
                import base64
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                from cryptography.hazmat.primitives.serialization import load_der_public_key
                pub_der = base64.b64decode(pub_b64)
                pub_key = load_der_public_key(pub_der)
                pub_key.verify(sig, acr_hash)
                signature_valid = True
            else:
                errors.append("No public key material in bundle — signature not verifiable")
        else:
            errors.append("Missing signature, kid, or public_keys in bundle")
    except Exception as e:
        errors.append(f"Signature verification failed: {e}")

    passed = merkle_root_match and signature_valid and len(errors) == 0

    return VerifyResult(
        passed=passed,
        acr_id=acr_id,
        case_id=case_id,
        merkle_root_match=merkle_root_match,
        signature_valid=signature_valid,
        artifact_count=len(artifacts),
        errors=errors,
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python verifier.py <acr.json>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        bundle = json.load(f)
    result = verify_bundle(bundle)
    print(json.dumps({
        "passed":            result.passed,
        "acr_id":            result.acr_id,
        "case_id":           result.case_id,
        "merkle_root_match": result.merkle_root_match,
        "signature_valid":   result.signature_valid,
        "artifact_count":    result.artifact_count,
        "errors":            result.errors,
    }, indent=2))
    sys.exit(0 if result.passed else 1)

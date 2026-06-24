"""SC-001 end-to-end demo: Dallas->Atlanta $220 overcharge.

Shows exactly what Phase 0 produces when it processes the SC-001 invoice:
  carrier charges $220  |  contract says $120  |  overcharge = $100

Run:
  cd backend/slices/sc-001-freight-invoice-overcharge/spine/core_lib
  py -3.13 scripts/demo_sc001.py
"""
import os, sys, hashlib, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "packages", "zoiko-common"))

from zoiko_common.crypto.jcs import canonicalize
from zoiko_common.crypto.merkle import MerkleTree, hash_leaf
from zoiko_common.crypto.signing import ZoikoSigner, LocalEd25519Backend, verify_envelope

SEP = "-" * 60

def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def show(label, value):
    if isinstance(value, bytes):
        print(f"  {label}: {value.hex()[:48]}...  ({len(value)} bytes)")
    else:
        print(f"  {label}: {value}")

# ─────────────────────────────────────────────────────────
# STEP 1 — Raw carrier invoice (what arrives from DHL)
# ─────────────────────────────────────────────────────────
section("STEP 1 — Raw carrier invoice (input)")

raw_invoice = {
    "invoice_number": "DHL-2026-00441",
    "carrier":        "DHL",
    "route":          "DAL-ATL",
    "charges": {
        "fuel":         120.00,
        "accessorial":  100.00
    },
    "total":   220.00,
    "currency": "USD",
    "billed_at": "2026-05-17T09:00:00Z"
}

print(f"  Input (as received from carrier):")
print("  " + json.dumps(raw_invoice, indent=4).replace("\n", "\n  "))

# ─────────────────────────────────────────────────────────
# STEP 2 — JCS canonicalize  (RFC 8785)
# ─────────────────────────────────────────────────────────
section("STEP 2 — JCS Canonicalize (RFC 8785)")

canonical_bytes = canonicalize(raw_invoice)
print(f"  Canonical UTF-8 form:")
print(f"  {canonical_bytes.decode()}")
print()
print(f"  Key observations:")
print(f"    - Keys are sorted alphabetically ('billed_at' before 'carrier')")
print(f"    - Numbers normalized: 120.00 → 120.0, 220.00 → 220.0")
print(f"    - No whitespace")
print(f"    - SAME bytes produced anywhere in the world, any language")

# ─────────────────────────────────────────────────────────
# STEP 3 — Domain-tagged SHA-256 hash (BEFORE encryption)
# ─────────────────────────────────────────────────────────
section("STEP 3 — Domain-tagged SHA-256 hash")

DOMAIN_SOURCE_RECORD = "zoiko/v1/source-record"
canonical_hash = hash_leaf(DOMAIN_SOURCE_RECORD, canonical_bytes)

print(f"  Domain tag : '{DOMAIN_SOURCE_RECORD}'")
print(f"  Formula    : SHA-256(0x00 || domain_tag || canonical_bytes)")
show("  Hash (hex) ", canonical_hash)
print()
print(f"  Why domain tag?")
print(f"    → A source-record hash and a canonical-invoice hash of the SAME")
print(f"      data produce DIFFERENT hashes. No cross-type confusion possible.")

other_domain = hash_leaf("zoiko/v1/canonical-invoice", canonical_bytes)
print(f"  Same data, different domain → different hash: {canonical_hash.hex()[:16]}... ≠ {other_domain.hex()[:16]}...")

# ─────────────────────────────────────────────────────────
# STEP 4 — Sign the hash
# ─────────────────────────────────────────────────────────
section("STEP 4 — Sign with Ed25519 (ingestion-service key)")

signer = ZoikoSigner(LocalEd25519Backend())
envelope = signer.sign(canonical_hash)

show("  Key ID (kid)      ", envelope.kid)
show("  Signature         ", envelope.signature)
show("  Public key (DER)  ", signer.public_key_der)
print()
print(f"  In production: kid = GCP KMS resource name (e.g.)")
print(f"    projects/zoiko-logistics-prod/locations/us-central1/")
print(f"    keyRings/zoiko-prod/cryptoKeys/ingestion-signing-key/cryptoKeyVersions/1")

# ─────────────────────────────────────────────────────────
# STEP 5 — Verify the signature (offline, no network)
# ─────────────────────────────────────────────────────────
section("STEP 5 — Verify signature offline")

is_valid = verify_envelope(envelope, signer.public_key_der)
print(f"  verify_envelope(envelope, public_key_der) → {is_valid}")

# Tamper test
import dataclasses
tampered = dataclasses.replace(envelope, payload=b"tampered-content")
is_valid_tampered = verify_envelope(tampered, signer.public_key_der)
print(f"  verify_envelope(TAMPERED envelope, public_key_der) → {is_valid_tampered}")
print()
print(f"  This is what the offline ACR verifier does — no Zoiko access needed.")

# ─────────────────────────────────────────────────────────
# STEP 6 — Build the 8-artifact ACR Merkle tree
# ─────────────────────────────────────────────────────────
section("STEP 6 — ACR Merkle tree (8 artifacts)")

artifacts = {
    "source_record":       canonical_hash,
    "validation_result":   hashlib.sha256(b"PASS:rule_violations=[]").digest(),
    "canonical_invoice":   hashlib.sha256(canonical_bytes).digest(),
    "finding":             hashlib.sha256(b"confidence=0.96:fuel=OK:accessorial=OVERCHARGE").digest(),
    "decision_proposal":   hashlib.sha256(b"action=RECOVER:amount=100.00:USD").digest(),
    "governance_decision": hashlib.sha256(b"outcome=APPROVED:policy_version=v1.2").digest(),
    "governance_token":    hashlib.sha256(b"scope=EXECUTE:tenant=ZOIKO-DEMO:expires=2026-05-18").digest(),
    "outcome":             hashlib.sha256(b"recovered=100.00:USD:connector=mock-carrier-api").digest(),
}

tree = MerkleTree("zoiko/v1/acr")
leaf_hashes = {}
for name, data in artifacts.items():
    leaf_hash = tree.append(data)
    leaf_hashes[name] = leaf_hash
    show(f"  Leaf [{name[:24]:24s}]", leaf_hash)

merkle_root = tree.root()
print()
show("  MERKLE ROOT", merkle_root)

# ─────────────────────────────────────────────────────────
# STEP 7 — Generate inclusion proofs (for ACR verify package)
# ─────────────────────────────────────────────────────────
section("STEP 7 — Generate inclusion proofs")

names = list(artifacts.keys())
for i, name in enumerate(names):
    proof = tree.proof(i)
    valid = MerkleTree.verify(merkle_root, leaf_hashes[name], proof)
    print(f"  proof({i}) [{name[:24]:24s}] path_length={len(proof.path)}  verify={valid}")

# ─────────────────────────────────────────────────────────
# STEP 8 — Tamper detection
# ─────────────────────────────────────────────────────────
section("STEP 8 — Tamper detection demo")

print(f"  Original Merkle root: {merkle_root.hex()[:32]}...")
print()

tampered_tree = MerkleTree("zoiko/v1/acr")
for name, data in artifacts.items():
    if name == "finding":
        tampered_data = hashlib.sha256(b"confidence=0.99:TAMPERED").digest()
        tampered_tree.append(tampered_data)
        print(f"  Attacker changes: finding confidence 0.96 → 0.99")
    else:
        tampered_tree.append(data)

tampered_root = tampered_tree.root()
print(f"  Tampered Merkle root: {tampered_root.hex()[:32]}...")
print()
print(f"  Roots match? {merkle_root == tampered_root}  ← Any change = different root")
print(f"  Tamper is DETECTABLE even without seeing the finding document itself.")

# ─────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────
section("FINAL OUTPUT — What Phase 0 produces for SC-001")

acr_summary = {
    "case_id":         "sc-001-dal-atl-2026-00441",
    "tenant_id":       "zoiko-demo",
    "canonical_hash":  canonical_hash.hex(),
    "merkle_root":     merkle_root.hex(),
    "signing_kid":     envelope.kid,
    "confidence":      0.96,
    "fuel_charge":     {"billed": 120.00, "contract": 120.00, "delta": 0.00,   "status": "OK"},
    "accessorial":     {"billed": 100.00, "contract": 0.00,   "delta": 100.00, "status": "OVERCHARGE"},
    "total_recovery":  100.00,
    "currency":        "USD",
    "acr_status":      "VERIFIED",
}

print(json.dumps(acr_summary, indent=2))
print()
print(f"  This ACR package can be verified by ANY auditor with:")
print(f"    python verify.sh  ← included in acr-verify-sc-001.zip")
print(f"    ZERO access to Zoiko systems required.")

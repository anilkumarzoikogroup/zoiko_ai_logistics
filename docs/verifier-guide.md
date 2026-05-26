# Offline ACR Verifier Guide

The Zoiko ACR (Action Certification Record) is cryptographically self-contained.
Any third party holding the tenant's public key can verify it **without contacting
any Zoiko infrastructure**.

---

## What the Verifier Checks

A valid ACR bundle must pass three verification steps:

### Step 1 — Artifact hashes well-formed
Every artifact must have a `hash` field that is a valid 64-character lowercase
hex string (SHA-256 digest). This ensures the bundle is not corrupted in transit.

### Step 2 — Merkle root recomputation
The verifier reconstructs the Merkle tree from the artifact hashes using the
`zoiko/v1/acr` domain tag and checks that the computed root matches the
`merkle_root` field in the bundle. This proves no artifact was added, removed,
or substituted after the ACR was issued.

### Step 3 — Ed25519 signature verification
The verifier checks the Ed25519 signature over:
```
SHA-256(b"zoiko/v1/acr" + JCS(payload_dict))
```
where `payload_dict` contains `merkle_root`, `case_id`, `tenant_id`, and `issued_at`.
The signature was created by the Zoiko KMS signing key identified by `kid`.
This proves the ACR was issued by an authorised Zoiko service and has not been
tampered with since issuance.

---

## Running the Verifier

### CLI (simplest)

```bash
# Linux/macOS
bash verify.sh acr.json

# Windows PowerShell
python phase-4/services/audit_acr_svc/verifier.py acr.json
```

Exit codes:
- `0` — All 3 steps PASS. ACR is authentic and untampered.
- `1` — Verification FAILED. Output includes the failing step and reason.

### Python API

```python
from services.audit_acr_svc.verifier import verify_bundle
import json

with open("acr.json") as f:
    bundle = json.load(f)

result = verify_bundle(bundle)
print(result.passed, result.steps)
```

### REST API (online, authenticated)

```
GET /v1/cases/{case_id}/acr        → Download ACR bundle as JSON
POST /v1/verifier/acrs/verify      → Verify bundle online (no auth required)
GET /v1/acrs/{acr_id}/verify-package → Download bundle + verifier script as ZIP
```

---

## ACR Bundle Format

```json
{
  "acr_id": "550e8400-...",
  "case_id": "...",
  "tenant_id": "...",
  "issued_at": "2025-10-01T14:23:00+00:00",
  "merkle_root": "a1b2c3...64hex...",
  "signature": "ed25519hex...",
  "kid": "local:acme-logistics:signing:v1",
  "artifacts": [
    {
      "name": "source_record",
      "hash": "sha256hexstring",
      "domain_tag": "zoiko.ingestion.invoice.v1:"
    },
    {
      "name": "canonical_invoice",
      "hash": "...",
      "domain_tag": "zoiko.canonical.invoice.v1:"
    },
    {
      "name": "evidence_bundle",
      "hash": "...",
      "domain_tag": "zoiko.evidence.item.v1:"
    },
    {
      "name": "finding",
      "hash": "...",
      "domain_tag": "zoiko.finding.v1:"
    },
    {
      "name": "proposal",
      "hash": "...",
      "domain_tag": "zoiko.proposal.v1:"
    },
    {
      "name": "governance_decision",
      "hash": "...",
      "domain_tag": "zoiko.governance.decision.v1:"
    },
    {
      "name": "governance_token",
      "hash": "...",
      "domain_tag": "zoiko.token.v1:"
    },
    {
      "name": "execution_envelope",
      "hash": "...",
      "domain_tag": "zoiko/v1/acr:"
    }
  ]
}
```

---

## Cryptographic Primitives

| Element | Algorithm |
|---------|-----------|
| Artifact content hash | SHA-256 with domain tag prefix |
| Merkle leaf hash | SHA-256(`b"zoiko/v1/acr:" + artifact_hash_bytes`) |
| Merkle parent hash | SHA-256(`left_hash + right_hash`) |
| ACR payload hash | SHA-256(`b"zoiko/v1/acr:" + JCS(payload_dict).encode()`) |
| Signature | Ed25519 over ACR payload hash |
| Serialisation | RFC 8785 JCS (JSON Canonicalization Scheme) |

---

## Verifying a Historical ACR

If the KMS signing key has been rotated, the `kid` field identifies the specific
key version used. Historical ACR records are always verifiable as long as the
public key for that `kid` is available in the key archive.

In production, public keys are stored in Cloud KMS and are never deleted.
In dev, the local KMS backend derives keys deterministically from a seed — the
same seed always produces the same keys, so old ACRs remain verifiable.

---

## Tamper Detection

If the verifier returns `FAIL`, one of the following has occurred:

1. **Step 1 fails** — Bundle is corrupted or truncated.
2. **Step 2 fails** — An artifact was modified, added, or removed after issuance.
   This is a security incident. Preserve the bundle as evidence.
3. **Step 3 fails** — The signature was forged or the payload was modified.
   The `kid` field does not match the key on record, or the signature bytes are wrong.
   This is a security incident requiring immediate escalation.

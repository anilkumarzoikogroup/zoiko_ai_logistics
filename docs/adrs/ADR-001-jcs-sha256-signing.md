# ADR-001: JCS + SHA-256 + Ed25519 for Event Signing

**Status:** Accepted  
**Date:** 2025-09-01  
**Deciders:** Zoiko Engineering

---

## Context

Every Kafka event and database record in the Zoiko freight audit pipeline must be
cryptographically signed so that the ACR (Action Certification Record) is verifiable
by any third party holding only the tenant's public key.

Requirements:
- Deterministic serialisation (same input → same bytes, every time, on every platform)
- Tamper evidence (any field mutation invalidates the signature)
- Independent verifiability (offline, no Zoiko infrastructure needed)
- Fast key rotation without invalidating historical records

## Decision

Use **RFC 8785 JSON Canonicalization Scheme (JCS)** + **domain-tagged SHA-256** +
**Ed25519 (NaCl)** as the canonical signing stack for all Zoiko events.

```
signature = Ed25519_sign(private_key, SHA-256(domain_tag || JCS(payload_dict)))
```

Domain tags (e.g. `b"zoiko.proposal.v1:"`) prevent cross-type signature confusion:
a valid proposal signature cannot be replayed as a token signature.

## Rationale

| Option | Rejected because |
|--------|-----------------|
| ECDSA P-256 | Non-deterministic without RFC 6979; 64-byte sigs vs 64-byte Ed25519 |
| RSA-PSS | 256-byte signatures; slower key generation; overkill for event signing |
| HMAC-SHA256 | Symmetric — requires sharing the signing secret; breaks non-repudiation |
| JSON-LD Signatures | Heavy dependency; no standard Python library; spec in flux |

JCS was chosen over protobuf or CBOR because:
- Events are already JSON (Kafka, REST, ACR bundle)
- RFC 8785 is a stable W3C candidate recommendation
- `canonicalize()` is pure-Python with no external dependencies

## Consequences

- **Hard CI block on JCS vectors:** Any regression in `canonicalize()` breaks the entire
  signing chain. The CI pipeline treats JCS test failures as a hard block (exit 1).
- **Hash-before-encrypt rule:** The canonical hash is computed from the PLAINTEXT before
  AES-GCM encryption. Storing only the ciphertext means the hash is recomputable from
  the decrypted value — the audit trail is intact even if the DEK is rotated.
- **Ed25519 key per tenant per phase:** Keys are provisioned via the KMS hierarchy
  (`zoiko_kms.hierarchy.KeyHierarchy`) and identified by KID (SHA-256 of public key DER).

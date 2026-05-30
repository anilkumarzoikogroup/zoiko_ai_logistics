# ADR-001: JCS (RFC 8785) as the Canonical Serialization Format

**Status:** Accepted  
**Date:** 2025-01-15  
**Authors:** Zoiko Engineering  

---

## Context

Zoiko needs a deterministic byte representation of invoice and case data before hashing. Without a canonical form, the same logical object can produce different bytes (and therefore different SHA-256 hashes) depending on key insertion order, number formatting, or serialization library.

Two options were considered:

| Option | Description | Problem |
|--------|-------------|---------|
| `json.dumps(obj, sort_keys=True)` | Python stdlib JSON with sorted keys | Number serialization differs between implementations (1.0 vs 1, trailing zeros) |
| **JCS (RFC 8785)** | IETF-standardized JSON Canonicalization Scheme | Deterministic number serialization, cross-language, RFC-backed |

## Decision

Use **RFC 8785 JCS** (`zoiko_common.crypto.jcs.canonicalize`) as the only serialization step before hashing.

Rules:
- Object keys sorted by Unicode code point (not locale-sensitive)
- Numbers: integers as-is, floats strip trailing zeros, `1.0` → `1`
- No whitespace
- UTF-8 encoded bytes output
- Called on every hash boundary: ingestion, canonical invoice, finding, proposal, governance decision, token

## Consequences

**Positive:**
- Cross-language reproducibility: a Rust or Go verifier can produce the same hash
- RFC 8785 test vectors lock behavior — CI hard-blocks on any regression
- Offline ACR verification possible without the backend

**Negative:**
- Cannot use standard `json.dumps` anywhere on hash-critical paths (enforced by code review)
- Number edge cases (NaN, Infinity) must be rejected at ingestion — not serializable in JCS

## Enforcement

- `phase-0/packages/zoiko-common/tests/crypto/test_jcs.py` — RFC 8785 Appendix B.1 vector, CI hard block
- `phase-0/packages/zoiko-common/tests/test_hardening_t001_t005.py::TestT001JCSDeterministic` (T-001)
- All service handlers call `canonicalize()` before `hashlib.sha256(domain + canonical_bytes)`

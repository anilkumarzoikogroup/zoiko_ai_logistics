# ADR-004: 8-Gate Execution Checklist Before Money Moves

**Status:** Accepted  
**Date:** 2025-10-01  
**Deciders:** Zoiko Engineering, Finance, Compliance

---

## Context

Phase 4 executes the financial recovery action (credit memo or debit note) for an
approved overcharge case. This is an irreversible financial action — once funds move,
reversal requires a separate dispute process. The governance token represents the
authorisation granted by the approval workflow.

## Decision

Before ANY financial dispatch, the Execution Gateway enforces 8 sequential gates.
All 8 must pass; the first failure stops execution and writes a FAILED envelope.

| Gate | Name | Check |
|------|------|-------|
| 1 | `signature_valid` | Ed25519 signature over token_hash verifies against KMS public key |
| 2 | `not_expired` | `expires_at > now()` — 15-minute execution window |
| 3 | `not_consumed` | Redis SET NX + DB `status != CONSUMED` — prevents replay |
| 4 | `tenant_binding` | SHA-256(tenant_id + decision_id) matches token's binding field |
| 5 | `scope_allowed` | `scope ∈ {EXECUTE_CREDIT_MEMO, EXECUTE_DEBIT_NOTE}` |
| 6 | `sanctions_clear` | Actor and carrier not on OFAC/UN sanctions list (stub in dev) |
| 7 | `fx_lock_valid` | FX rate locked within 5% tolerance of agreed amount |
| 8 | `connector_active` | Carrier connector certified and circuit breaker CLOSED |

## Rationale

The 8-gate structure mirrors Zoiko's compliance framework (spec §7.4). Each gate
corresponds to a different risk dimension: cryptographic, temporal, replay, binding,
scope, regulatory, financial, and operational. Combining them into one atomic check
ensures that partial failures are caught before the token is consumed.

## Consequences

- **Atomicity:** The token is marked CONSUMED only if ALL 8 gates pass. A gate failure
  does NOT consume the token — the analyst can resolve the issue and retry within TTL.
- **No partial execution:** If gate 6 (sanctions) fails after gates 1-5 pass, no
  financial action has been taken. The token remains valid until TTL expires.
- **WORM audit:** Every gate result is recorded in the execution envelope, which is
  written to the `audit_worm_index` table. Gate results are immutable.
- **Redis graceful degradation:** If Redis is unavailable, gate 3 falls back to the
  DB `status` check (slightly weaker but never allows double-spend if DB is consistent).

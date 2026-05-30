# ADR-002: Separation of Duties (SoD) — Proposer ≠ Approver

**Status:** Accepted  
**Date:** 2025-01-15  
**Authors:** Zoiko Engineering  

---

## Context

The SC-001 dispute recovery pipeline moves real money. Without a two-person rule, a single compromised account could propose a fraudulent recovery and approve it themselves.

Freight overcharge amounts can reach millions of INR per case. Separation of Duties (SoD) is a standard internal control in financial systems and is required by our enterprise customers' audit frameworks (SOC 2 Type II, ISO 27001).

## Decision

**The actor who proposes a recovery (analyst) cannot be the same person who approves it (manager).**

Enforcement points:

1. **Phase 3 GovernanceHandler.decide()** — hard check before any DB write:
   ```python
   if actor_sub == task["proposer_sub"]:
       raise ValueError(
           f"Separation of Duties violation: actor_sub '{actor_sub}' "
           f"cannot be the same as proposer_sub '{task['proposer_sub']}'"
       )
   ```

2. **OPA policy** — RBAC roles are enforced: `role=analyst` can propose, `role=manager` can decide. The same JWT cannot have a role that permits both at the same time on the same case.

3. **Governance token** — the token includes both `proposer_sub` and `decision_id` in its hash payload, creating a tamper-evident chain that links approval to a specific named individual.

4. **TCP certification test** — T-023 (`test_tcp_certification.py::TestTCPSoDCertification`) verifies this enforcement on every CI run and writes results to `certification_runs`.

## Consequences

**Positive:**
- No single credential can move money unilaterally
- SoD violation attempts are logged as security events (`zoiko.security.event-detected.v1`)
- Audit trail includes both actor identities in `governance_decisions` and `approval_tasks`

**Negative:**
- Demo flows require two separate JWT identities (analyst + manager)
- In `ZOIKO_DEV_MODE=true`, the check still runs — tests must use different `actor_sub` values

## WONT-DO

We will NOT bypass SoD via configuration flag, emergency override, or superuser bypass. If a legitimate override is ever required, it must go through a separate governance workflow with a quorum of 3 approvers — that is a future ADR.

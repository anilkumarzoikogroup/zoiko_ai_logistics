# ADR-003: OPA Fail-Closed Policy Enforcement

**Status:** Accepted  
**Date:** 2025-09-10  
**Deciders:** Zoiko Engineering, Compliance

---

## Context

Every API request in Phases 2 and 3 must be authorised by an OPA (Open Policy Agent)
policy that enforces tenant isolation (RBAC + row-level security). If the OPA server
is unavailable, the system must not silently allow requests.

## Decision

OPA is **fail-closed**: if the OPA server is unreachable or returns an error, the
request is rejected with HTTP 503 (Service Unavailable) with error code `OPA_UNAVAILABLE`.

Never-permit rule:
```python
if not opa_result.allow:
    raise OPADeniedError(policy=policy_name, reason=opa_result.reason)
if opa_result.error:
    return OPAResult(allow=False, reason="OPA unavailable")  # fail closed
```

In dev (`OPA_URL` not set), `MockOPAClient` always returns `allow=True`. This is
explicitly a dev-only bypass — never set `OPA_URL=""` in staging/production.

## Rationale

The alternative (fail-open) is categorically unacceptable for a financial compliance
system. A tenant whose OPA policy was mis-configured must be denied, not silently
allowed. The 503 response is preferable to a false positive.

The tradeoff is availability: if OPA goes down, the API stops accepting requests.
This is mitigated by:
- OPA running as a sidecar in the same pod (not a remote service)
- Health checks that gate OPA deployment
- Circuit breaker on the OPA HTTP client (future work)

## Consequences

- **No silent permit:** `allow=False OR error` → request rejected with 503 or 403
- **Audit trail:** Every OPA denial is logged with tenant_id, policy name, and reason
- **Dev bypass:** `OPA_URL=""` → `MockOPAClient(allow=True)` — acceptable in dev,
  forbidden in production (enforced by deployment checklist)

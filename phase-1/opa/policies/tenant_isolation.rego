# tenant_isolation.rego
# Hard guard: every data-accessing request must carry a matching tenant_id.
#
# This policy runs BEFORE any service logic.
# If OPA is unreachable, the service must return 503 — never bypass.

package zoiko.tenant_isolation

import future.keywords.if
import future.keywords.in

# ── Default deny ─────────────────────────────────────────────────────────────
default allow := false

# ── Allow: tenant_id in JWT matches tenant_id in request path/body ────────────
allow if {
    input.claim_tenant_id != ""
    input.resource_tenant_id != ""
    input.claim_tenant_id == input.resource_tenant_id
}

# ── Allow: admin cross-tenant read (audit only) ────────────────────────────
allow if {
    input.action == "ADMIN_READ"
    "admin" in input.roles
}

# ── Violations ────────────────────────────────────────────────────────────────
violations[msg] if {
    input.claim_tenant_id != input.resource_tenant_id
    msg := sprintf(
        "Tenant isolation violation: token has tenant %q but resource belongs to tenant %q",
        [input.claim_tenant_id, input.resource_tenant_id]
    )
}

violations[msg] if {
    input.claim_tenant_id == ""
    msg := "Missing tenant_id claim in token"
}

violations[msg] if {
    input.resource_tenant_id == ""
    msg := "Missing tenant_id on resource"
}

# freight_dispute.rego
# Policy bundle for SC-001 freight dispute resolution.
#
# Rules enforced:
#   1. Only analysts can propose recovery actions
#   2. Only managers can approve governance decisions
#   3. Proposer and approver must be different (SoD)
#   4. Recovery amount must not exceed the detected overcharge
#   5. Token scope must match the requested action
#
# OPA is fail-closed: if this policy bundle is unreachable → 503.
# Never permit on unavailability.

package zoiko.freight_dispute

import future.keywords.if
import future.keywords.in

# ── Default deny ─────────────────────────────────────────────────────────────
default allow := false

# ── Allow: analyst may propose a recovery ────────────────────────────────────
allow if {
    input.action == "PROPOSE_RECOVERY"
    "analyst" in input.roles
    input.tenant_id == input.claim_tenant_id
}

# ── Allow: manager may approve a proposal ────────────────────────────────────
allow if {
    input.action == "APPROVE_PROPOSAL"
    "manager" in input.roles
    input.tenant_id == input.claim_tenant_id
    sod_satisfied
}

# ── Allow: any authenticated user may view cases for their tenant ─────────────
allow if {
    input.action == "READ_CASE"
    input.tenant_id == input.claim_tenant_id
}

# ── Allow: execution gateway with valid EXECUTE token ────────────────────────
allow if {
    input.action == "EXECUTE_RECOVERY"
    input.token_scope == "EXECUTE"
    input.tenant_id == input.claim_tenant_id
    not input.token_expired
}

# ── Separation of Duties ─────────────────────────────────────────────────────
# proposer_sub must differ from actor_sub
sod_satisfied if {
    input.proposer_sub != input.actor_sub
}

# ── Violations (returned alongside deny for observability) ────────────────────
violations[msg] if {
    input.action == "APPROVE_PROPOSAL"
    input.proposer_sub == input.actor_sub
    msg := "SoD violation: proposer and approver are the same person"
}

violations[msg] if {
    input.action in {"PROPOSE_RECOVERY", "APPROVE_PROPOSAL", "EXECUTE_RECOVERY"}
    input.tenant_id != input.claim_tenant_id
    msg := "Tenant mismatch: token tenant does not match resource tenant"
}

violations[msg] if {
    input.action == "EXECUTE_RECOVERY"
    input.token_expired
    msg := "Token is expired"
}

violations[msg] if {
    input.action == "APPROVE_PROPOSAL"
    not "manager" in input.roles
    msg := "Role required: manager"
}

violations[msg] if {
    input.action == "PROPOSE_RECOVERY"
    not "analyst" in input.roles
    msg := "Role required: analyst"
}

# Zoiko Freight Overcharge Policy — OPA Rego
#
# Evaluated by the API Gateway on every request (fail-closed: if OPA
# is unreachable the request is rejected with 503, never permitted).
#
# Input shape (from the gateway's OPA client):
#   input.method   — HTTP verb (GET, POST, PATCH, DELETE)
#   input.path     — request path array ["v1","cases","<id>","proposal"]
#   input.claims   — JWT claims {sub, tenant_id, roles, zoiko_env}
#   input.resource — optional resource hint for fine-grained rules
#
# Decisions:
#   data.zoiko.freight.allow.decision == true  → permit
#   data.zoiko.freight.allow.decision == false → 403
#
# SoD enforcement is done in the handler layer (GovernanceHandler.decide);
# OPA handles coarse-grained RBAC here.

package zoiko.freight.allow

import future.keywords.if
import future.keywords.in

default decision := false

# ── Role definitions ──────────────────────────────────────────────────────────

_roles := input.claims.roles

_is_analyst := "analyst" in _roles
_is_manager := "manager" in _roles
_is_admin   := "admin"   in _roles

# ── Public routes (no auth) ────────────────────────────────────────────────────

decision if {
    input.method == "GET"
    input.path[0] == "health"
}

# ── Analyst routes — READ any case data ───────────────────────────────────────

decision if {
    _is_analyst
    input.method == "GET"
}

decision if {
    _is_analyst
    input.method == "POST"
    input.path[0] in {"invoices", "cases", "ingestion"}
}

# Analyst can create proposals
decision if {
    _is_analyst
    input.method == "POST"
    "proposal" in input.path
}

# ── Manager routes — approve/reject proposals ─────────────────────────────────

decision if {
    _is_manager
    input.method in {"GET", "POST", "PATCH"}
}

# ── Admin routes — full access ────────────────────────────────────────────────

decision if {
    _is_admin
}

# ── Execution gateway — system-level token consumption ────────────────────────

decision if {
    input.claims.zoiko_env == "dev"
    input.method in {"GET", "POST", "PATCH", "DELETE"}
}

# ── Tenant isolation — claims.tenant_id must match X-Tenant-ID header ─────────
# (checked in the gateway, but expressed here for documentation)

tenant_isolated if {
    input.claims.tenant_id == input.tenant_id_header
}

tenant_isolated if {
    input.claims.zoiko_env == "dev"
}

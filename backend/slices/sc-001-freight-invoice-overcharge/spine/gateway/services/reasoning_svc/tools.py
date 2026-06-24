"""Agent Tool Registry — permission enforcement for the freight dispute agent.

Read-only tools (ALLOWED):
  read_evidence_bundle  — fetches evidence items for a bundle
  read_contract_rates   — fetches applicable contract rates
  read_case_metadata    — fetches case state and subject metadata (invoice or claim)

Forbidden tools (DENIED — these require the Execution Gateway):
  call_carrier_api        — only Execution Gateway may call carrier APIs
  issue_credit_memo       — only Phase 4 can move money
  write_canonical_invoice — canonical invoice is immutable after creation

The in-process _REGISTRY is the ground truth for permission checks.
The agent_tool_permissions DB table mirrors this for audit and reporting.
"""
from __future__ import annotations
import uuid

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter


class ToolPermissionError(Exception):
    pass


_REGISTRY: dict[str, dict] = {
    "read_evidence_bundle": {
        "allowed": True,
        "requires_approval": False,
        "description": "Read evidence items from a bundle (read-only)",
    },
    "read_contract_rates": {
        "allowed": True,
        "requires_approval": False,
        "description": "Fetch contract rates for validation (read-only)",
    },
    "read_case_metadata": {
        "allowed": True,
        "requires_approval": False,
        "description": "Read case state and subject metadata — invoice or claim (read-only)",
    },
    "call_carrier_api": {
        "allowed": False,
        "requires_approval": False,
        "description": "Direct carrier API call — only Execution Gateway permitted",
    },
    "issue_credit_memo": {
        "allowed": False,
        "requires_approval": False,
        "description": "Issue credit memo directly — only Phase 4 Execution Gateway",
    },
    "write_canonical_invoice": {
        "allowed": False,
        "requires_approval": False,
        "description": "Modify canonical invoice — agent is read-only",
    },
}


def check_permission(tool_name: str) -> None:
    """Raise ToolPermissionError if tool is unknown or not permitted."""
    entry = _REGISTRY.get(tool_name)
    if entry is None:
        raise ToolPermissionError(
            f"Unknown tool '{tool_name}' — not in registry. "
            f"Permitted tools: {[k for k, v in _REGISTRY.items() if v['allowed']]}"
        )
    if not entry["allowed"]:
        raise ToolPermissionError(
            f"Tool '{tool_name}' is NOT permitted for agent use: {entry['description']}"
        )


def invoke(tool_name: str, db_url: str, **kwargs) -> dict:
    """Check permission then execute the tool. Returns a result dict."""
    check_permission(tool_name)
    _handlers = {
        "read_evidence_bundle": _read_evidence_bundle,
        "read_contract_rates":  _read_contract_rates,
        "read_case_metadata":   _read_case_metadata,
    }
    return _handlers[tool_name](db_url=db_url, **kwargs)


def all_permissions() -> list[dict]:
    """Return the full tool registry as a list (for reporting)."""
    return [
        {"tool_name": k, **v}
        for k, v in _REGISTRY.items()
    ]


# ── Tool implementations (read-only) ─────────────────────────────────────────

def _read_evidence_bundle(db_url: str, bundle_id: str, tenant_id: str) -> dict:
    try:
        conn = psycopg2.connect(db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, item_type FROM evidence_items "
                "WHERE bundle_id=%s AND tenant_id=%s ORDER BY added_at",
                (uuid.UUID(bundle_id), tenant_id),
            )
            items = [{"id": str(r["id"]), "item_type": r["item_type"]} for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        items = []
    return {"bundle_id": bundle_id, "item_count": len(items), "items": items}


def _read_contract_rates(db_url: str, tenant_id: str, carrier_id: str = None) -> dict:
    try:
        conn = psycopg2.connect(db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            if carrier_id:
                cur.execute(
                    "SELECT carrier_id, rate_type, rate_value, currency "
                    "FROM contract_rates WHERE tenant_id=%s AND carrier_id=%s "
                    "AND superseded_at IS NULL "
                    "AND (expires_on IS NULL OR expires_on >= CURRENT_DATE) "
                    "ORDER BY effective_on DESC",
                    (tenant_id, carrier_id),
                )
            else:
                cur.execute(
                    "SELECT carrier_id, rate_type, rate_value, currency "
                    "FROM contract_rates WHERE tenant_id=%s "
                    "AND superseded_at IS NULL "
                    "AND (expires_on IS NULL OR expires_on >= CURRENT_DATE) "
                    "ORDER BY effective_on DESC",
                    (tenant_id,),
                )
            rates = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        rates = []
    return {"tenant_id": tenant_id, "rate_count": len(rates), "rates": rates}


def _read_case_metadata(db_url: str, case_id: str, tenant_id: str) -> dict:
    """Reads case state + invoice subject metadata."""
    try:
        conn = psycopg2.connect(db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT c.state, ci.carrier_id, ci.total_amount, ci.currency "
                "FROM cases c "
                "JOIN canonical_invoices ci ON ci.id = c.invoice_id "
                "WHERE c.id=%s AND c.tenant_id=%s",
                (uuid.UUID(case_id), tenant_id),
            )
            row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        row = None
    if not row:
        return {"case_id": case_id, "found": False}
    return {"case_id": case_id, "found": True, **dict(row)}

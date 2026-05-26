"""
Sanctions screening stub (fail-closed).

Dev/test: passes all actors through.
Prod:     call OFAC/UN sanctions API; block and raise on match.

Setting SANCTIONS_BLOCKED_ACTORS env var (comma-separated) lets tests inject
blocked actors without a real sanctions API.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SanctionsResult:
    actor:    str
    cleared:  bool
    reason:   str


_BLOCKED: set[str] = set(
    x.strip() for x in os.getenv("SANCTIONS_BLOCKED_ACTORS", "").split(",") if x.strip()
)


def screen(actor_sub: str, tenant_id: str) -> SanctionsResult:
    """
    Screen actor_sub against the sanctions list.
    Fail-closed: any exception → treat as blocked.
    """
    try:
        api_url = os.getenv("SANCTIONS_API_URL", "")
        if api_url:
            return _call_real_api(actor_sub, tenant_id, api_url)

        # Dev stub — check env-injected block list
        if actor_sub in _BLOCKED:
            return SanctionsResult(actor=actor_sub, cleared=False, reason="On SANCTIONS_BLOCKED_ACTORS list")

        return SanctionsResult(actor=actor_sub, cleared=True, reason="Cleared (dev stub)")
    except Exception as e:
        # Fail-closed: unavailable = blocked
        return SanctionsResult(actor=actor_sub, cleared=False, reason=f"Sanctions check failed (fail-closed): {e}")


def _call_real_api(actor_sub: str, tenant_id: str, api_url: str) -> SanctionsResult:
    import urllib.request, json
    req  = urllib.request.Request(
        f"{api_url}/screen",
        data=json.dumps({"actor": actor_sub, "tenant_id": tenant_id}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read())
    cleared = body.get("cleared", False)
    return SanctionsResult(
        actor=actor_sub,
        cleared=cleared,
        reason=body.get("reason", ""),
    )

"""
OPA REST client — fail-closed.

Key rule (non-negotiable):
  If OPA is unreachable → raise OPAUnavailableError → service returns 503.
  NEVER permit on unavailability.

OPA REST API:
  POST /v1/data/{package_path}
  Body:  {"input": {...}}
  Response: {"result": {"allow": true/false, "violations": [...]}}
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OPADecision:
    """Result from OPA policy evaluation."""
    allow:      bool
    violations: List[str] = field(default_factory=list)
    policy:     str = ""

    @property
    def denied(self) -> bool:
        return not self.allow

    def reason(self) -> str:
        if self.violations:
            return "; ".join(self.violations)
        return "Denied by policy" if self.denied else "Allowed"


class OPAUnavailableError(Exception):
    """Raised when OPA is unreachable. Services must return 503."""
    pass


class OPAClient:
    """
    Synchronous OPA REST client.

    opa_url: base URL of OPA server, e.g. "http://localhost:8181"
    timeout: seconds to wait before raising OPAUnavailableError
    """

    def __init__(self, opa_url: str = "http://localhost:8181", timeout: float = 2.0):
        self._url     = opa_url.rstrip("/")
        self._timeout = timeout

    def evaluate(self, policy_path: str, input_data: Dict[str, Any]) -> OPADecision:
        """
        Evaluate a policy rule.

        policy_path: e.g. "zoiko/freight_dispute" → calls /v1/data/zoiko/freight_dispute
        input_data:  the input document sent to OPA

        Raises OPAUnavailableError if OPA cannot be reached.
        """
        url  = f"{self._url}/v1/data/{policy_path.replace('.', '/')}"
        body = json.dumps({"input": input_data}).encode("utf-8")
        req  = urllib.request.Request(
            url,
            data    = body,
            method  = "POST",
            headers = {"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read())
        except urllib.error.URLError as e:
            raise OPAUnavailableError(
                f"OPA unreachable at {url}: {e}. "
                "Failing closed — request blocked per policy rule 5."
            ) from e
        except Exception as e:
            raise OPAUnavailableError(f"OPA error: {e}") from e

        data = result.get("result", {})
        return OPADecision(
            allow      = bool(data.get("allow", False)),
            violations = list(data.get("violations", [])),
            policy     = policy_path,
        )

    def check_freight_dispute(self, input_data: Dict[str, Any]) -> OPADecision:
        return self.evaluate("zoiko/freight_dispute", input_data)

    def check_tenant_isolation(self, claim_tenant: str, resource_tenant: str, roles: list) -> OPADecision:
        return self.evaluate("zoiko/tenant_isolation", {
            "claim_tenant_id":    claim_tenant,
            "resource_tenant_id": resource_tenant,
            "roles":              roles,
            "action":             "ACCESS",
        })

    def health(self) -> bool:
        """Return True if OPA is reachable and healthy."""
        try:
            with urllib.request.urlopen(f"{self._url}/health", timeout=self._timeout):
                return True
        except Exception:
            return False


class MockOPAClient(OPAClient):
    """
    In-memory OPA mock for unit tests and local/dev convenience.
    Pre-load decisions with .set_decision(); default is allow=True.

    NEVER wire this up for a production environment (ZOIKO_DEV_MODE=false) —
    use resolve_opa_client() below instead of constructing clients directly.
    """

    def __init__(self):
        self._decisions: Dict[str, OPADecision] = {}
        self._calls:     List[dict] = []

    def set_decision(self, policy_path: str, decision: OPADecision) -> None:
        self._decisions[policy_path] = decision

    def evaluate(self, policy_path: str, input_data: Dict[str, Any]) -> OPADecision:
        self._calls.append({"policy": policy_path, "input": input_data})
        return self._decisions.get(policy_path, OPADecision(allow=True))

    @property
    def call_count(self) -> int:
        return len(self._calls)

    def last_input(self, policy_path: Optional[str] = None) -> Optional[dict]:
        if policy_path:
            for c in reversed(self._calls):
                if c["policy"] == policy_path:
                    return c["input"]
            return None
        return self._calls[-1]["input"] if self._calls else None


class FailClosedOPAClient(OPAClient):
    """
    Used when no real OPA server is configured outside of dev/test mode.

    Per SCAP v3.0 ("policy is fail-closed; no consequential action without
    a governance decision"), a production deployment with no OPA_URL set
    must never silently allow — it must behave exactly as if OPA were
    unreachable: every check raises OPAUnavailableError, which callers
    already convert to HTTP 503.
    """

    def __init__(self):
        pass

    def evaluate(self, policy_path: str, input_data: Dict[str, Any]) -> OPADecision:
        raise OPAUnavailableError(
            f"No OPA_URL configured for policy '{policy_path}' outside dev/test mode — "
            "failing closed. Set OPA_URL or ZOIKO_DEV_MODE=true."
        )

    def health(self) -> bool:
        return False


def resolve_opa_client(opa_url: str, dev_mode: bool) -> OPAClient:
    """
    Single source of truth for which OPA client a service should use.

      OPA_URL set            -> real OPAClient(opa_url), fail-closed on unreachable
      OPA_URL unset + dev    -> MockOPAClient(), allow=True (local/test convenience)
      OPA_URL unset + prod   -> FailClosedOPAClient(), every check raises -> 503

    This replaces the old `OPAClient(OPA_URL) if OPA_URL else MockOPAClient()`
    pattern, which silently allowed every request in production whenever
    OPA_URL was left unset — the opposite of "non-bypassable governance."
    """
    if opa_url:
        return OPAClient(opa_url)
    if dev_mode:
        return MockOPAClient()
    return FailClosedOPAClient()

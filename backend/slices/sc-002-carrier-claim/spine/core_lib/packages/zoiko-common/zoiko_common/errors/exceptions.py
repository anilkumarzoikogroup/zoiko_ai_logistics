"""Zoiko standard exception hierarchy."""
from __future__ import annotations


class ZoikoError(Exception):
    """Base class for all Zoiko domain errors."""
    http_status: int = 500

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code

    def to_dict(self) -> dict:
        return {"error": self.code, "detail": self.message}


class DuplicateError(ZoikoError):
    """Idempotency violation — the same Idempotency-Key was already processed."""
    http_status = 409

    def __init__(self, message: str = "Duplicate request") -> None:
        super().__init__(message, "DUPLICATE_REQUEST")


class NotFoundError(ZoikoError):
    """Requested aggregate does not exist for this tenant."""
    http_status = 404

    def __init__(self, resource: str, id: str) -> None:
        super().__init__(f"{resource} '{id}' not found", "NOT_FOUND")


class ValidationError(ZoikoError):
    """Domain validation failed — invoice does not meet contract constraints."""
    http_status = 422

    def __init__(self, message: str) -> None:
        super().__init__(message, "VALIDATION_FAILED")


class SoDViolationError(ZoikoError):
    """Separation of Duties violation — proposer and approver must be different."""
    http_status = 403

    def __init__(self, actor_sub: str, proposer_sub: str) -> None:
        super().__init__(
            f"SoD violation: actor '{actor_sub}' cannot approve own proposal by '{proposer_sub}'",
            "SOD_VIOLATION",
        )


class TokenExpiredError(ZoikoError):
    """Governance token TTL has elapsed — execution window closed."""
    http_status = 410

    def __init__(self, token_id: str) -> None:
        super().__init__(f"Token '{token_id}' has expired", "TOKEN_EXPIRED")


class TokenConsumedError(ZoikoError):
    """Token already consumed — duplicate execution attempt blocked."""
    http_status = 409

    def __init__(self, token_id: str) -> None:
        super().__init__(f"Token '{token_id}' already consumed", "TOKEN_CONSUMED")


class OPADeniedError(ZoikoError):
    """OPA policy denied the request. Fail-closed — never permit on error."""
    http_status = 403

    def __init__(self, policy: str, reason: str = "") -> None:
        super().__init__(f"OPA policy '{policy}' denied: {reason}", "OPA_DENIED")


class GateFailureError(ZoikoError):
    """One of the 8 execution gates failed — no dispatch until resolved."""
    http_status = 422

    def __init__(self, gate: int, gate_name: str, reason: str) -> None:
        super().__init__(
            f"Gate {gate} ({gate_name}) failed: {reason}",
            f"GATE_{gate}_FAILURE",
        )
        self.gate = gate
        self.gate_name = gate_name

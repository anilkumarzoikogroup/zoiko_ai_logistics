"""Zoiko standard exception hierarchy."""
from zoiko_common.errors.exceptions import (
    ZoikoError,
    DuplicateError,
    NotFoundError,
    ValidationError,
    SoDViolationError,
    TokenExpiredError,
    TokenConsumedError,
    OPADeniedError,
    GateFailureError,
)

__all__ = [
    "ZoikoError", "DuplicateError", "NotFoundError", "ValidationError",
    "SoDViolationError", "TokenExpiredError", "TokenConsumedError",
    "OPADeniedError", "GateFailureError",
]

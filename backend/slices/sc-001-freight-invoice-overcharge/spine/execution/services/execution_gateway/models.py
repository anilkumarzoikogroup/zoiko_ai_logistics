"""Phase 4 — Execution Gateway Pydantic models."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ExecutionRequest:
    """Inputs required to start the 8-gate execution flow."""
    token_id:   str
    tenant_id:  str
    actor_sub:  str


@dataclass
class GateResult:
    gate:    int
    name:    str
    passed:  bool
    detail:  str


@dataclass
class ExecutionEnvelope:
    """Persisted after all 8 gates pass."""
    envelope_id:   str
    token_id:      str
    tenant_id:     str
    case_id:       str
    scope:         str
    amount:        float
    currency:      str
    actor_sub:     str
    gate_results:  list[GateResult]
    dispatched_at: datetime
    status:        str   # DISPATCHED | FAILED | ROLLED_BACK
    connector_ref: Optional[str] = None

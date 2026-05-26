"""
Approval queue with Separation of Duties (SoD) enforcement.

Manages manual approval tasks that require two distinct actors:
  1. Proposer submits the task.
  2. Approver (≠ proposer) approves or rejects.

SoD rule: actor_sub of approve() MUST differ from proposer_sub.
Raises SoDViolationError otherwise (mirrors Phase-3 governance behaviour).

In-memory store for dev/test. Prod: back by DB table.
"""
from __future__ import annotations

import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List


class SoDViolationError(ValueError):
    pass


@dataclass
class ApprovalTask:
    task_id:      str
    envelope_id:  str
    tenant_id:    str
    proposer_sub: str
    description:  str
    amount_usd:   float
    state:        str   # PENDING | APPROVED | REJECTED | EXPIRED
    created_at:   datetime
    decided_at:   Optional[datetime] = None
    actor_sub:    Optional[str]      = None
    decision:     Optional[str]      = None
    reason:       Optional[str]      = None


@dataclass
class ApprovalResult:
    task_id:   str
    decision:  str   # APPROVED | REJECTED
    actor_sub: str
    decided_at: datetime


_store: dict[str, ApprovalTask] = {}
_mu = threading.Lock()


def create_task(
    envelope_id:  str,
    tenant_id:    str,
    proposer_sub: str,
    amount_usd:   float,
    description:  str = "",
) -> ApprovalTask:
    task = ApprovalTask(
        task_id      = str(uuid.uuid4()),
        envelope_id  = envelope_id,
        tenant_id    = tenant_id,
        proposer_sub = proposer_sub,
        description  = description or f"Approve credit USD {amount_usd:.2f}",
        amount_usd   = amount_usd,
        state        = "PENDING",
        created_at   = datetime.now(timezone.utc),
    )
    with _mu:
        _store[task.task_id] = task
    return task


def approve(task_id: str, actor_sub: str, decision: str, reason: str = "") -> ApprovalResult:
    """
    Approve or reject a pending task.
    Raises SoDViolationError if actor_sub == proposer_sub.
    Raises ValueError if task not found or already decided.
    """
    with _mu:
        task = _store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")
        if task.state != "PENDING":
            raise ValueError(f"Task '{task_id}' is '{task.state}', not PENDING")
        if actor_sub == task.proposer_sub:
            raise SoDViolationError(
                f"Separation of Duties violation: actor_sub '{actor_sub}' "
                f"cannot be the same as proposer_sub '{task.proposer_sub}'"
            )
        if decision not in ("APPROVED", "REJECTED"):
            raise ValueError(f"decision must be APPROVED or REJECTED, got '{decision}'")

        now = datetime.now(timezone.utc)
        task.state      = decision
        task.actor_sub  = actor_sub
        task.decision   = decision
        task.reason     = reason
        task.decided_at = now

    return ApprovalResult(
        task_id    = task_id,
        decision   = decision,
        actor_sub  = actor_sub,
        decided_at = now,
    )


def get_task(task_id: str) -> Optional[ApprovalTask]:
    with _mu:
        return _store.get(task_id)


def list_pending(tenant_id: str) -> List[ApprovalTask]:
    with _mu:
        return [t for t in _store.values()
                if t.tenant_id == tenant_id and t.state == "PENDING"]

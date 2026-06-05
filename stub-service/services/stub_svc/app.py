"""
Stub Service FastAPI gateway — port 8013.

Provides fail-closed stubs for external dependencies that gates 6/7 call:
  Gate 6: Sanctions screening
  Gate 7: FX rate lock
  + GL journal posting (post-execution)
  + Approval queue with SoD (for manual review workflows)

Routes:
  GET  /health
  POST /v1/sanctions/screen               — screen actor against sanctions list
  POST /v1/fx/lock                        — acquire FX rate lock
  POST /v1/fx/validate                    — validate an existing lock
  POST /v1/gl/journal                     — post GL journal entry
  GET  /v1/gl/journal/{tenant_id}         — list GL entries for tenant
  POST /v1/approval/tasks                 — create approval task
  GET  /v1/approval/tasks/{task_id}       — get task status
  POST /v1/approval/tasks/{task_id}/decide — approve or reject task (SoD enforced)
  GET  /v1/approval/tasks/pending/{tenant_id} — list pending tasks
"""
from __future__ import annotations

from fastapi import FastAPI, APIRouter, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.stub_svc.sanctions     import screen
from services.stub_svc.fx_lock       import acquire as fx_acquire, validate as fx_validate
from services.stub_svc.gl_journal    import post_entry, get_entries
from services.stub_svc.approval_queue import (
    create_task, approve, get_task, list_pending, SoDViolationError,
)

app = FastAPI(title="Zoiko Stub Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "service": "stub-service", "version": "1.0.0"}


# ── Sanctions ─────────────────────────────────────────────────────────────────

class SanctionsBody(BaseModel):
    actor_sub: str
    tenant_id: str


@v1.post("/sanctions/screen", tags=["sanctions"])
def sanctions_screen(body: SanctionsBody):
    result = screen(body.actor_sub, body.tenant_id)
    if not result.cleared:
        raise HTTPException(status_code=403, detail=result.reason)
    return {"actor": result.actor, "cleared": result.cleared, "reason": result.reason}


# ── FX Lock ───────────────────────────────────────────────────────────────────

class FXLockBody(BaseModel):
    amount:      float
    currency:    str
    envelope_id: str


class FXValidateBody(BaseModel):
    lock_id:    str
    amount_usd: float


@v1.post("/fx/lock", tags=["fx"])
def fx_lock(body: FXLockBody):
    result = fx_acquire(body.amount, body.currency, body.envelope_id)
    if not result.acquired:
        raise HTTPException(status_code=503, detail=result.reason)
    return {
        "acquired":           result.acquired,
        "lock_id":            result.lock_id,
        "locked_rate":        result.locked_rate,
        "locked_amount_usd":  result.locked_amount_usd,
        "currency":           result.currency,
        "reason":             result.reason,
    }


@v1.post("/fx/validate", tags=["fx"])
def fx_lock_validate(body: FXValidateBody):
    valid = fx_validate(body.lock_id, body.amount_usd)
    return {"lock_id": body.lock_id, "valid": valid}


# ── GL Journal ────────────────────────────────────────────────────────────────

class GLJournalBody(BaseModel):
    envelope_id: str
    tenant_id:   str
    amount_usd:  float
    description: str = "Freight overcharge recovery credit"


@v1.post("/gl/journal", status_code=201, tags=["gl"])
def gl_post(body: GLJournalBody, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    result = post_entry(body.envelope_id, body.tenant_id, body.amount_usd, body.description)
    if not result.posted:
        raise HTTPException(status_code=503, detail=result.reason)
    return {"posted": result.posted, "entry_id": result.entry_id, "reason": result.reason}


@v1.get("/gl/journal/{tenant_id}", tags=["gl"])
def gl_list(tenant_id: str):
    entries = get_entries(tenant_id)
    return [
        {
            "entry_id":       e.entry_id,
            "envelope_id":    e.envelope_id,
            "debit_account":  e.debit_account,
            "credit_account": e.credit_account,
            "amount_usd":     e.amount_usd,
            "status":         e.status,
            "posted_at":      e.posted_at.isoformat(),
        }
        for e in entries
    ]


# ── Approval Queue ────────────────────────────────────────────────────────────

class ApprovalCreateBody(BaseModel):
    envelope_id:  str
    tenant_id:    str
    proposer_sub: str
    amount_usd:   float
    description:  str = ""


class ApprovalDecideBody(BaseModel):
    actor_sub: str
    decision:  str   # APPROVED | REJECTED
    reason:    str = ""


@v1.post("/approval/tasks", status_code=201, tags=["approval"])
def approval_create(body: ApprovalCreateBody, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    task = create_task(body.envelope_id, body.tenant_id, body.proposer_sub, body.amount_usd, body.description)
    return {"task_id": task.task_id, "state": task.state, "created_at": task.created_at.isoformat()}


@v1.get("/approval/tasks/{task_id}", tags=["approval"])
def approval_get(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id":      task.task_id,
        "state":        task.state,
        "proposer_sub": task.proposer_sub,
        "amount_usd":   task.amount_usd,
        "description":  task.description,
        "created_at":   task.created_at.isoformat(),
        "decided_at":   task.decided_at.isoformat() if task.decided_at else None,
        "actor_sub":    task.actor_sub,
        "decision":     task.decision,
    }


@v1.post("/approval/tasks/{task_id}/decide", tags=["approval"])
def approval_decide(
    task_id: str,
    body: ApprovalDecideBody,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    try:
        result = approve(task_id, body.actor_sub, body.decision, body.reason)
    except SoDViolationError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "task_id":    result.task_id,
        "decision":   result.decision,
        "actor_sub":  result.actor_sub,
        "decided_at": result.decided_at.isoformat(),
    }


@v1.get("/approval/tasks/pending/{tenant_id}", tags=["approval"])
def approval_list_pending(tenant_id: str):
    tasks = list_pending(tenant_id)
    return [
        {"task_id": t.task_id, "amount_usd": t.amount_usd, "proposer_sub": t.proposer_sub, "state": t.state}
        for t in tasks
    ]


# ── Route registration ────────────────────────────────────────────────────────
app.include_router(v1, prefix="/v1")

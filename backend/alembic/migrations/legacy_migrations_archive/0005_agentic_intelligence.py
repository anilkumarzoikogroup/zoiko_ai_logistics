"""Agentic Intelligence — reasoning traces, tool permissions, approval thresholds.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-27

New tables:
  reasoning_traces       — per-step agent reasoning log (audit trail)
  agent_tool_permissions — tool registry: allowed/denied + requires_approval flag
  approval_thresholds    — per-tenant threshold config (auto/single/dual routing)
  approval_requests      — tracks approval level + deadline per proposal
  approval_decisions     — APPEND-ONLY human decisions on approval requests

Column additions:
  decision_proposals.reasoning_trace_id — FK to reasoning_traces
  decision_proposals.governance_envelope — JSONB formal governance envelope
  approval_tasks.approval_level          — AUTO | SINGLE | DUAL
  approval_tasks.deadline_at             — escalation deadline
"""
from __future__ import annotations
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── reasoning_traces ────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE reasoning_traces (
        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id      UUID NOT NULL REFERENCES tenants(id),
        case_id        UUID NOT NULL REFERENCES cases(id),
        agent_id       TEXT NOT NULL,
        steps          JSONB NOT NULL DEFAULT '[]',
        tools_used     TEXT[] NOT NULL DEFAULT '{}',
        evidence_refs  TEXT[] NOT NULL DEFAULT '{}',
        confidence     NUMERIC(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
        action_intent  TEXT NOT NULL,
        policy_version TEXT NOT NULL DEFAULT 'v1.0.0',
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    op.execute("ALTER TABLE reasoning_traces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE reasoning_traces FORCE ROW LEVEL SECURITY")

    # ── agent_tool_permissions ───────────────────────────────────────────────
    op.execute("""
    CREATE TABLE agent_tool_permissions (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tool_name         TEXT NOT NULL UNIQUE,
        allowed           BOOLEAN NOT NULL DEFAULT TRUE,
        description       TEXT NOT NULL DEFAULT '',
        requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")

    op.execute("""
    INSERT INTO agent_tool_permissions
        (tool_name, allowed, description, requires_approval)
    VALUES
        ('read_evidence_bundle',    TRUE,  'Read evidence items from a bundle (read-only)',                   FALSE),
        ('read_contract_rates',     TRUE,  'Fetch contract rates for validation (read-only)',                 FALSE),
        ('read_case_metadata',      TRUE,  'Read case state and invoice metadata (read-only)',                FALSE),
        ('call_carrier_api',        FALSE, 'Direct carrier API call — only Execution Gateway permitted',     FALSE),
        ('issue_credit_memo',       FALSE, 'Issue credit memo directly — only Phase 4 Execution Gateway',   FALSE),
        ('write_canonical_invoice', FALSE, 'Modify canonical invoice — agent is read-only',                 FALSE)
    """)

    # ── approval_thresholds ─────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE approval_thresholds (
        id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id            UUID NOT NULL REFERENCES tenants(id),
        currency             TEXT NOT NULL DEFAULT 'INR',
        auto_approve_below   NUMERIC(15,2),
        dual_auth_above      NUMERIC(15,2),
        escalate_after_hours INTEGER NOT NULL DEFAULT 24,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (tenant_id, currency)
    )""")
    op.execute("ALTER TABLE approval_thresholds ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE approval_thresholds FORCE ROW LEVEL SECURITY")

    # ── approval_requests ───────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE approval_requests (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        proposal_id     UUID NOT NULL REFERENCES decision_proposals(id),
        approval_level  TEXT NOT NULL CHECK (approval_level IN ('AUTO','SINGLE','DUAL')),
        status          TEXT NOT NULL DEFAULT 'PENDING'
                          CHECK (status IN ('PENDING','APPROVED','REJECTED','ESCALATED','TIMEOUT')),
        approver_1_sub  TEXT,
        approver_2_sub  TEXT,
        requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        deadline_at     TIMESTAMPTZ NOT NULL,
        actioned_at     TIMESTAMPTZ
    )""")
    op.execute("ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE approval_requests FORCE ROW LEVEL SECURITY")

    # ── approval_decisions (APPEND-ONLY) ────────────────────────────────────
    op.execute("""
    CREATE TABLE approval_decisions (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id           UUID NOT NULL REFERENCES tenants(id),
        approval_request_id UUID NOT NULL REFERENCES approval_requests(id),
        actor_sub           TEXT NOT NULL,
        decision            TEXT NOT NULL CHECK (decision IN ('APPROVE','REJECT','ESCALATE')),
        rationale           TEXT,
        decided_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    op.execute("ALTER TABLE approval_decisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE approval_decisions FORCE ROW LEVEL SECURITY")

    # ── Backfill columns on existing tables ─────────────────────────────────
    op.execute("""
        ALTER TABLE decision_proposals
            ADD COLUMN reasoning_trace_id UUID REFERENCES reasoning_traces(id),
            ADD COLUMN governance_envelope JSONB
    """)

    op.execute("""
        ALTER TABLE approval_tasks
            ADD COLUMN approval_level TEXT DEFAULT 'SINGLE'
                CHECK (approval_level IN ('AUTO','SINGLE','DUAL')),
            ADD COLUMN deadline_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE approval_tasks DROP COLUMN IF EXISTS deadline_at")
    op.execute("ALTER TABLE approval_tasks DROP COLUMN IF EXISTS approval_level")
    op.execute("ALTER TABLE decision_proposals DROP COLUMN IF EXISTS governance_envelope")
    op.execute("ALTER TABLE decision_proposals DROP COLUMN IF EXISTS reasoning_trace_id")
    for tbl in [
        "approval_decisions", "approval_requests", "approval_thresholds",
        "agent_tool_permissions", "reasoning_traces",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")

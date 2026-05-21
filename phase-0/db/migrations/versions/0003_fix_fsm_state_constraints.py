"""Fix FSM state and outcome CHECK constraints to match spec §7.5.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21

Changes:
  - cases.state: replaces old OPENED/EVIDENCE_GATHERING/… set with spec-aligned
    NEW/EVIDENCE_PENDING/FINDING_GENERATED/APPROVAL_PENDING/EXECUTION_READY/
    DISPATCHED/OUTCOME_RECORDED/CLOSED/ABORTED
  - cases.state DEFAULT: 'OPENED' → 'NEW'
  - governance_decisions.outcome: APPROVED/REJECTED → EXECUTION_READY/ABORTED
"""
from __future__ import annotations
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── cases.state: migrate existing rows first ─────────────────────────
    op.execute("ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_state_check")
    op.execute("""
        UPDATE cases SET state = CASE state
            WHEN 'OPENED'             THEN 'NEW'
            WHEN 'EVIDENCE_GATHERING' THEN 'EVIDENCE_PENDING'
            WHEN 'UNDER_REVIEW'       THEN 'FINDING_GENERATED'
            WHEN 'PENDING_APPROVAL'   THEN 'APPROVAL_PENDING'
            WHEN 'APPROVED'           THEN 'EXECUTION_READY'
            WHEN 'REJECTED'           THEN 'ABORTED'
            WHEN 'EXECUTED'           THEN 'DISPATCHED'
            WHEN 'RECONCILED'         THEN 'OUTCOME_RECORDED'
            ELSE state
        END
    """)
    op.execute("""
        ALTER TABLE cases
            ADD CONSTRAINT cases_state_check
            CHECK (state IN (
                'NEW','EVIDENCE_PENDING','FINDING_GENERATED','APPROVAL_PENDING',
                'EXECUTION_READY','DISPATCHED','OUTCOME_RECORDED','CLOSED','ABORTED'
            ))
    """)
    op.execute("ALTER TABLE cases ALTER COLUMN state SET DEFAULT 'NEW'")

    # ── governance_decisions.outcome: migrate existing rows first ─────────
    op.execute(
        "ALTER TABLE governance_decisions "
        "DROP CONSTRAINT IF EXISTS governance_decisions_outcome_check"
    )
    op.execute("""
        UPDATE governance_decisions SET outcome = CASE outcome
            WHEN 'APPROVED' THEN 'EXECUTION_READY'
            WHEN 'REJECTED' THEN 'ABORTED'
            ELSE outcome
        END
    """)
    op.execute("""
        ALTER TABLE governance_decisions
            ADD CONSTRAINT governance_decisions_outcome_check
            CHECK (outcome IN ('EXECUTION_READY','ABORTED'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_state_check")
    op.execute("""
        ALTER TABLE cases
            ADD CONSTRAINT cases_state_check
            CHECK (state IN (
                'OPENED','EVIDENCE_GATHERING','UNDER_REVIEW',
                'PENDING_APPROVAL','APPROVED','REJECTED','EXECUTED',
                'RECONCILED','CLOSED'
            ))
    """)
    op.execute("ALTER TABLE cases ALTER COLUMN state SET DEFAULT 'OPENED'")

    op.execute(
        "ALTER TABLE governance_decisions "
        "DROP CONSTRAINT IF EXISTS governance_decisions_outcome_check"
    )
    op.execute("""
        ALTER TABLE governance_decisions
            ADD CONSTRAINT governance_decisions_outcome_check
            CHECK (outcome IN ('APPROVED','REJECTED'))
    """)

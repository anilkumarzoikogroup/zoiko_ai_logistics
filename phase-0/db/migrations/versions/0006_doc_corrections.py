"""Document corrections — approval chain hash, policy version binding, action intents,
variance records.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-27

Changes:
  governance_decisions   ADD approval_chain_hash BYTEA, policy_version TEXT
  governance_tokens      ADD approval_chain_hash BYTEA, policy_version TEXT
  decision_proposals     ADD action_intent_id UUID → action_intents(id)
  action_intents         NEW — one intent per proposal (owned by reasoning/governance)
  variance_records       NEW — reconciliation variance log (A-11: no close with open variance)
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, BYTEA


revision      = "0006"
down_revision = "0005"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── action_intents ───────────────────────────────────────────────────────
    # One record per decision_proposal — captures the agent's declared intent
    # before human approval so the token can bind to it.
    op.execute("""
    CREATE TABLE action_intents (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id        UUID NOT NULL REFERENCES tenants(id),
        case_id          UUID NOT NULL REFERENCES cases(id),
        proposal_id      UUID,
        action_type      TEXT NOT NULL,
        policy_version   TEXT NOT NULL DEFAULT 'v1.0.0',
        agent_id         TEXT NOT NULL DEFAULT 'zoiko.agent.freight_dispute.v1',
        declared_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        rationale        TEXT
    )""")
    op.execute("ALTER TABLE action_intents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE action_intents FORCE ROW LEVEL SECURITY")

    # ── decision_proposals: action_intent_id ────────────────────────────────
    op.execute("""
        ALTER TABLE decision_proposals
            ADD COLUMN action_intent_id UUID REFERENCES action_intents(id)
    """)

    # ── governance_decisions: approval chain hash + policy version ──────────
    # approval_chain_hash = SHA-256(proposer_sub || actor_sub || decision_hash)
    # policy_version      = version string from the active policy bundle
    op.execute("""
        ALTER TABLE governance_decisions
            ADD COLUMN approval_chain_hash BYTEA,
            ADD COLUMN policy_version      TEXT NOT NULL DEFAULT 'v1.0.0'
    """)

    # ── governance_tokens: bind approval chain hash + policy version ─────────
    # Non-bypassable rule (doc §5.1): token must bind approval_chain_hash
    # and policy_version so Phase 4 can verify the full chain.
    op.execute("""
        ALTER TABLE governance_tokens
            ADD COLUMN approval_chain_hash BYTEA,
            ADD COLUMN policy_version      TEXT NOT NULL DEFAULT 'v1.0.0'
    """)

    # ── variance_records ─────────────────────────────────────────────────────
    # A-11: no case can close with an unresolved variance.
    # Records discrepancies found during reconciliation.
    op.execute("""
    CREATE TABLE variance_records (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        case_id         UUID NOT NULL REFERENCES cases(id),
        proposal_id     UUID REFERENCES decision_proposals(id),
        variance_type   TEXT NOT NULL CHECK (variance_type IN
                            ('AMOUNT_MISMATCH','CARRIER_MISMATCH',
                             'CURRENCY_MISMATCH','OVERCHARGE_DELTA','OTHER')),
        expected_value  NUMERIC(15,4),
        actual_value    NUMERIC(15,4),
        delta           NUMERIC(15,4),
        status          TEXT NOT NULL DEFAULT 'OPEN'
                          CHECK (status IN ('OPEN','RESOLVED','WAIVED')),
        resolved_by     TEXT,
        resolved_at     TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    op.execute("ALTER TABLE variance_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE variance_records FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS variance_records CASCADE")
    op.execute("ALTER TABLE governance_tokens DROP COLUMN IF EXISTS policy_version")
    op.execute("ALTER TABLE governance_tokens DROP COLUMN IF EXISTS approval_chain_hash")
    op.execute("ALTER TABLE governance_decisions DROP COLUMN IF EXISTS policy_version")
    op.execute("ALTER TABLE governance_decisions DROP COLUMN IF EXISTS approval_chain_hash")
    op.execute("ALTER TABLE decision_proposals DROP COLUMN IF EXISTS action_intent_id")
    op.execute("DROP TABLE IF EXISTS action_intents CASCADE")

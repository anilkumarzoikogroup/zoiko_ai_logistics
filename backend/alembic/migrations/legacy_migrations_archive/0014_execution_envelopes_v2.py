"""Align execution_envelopes schema with Phase 4 handler expectations.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-01

Changes:
  execution_envelopes:
    - ADD scope, amount, currency, actor_sub, connector_ref columns
    - Make env_hash, signature, kid, case_id nullable
      (Phase 4 inline handler computes env_hash later; case_id can be NULL
       when token has no linked case)
"""
from __future__ import annotations
from alembic import op

revision      = "0014"
down_revision = "0013"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Add new operational columns
    op.execute("""
        ALTER TABLE execution_envelopes
            ADD COLUMN IF NOT EXISTS scope         TEXT,
            ADD COLUMN IF NOT EXISTS amount        NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS currency      TEXT DEFAULT 'INR',
            ADD COLUMN IF NOT EXISTS actor_sub     TEXT,
            ADD COLUMN IF NOT EXISTS connector_ref TEXT,
            ALTER COLUMN case_id   DROP NOT NULL
    """)
    # NOTE: env_hash, signature, kid remain NOT NULL — they are cryptographic
    # integrity fields and must never be nullable in production.
    # The inline execute handler in Phase 2 fills them with a computed hash
    # and dev-mode signature values.


def downgrade() -> None:
    op.execute("""
        ALTER TABLE execution_envelopes
            DROP COLUMN IF EXISTS scope,
            DROP COLUMN IF EXISTS amount,
            DROP COLUMN IF EXISTS currency,
            DROP COLUMN IF EXISTS actor_sub,
            DROP COLUMN IF EXISTS connector_ref
    """)

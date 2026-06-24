"""Ensure findings AI columns are nullable (fix for CI NOT NULL constraint).

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-30

Anil's handler created ai_confidence with NOT NULL DEFAULT 0.0 via _ensure_tables().
This migration explicitly drops any NOT NULL constraint so the handler can
insert NULL when GROQ_API_KEY is not configured.
"""
from __future__ import annotations
from alembic import op

revision      = "0012"
down_revision = "0011"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE findings
            ADD COLUMN IF NOT EXISTS ai_confidence NUMERIC(5,4),
            ADD COLUMN IF NOT EXISTS risk_level     TEXT,
            ADD COLUMN IF NOT EXISTS ai_reasoning   TEXT
    """)
    # Drop NOT NULL constraint if it exists (from any previous schema)
    op.execute("ALTER TABLE findings ALTER COLUMN ai_confidence DROP NOT NULL")
    op.execute("ALTER TABLE findings ALTER COLUMN risk_level     DROP NOT NULL")
    op.execute("ALTER TABLE findings ALTER COLUMN ai_reasoning   DROP NOT NULL")


def downgrade() -> None:
    pass

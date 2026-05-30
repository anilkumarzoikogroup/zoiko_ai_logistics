"""Add ai_confidence, risk_level, ai_reasoning to findings table.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-29

Adds Groq AI supplementary fields to findings.
Official confidence (SC001 = 0.96) is never changed by AI.
"""
from __future__ import annotations
from alembic import op

revision      = "0011"
down_revision = "0010"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE findings
            ADD COLUMN IF NOT EXISTS ai_confidence NUMERIC(5,4),
            ADD COLUMN IF NOT EXISTS risk_level     TEXT
                CHECK (risk_level IN ('HIGH', 'MEDIUM', 'LOW')),
            ADD COLUMN IF NOT EXISTS ai_reasoning   TEXT
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE findings
            DROP COLUMN IF EXISTS ai_confidence,
            DROP COLUMN IF EXISTS risk_level,
            DROP COLUMN IF EXISTS ai_reasoning
    """)

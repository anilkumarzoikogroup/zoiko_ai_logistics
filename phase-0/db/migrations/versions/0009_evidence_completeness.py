"""0009 — evidence bundle completeness status

Adds completeness_status to evidence_bundles so that the reasoning service
can enforce T-006: proposal creation is blocked until the bundle is explicitly
sealed (marked COMPLETE) by an authorised analyst.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-27
"""
from __future__ import annotations
from alembic import op

revision      = "0009"
down_revision = "0008"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE evidence_bundles
        ADD COLUMN IF NOT EXISTS completeness_status TEXT NOT NULL
            DEFAULT 'INCOMPLETE'
            CHECK (completeness_status IN ('INCOMPLETE', 'COMPLETE'))
    """)
    op.execute("""
        COMMENT ON COLUMN evidence_bundles.completeness_status IS
        'INCOMPLETE = still accepting items; COMPLETE = sealed, reasoning allowed'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE evidence_bundles DROP COLUMN IF EXISTS completeness_status")

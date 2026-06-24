"""Add predecessor_version_hash to canonical_invoices.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-01

Enables append-only version chain:
  Each new canonical invoice stores the SHA-256 hash of the previous
  version so the full history is cryptographically linked and tamper-evident.
  NULL = first version for that invoice_number.
"""
from __future__ import annotations
from alembic import op

revision      = "0015"
down_revision = "0014"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE canonical_invoices
            ADD COLUMN IF NOT EXISTS predecessor_version_hash BYTEA
    """)
    op.execute("""
        COMMENT ON COLUMN canonical_invoices.predecessor_version_hash IS
        'SHA-256 of the previous canonical_hash for this invoice_number. NULL for first version.'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE canonical_invoices DROP COLUMN IF EXISTS predecessor_version_hash")

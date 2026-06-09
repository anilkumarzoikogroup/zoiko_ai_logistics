"""Add invoice_date, transport_mode, charge_lines to canonical_invoices;
   add mode, equipment_type to canonical_shipments.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-09
"""
from __future__ import annotations
from alembic import op

revision      = "0016"
down_revision = "0015"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE canonical_invoices
            ADD COLUMN IF NOT EXISTS invoice_date   TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS transport_mode TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS charge_lines   JSONB NOT NULL DEFAULT '[]'
    """)
    op.execute("""
        ALTER TABLE canonical_shipments
            ADD COLUMN IF NOT EXISTS mode           TEXT NOT NULL DEFAULT 'TRUCKLOAD',
            ADD COLUMN IF NOT EXISTS equipment_type TEXT NOT NULL DEFAULT ''
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE canonical_invoices
            DROP COLUMN IF EXISTS invoice_date,
            DROP COLUMN IF EXISTS transport_mode,
            DROP COLUMN IF EXISTS charge_lines
    """)
    op.execute("""
        ALTER TABLE canonical_shipments
            DROP COLUMN IF EXISTS mode,
            DROP COLUMN IF EXISTS equipment_type
    """)

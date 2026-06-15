"""Deduplicate canonical_shipments and add UNIQUE(invoice_id).

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-12

canonicalize_invoice() inserts a canonical_shipments row with
ON CONFLICT DO NOTHING, but there was no unique constraint for that
clause to act on — every re-submission of an already-seen invoice
(correctly deduped at the canonical_invoices/cases level) still added
another canonical_shipments row for the same invoice_id. The case list
LEFT JOINs canonical_shipments, so each extra row fanned out into a
duplicate case row in the UI.

This migration removes the extra duplicate rows (keeping the earliest
per invoice_id) and adds UNIQUE(invoice_id) so ON CONFLICT DO NOTHING
becomes effective going forward.
"""
from __future__ import annotations
from alembic import op

revision      = "0025"
down_revision = "0024"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM canonical_shipments cs
        WHERE cs.id NOT IN (
            SELECT (array_agg(id ORDER BY created_at ASC))[1]
            FROM canonical_shipments
            GROUP BY invoice_id
        )
    """)
    op.execute("""
        ALTER TABLE canonical_shipments
            ADD CONSTRAINT uq_canonical_shipments_invoice_id UNIQUE (invoice_id)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE canonical_shipments
            DROP CONSTRAINT IF EXISTS uq_canonical_shipments_invoice_id
    """)

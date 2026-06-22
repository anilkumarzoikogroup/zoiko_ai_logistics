"""SC-002 — add claim_reference to claims (mirrors canonical_invoices.invoice_number).

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-22

claims had no human-referenceable business key for canonicalize_claim() to
dedupe on, unlike canonical_invoices.invoice_number. This adds one column
and a matching UNIQUE(tenant_id, claim_reference), following the exact same
shape as canonical_invoices_tenant_id_invoice_number_key.
"""
from alembic import op

revision      = "0042"
down_revision = "0041"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("ALTER TABLE claims ADD COLUMN IF NOT EXISTS claim_reference TEXT NOT NULL DEFAULT ''")
    op.execute("CREATE UNIQUE INDEX uq_claims_tenant_reference ON claims(tenant_id, claim_reference) WHERE claim_reference <> ''")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_claims_tenant_reference")
    op.execute("ALTER TABLE claims DROP COLUMN IF EXISTS claim_reference")

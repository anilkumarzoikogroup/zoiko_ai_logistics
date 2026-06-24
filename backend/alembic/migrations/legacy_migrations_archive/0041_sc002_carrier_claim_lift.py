"""SC-002 increment 1 — lift cases to carry a claim, not only an invoice.

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-22

The SC-001 build proved the platform spine (ingest -> canonical -> case ->
evidence -> reasoning -> governance -> token -> execution -> reconciliation
-> ACR). Per the engineering build map: "do not start SC-002 implementation
before SC-001 runs against lifted platform primitives." This migration is
that lift, scoped narrowly:

  - cases.invoice_id becomes nullable; cases gains a nullable claim_id FK
    and a case_type discriminator. A CHECK constraint enforces exactly one
    of (invoice_id, claim_id) is set, matching case_type. Existing SC-001
    rows are untouched — invoice_id stays populated, case_type backfills to
    'INVOICE_OVERCHARGE' by default. Zero behavior change for SC-001.
  - The old UNIQUE(tenant_id, invoice_id) is replaced by two partial unique
    indexes (one per case_type) so a tenant can have at most one case per
    invoice AND at most one case per claim, independently.
  - claims (created unused in migration 0019) gets a real status lifecycle,
    plus source_record_id/carrier_id/claim_hash so it can be canonicalized
    the same way canonical_invoices is.

NOT in scope here (flagged, not silently dropped): claim_lines, multi-round
counter-offer negotiation tracking, a real carrier-claim connector, and
claim-specific GET/report read endpoints.
"""
from alembic import op

revision      = "0041"
down_revision = "0040"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE claims ADD CONSTRAINT chk_claims_status CHECK (status IN (
            'OPEN','SUBMITTED','UNDER_CARRIER_REVIEW','COUNTERED',
            'PARTIALLY_ACCEPTED','ACCEPTED','REJECTED','WITHDRAWN','CLOSED'
        ))
    """)
    op.execute("ALTER TABLE claims ADD COLUMN IF NOT EXISTS source_record_id UUID REFERENCES source_records(id)")
    op.execute("ALTER TABLE claims ADD COLUMN IF NOT EXISTS carrier_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE claims ADD COLUMN IF NOT EXISTS claim_hash BYTEA")

    op.execute("ALTER TABLE cases ALTER COLUMN invoice_id DROP NOT NULL")
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS claim_id UUID REFERENCES claims(id)")
    op.execute("""
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_type TEXT NOT NULL DEFAULT 'INVOICE_OVERCHARGE'
            CHECK (case_type IN ('INVOICE_OVERCHARGE','CARRIER_CLAIM'))
    """)
    op.execute("""
        ALTER TABLE cases ADD CONSTRAINT chk_cases_subject CHECK (
            (case_type = 'INVOICE_OVERCHARGE' AND invoice_id IS NOT NULL AND claim_id IS NULL) OR
            (case_type = 'CARRIER_CLAIM'      AND claim_id   IS NOT NULL AND invoice_id IS NULL)
        )
    """)
    op.execute("ALTER TABLE cases DROP CONSTRAINT cases_tenant_id_invoice_id_key")
    op.execute("CREATE UNIQUE INDEX uq_cases_tenant_invoice ON cases(tenant_id, invoice_id) WHERE invoice_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_cases_tenant_claim ON cases(tenant_id, claim_id) WHERE claim_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_cases_tenant_claim")
    op.execute("DROP INDEX IF EXISTS uq_cases_tenant_invoice")
    op.execute("ALTER TABLE cases ADD CONSTRAINT cases_tenant_id_invoice_id_key UNIQUE (tenant_id, invoice_id)")
    op.execute("ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_cases_subject")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS case_type")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS claim_id")
    op.execute("ALTER TABLE cases ALTER COLUMN invoice_id SET NOT NULL")
    op.execute("ALTER TABLE claims DROP COLUMN IF EXISTS claim_hash")
    op.execute("ALTER TABLE claims DROP COLUMN IF EXISTS carrier_id")
    op.execute("ALTER TABLE claims DROP COLUMN IF EXISTS source_record_id")
    op.execute("ALTER TABLE claims DROP CONSTRAINT IF EXISTS chk_claims_status")

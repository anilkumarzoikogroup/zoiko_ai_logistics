"""Fix dedup_index column drift on environments where the table pre-dates 0020.

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-15

0020's CREATE TABLE IF NOT EXISTS dedup_index no-ops on environments where
this table already existed with an older shape, leaving columns like
payload_hash missing. Backfill any missing columns defensively and ensure
the (tenant_id, deduplication_key) unique constraint that write_dedup_index's
ON CONFLICT clause depends on is present.
"""

from alembic import op

revision      = "0032"
down_revision = "0031"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS dedup_index (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id),
            deduplication_key   TEXT NOT NULL,
            outcome             TEXT NOT NULL DEFAULT 'FIRST_SEEN'
                                CHECK (outcome IN ('FIRST_SEEN','DUPLICATE_OF','AMBIGUOUS')),
            source_record_id    UUID NOT NULL REFERENCES source_records(id),
            original_record_id  UUID REFERENCES source_records(id),
            external_source_ref TEXT,
            payload_hash        TEXT NOT NULL DEFAULT '',
            source_type         TEXT NOT NULL DEFAULT '',
            source_type_version TEXT NOT NULL DEFAULT 'v1',
            decided_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("ALTER TABLE dedup_index ADD COLUMN IF NOT EXISTS outcome TEXT NOT NULL DEFAULT 'FIRST_SEEN'")
    op.execute("ALTER TABLE dedup_index ADD COLUMN IF NOT EXISTS original_record_id UUID")
    op.execute("ALTER TABLE dedup_index ADD COLUMN IF NOT EXISTS external_source_ref TEXT")
    op.execute("ALTER TABLE dedup_index ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE dedup_index ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE dedup_index ADD COLUMN IF NOT EXISTS source_type_version TEXT NOT NULL DEFAULT 'v1'")
    op.execute("ALTER TABLE dedup_index ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")

    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE dedup_index
                ADD CONSTRAINT dedup_index_tenant_id_deduplication_key_key
                UNIQUE (tenant_id, deduplication_key);
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_dedup_index_tenant ON dedup_index (tenant_id, external_source_ref)")


def downgrade() -> None:
    # Backfilled columns were part of the original 0020 design — no-op
    # downgrade to avoid destroying data on environments where they
    # were genuinely missing only due to drift.
    pass

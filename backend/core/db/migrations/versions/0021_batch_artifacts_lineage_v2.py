"""
0021 — Batch artifacts + lineage v2 (transform contract).

New tables:
  - batch_artifacts  — one row per bulk upload, tracks per-record outcome counts
  - batch_records    — individual source_record_id rows belonging to a batch

Extends lineage_records with transform contract fields (§14):
  - transform_id, transform_version
  - transform_input_hash, transform_output_hash
  - reference_data_snapshot (JSONB)
  - transformed_at, transformed_by
  - canonical_records (JSONB array: [{type, id, payload_hash}])
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------ #
    # 1. batch_artifacts                                                   #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE IF NOT EXISTS batch_artifacts (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id             UUID NOT NULL REFERENCES tenants(id),
            channel               TEXT NOT NULL DEFAULT 'file_upload',
            submitted_by_user_id  UUID,
            declared_schema       TEXT NOT NULL DEFAULT 'freight-invoice-batch-v1',
            declared_record_count INTEGER NOT NULL DEFAULT 0,
            received_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            batch_payload_hash    TEXT,
            batch_payload_size_bytes BIGINT,
            processing_status     TEXT NOT NULL DEFAULT 'RECEIVED'
                                  CHECK (processing_status IN (
                                      'RECEIVED','STREAMING','PROCESSING',
                                      'COMPLETED','FAILED_PARTIAL','FAILED'
                                  )),
            total_records         INTEGER NOT NULL DEFAULT 0,
            first_seen_count      INTEGER NOT NULL DEFAULT 0,
            duplicate_count       INTEGER NOT NULL DEFAULT 0,
            ambiguous_count       INTEGER NOT NULL DEFAULT 0,
            rejected_count        INTEGER NOT NULL DEFAULT 0,
            quarantined_count     INTEGER NOT NULL DEFAULT 0,
            processed_count       INTEGER NOT NULL DEFAULT 0,
            completed_at          TIMESTAMPTZ,
            error_detail          TEXT,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_batch_artifacts_tenant ON batch_artifacts (tenant_id, received_at DESC)")

    # ------------------------------------------------------------------ #
    # 2. batch_records — per-record membership in a batch                  #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE IF NOT EXISTS batch_records (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id         UUID NOT NULL REFERENCES batch_artifacts(id),
            tenant_id        UUID NOT NULL REFERENCES tenants(id),
            source_record_id UUID REFERENCES source_records(id),
            record_index     INTEGER NOT NULL,
            external_source_ref TEXT,
            outcome          TEXT NOT NULL DEFAULT 'PENDING'
                             CHECK (outcome IN (
                                 'PENDING','FIRST_SEEN','DUPLICATE_OF',
                                 'AMBIGUOUS','REJECTED','QUARANTINED','PROCESSED'
                             )),
            error_detail     TEXT,
            processed_at     TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_batch_records_batch ON batch_records (batch_id, record_index)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_batch_records_outcome ON batch_records (batch_id, outcome)")

    # ------------------------------------------------------------------ #
    # 3. Extend lineage_records with transform contract fields (§14)       #
    # ------------------------------------------------------------------ #
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transform_id TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transform_version TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transform_input_hash TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transform_output_hash TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS reference_data_snapshot JSONB")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transformed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transformed_by TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS canonical_records JSONB")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS lineage_domain_tag TEXT DEFAULT 'zoiko/v1/lineage-record'")


def downgrade():
    op.execute("DROP TABLE IF EXISTS batch_records")
    op.execute("DROP TABLE IF EXISTS batch_artifacts")
    for col in ["transform_id","transform_version","transform_input_hash","transform_output_hash",
                "reference_data_snapshot","transformed_at","transformed_by",
                "canonical_records","lineage_domain_tag"]:
        op.execute(f"ALTER TABLE lineage_records DROP COLUMN IF EXISTS {col}")

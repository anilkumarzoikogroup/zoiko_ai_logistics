"""Reapply 0021's lineage_records transform fields + fix validation_results.rule_set_id type.

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-15

Two more "alembic_version advanced past the migration without its body
running" drift cases on CI's DB, same pattern as 0033/0020:

1. lineage_records is missing 0021's transform contract columns
   (transform_id, transform_version, transform_input_hash,
   transform_output_hash, reference_data_snapshot, transformed_at,
   transformed_by, canonical_records, lineage_domain_tag) — re-apply
   0021's ADD COLUMN IF NOT EXISTS statements verbatim.

2. validation_results.rule_set_id pre-exists as UUID (from before this
   migration chain), but 0020/0033's `ADD COLUMN IF NOT EXISTS rule_set_id
   TEXT` no-ops against it, and validation_svc writes a TEXT rule set
   identifier like 'carrier_invoice_validation' into it. Drop any
   constraints on the column and convert it to TEXT.
"""

from alembic import op

revision      = "0035"
down_revision = "0034"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── lineage_records — transform contract fields (from 0021) ───────────
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transform_id TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transform_version TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transform_input_hash TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transform_output_hash TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS reference_data_snapshot JSONB")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transformed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS transformed_by TEXT")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS canonical_records JSONB")
    op.execute("ALTER TABLE lineage_records ADD COLUMN IF NOT EXISTS lineage_domain_tag TEXT DEFAULT 'zoiko/v1/lineage-record'")

    # ── validation_results.rule_set_id — convert UUID drift column to TEXT ─
    op.execute("""
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            IF (SELECT data_type FROM information_schema.columns
                WHERE table_name='validation_results' AND column_name='rule_set_id') = 'uuid'
            THEN
                FOR r IN
                    SELECT con.conname
                    FROM pg_constraint con
                    JOIN pg_attribute att
                        ON att.attnum = ANY(con.conkey) AND att.attrelid = con.conrelid
                    WHERE con.conrelid = 'validation_results'::regclass
                      AND att.attname = 'rule_set_id'
                LOOP
                    EXECUTE format('ALTER TABLE validation_results DROP CONSTRAINT %I', r.conname);
                END LOOP;

                ALTER TABLE validation_results
                    ALTER COLUMN rule_set_id TYPE TEXT USING rule_set_id::text;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # No-op — re-applications of 0021 and a drift type fix; not safe to
    # destructively reverse.
    pass

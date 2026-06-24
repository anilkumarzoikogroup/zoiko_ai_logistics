"""Relax dedup_index.raw_payload_hash NOT NULL drift column.

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-15

Some environments' dedup_index table has an extra raw_payload_hash column
(not part of this model) with a NOT NULL constraint and no default. The
write_dedup_index() INSERT only sets payload_hash, so it fails with
NotNullViolation on raw_payload_hash. Drop the NOT NULL constraint,
swallowing undefined_column if the column isn't present.
"""

from alembic import op

revision      = "0034"
down_revision = "0033"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE dedup_index ALTER COLUMN raw_payload_hash DROP NOT NULL;
        EXCEPTION WHEN undefined_column THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    # No-op — re-adding NOT NULL on a drift column we don't own isn't safe.
    pass

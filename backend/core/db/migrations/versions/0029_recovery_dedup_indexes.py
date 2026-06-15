"""Clarification 06 Slice 1 — duplicate credit controls.

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-14

Adds partial unique indexes that prevent double-counting in the financial
recovery layer:
  - recovery_instruments: one row per (tenant_id, external_reference)
  - expected_recoveries: one *live* (superseded_by IS NULL) row per
    (tenant_id, case_id, authorization_decision_id)

Also makes expected_recoveries.superseded_by's FK deferrable: supersede()
must clear the old row's superseded_by-is-null "live" marker (to satisfy the
new unique index) in the same transaction as inserting the new row it points
to, which an IMMEDIATE FK can't allow in either order.
"""
from __future__ import annotations
from alembic import op

revision      = "0029"
down_revision = "0028"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX uq_recovery_instruments_tenant_extref
        ON recovery_instruments (tenant_id, external_reference)
        WHERE external_reference IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_expected_recoveries_tenant_case_authdec
        ON expected_recoveries (tenant_id, case_id, authorization_decision_id)
        WHERE authorization_decision_id IS NOT NULL AND superseded_by IS NULL
    """)
    op.execute("""
        ALTER TABLE expected_recoveries
        DROP CONSTRAINT expected_recoveries_superseded_by_fkey
    """)
    op.execute("""
        ALTER TABLE expected_recoveries
        ADD CONSTRAINT expected_recoveries_superseded_by_fkey
        FOREIGN KEY (superseded_by) REFERENCES expected_recoveries(id)
        DEFERRABLE INITIALLY DEFERRED
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE expected_recoveries
        DROP CONSTRAINT expected_recoveries_superseded_by_fkey
    """)
    op.execute("""
        ALTER TABLE expected_recoveries
        ADD CONSTRAINT expected_recoveries_superseded_by_fkey
        FOREIGN KEY (superseded_by) REFERENCES expected_recoveries(id)
    """)
    op.execute("DROP INDEX IF EXISTS uq_expected_recoveries_tenant_case_authdec")
    op.execute("DROP INDEX IF EXISTS uq_recovery_instruments_tenant_extref")

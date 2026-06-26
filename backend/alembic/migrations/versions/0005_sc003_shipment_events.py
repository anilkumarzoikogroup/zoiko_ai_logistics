"""SC-003 Shipment Exception / SLA Penalty — schema additions.

Adds:
  - cases.committed_eta          TIMESTAMPTZ  — carrier's promised delivery window
  - cases.actual_delivery        TIMESTAMPTZ  — when shipment actually arrived
  - cases.sla_breach_hours       NUMERIC      — hours beyond committed_eta
  - cases.sla_penalty_amount     NUMERIC      — calculated penalty amount
  - shipment_events              TABLE        — time-series shipment event log
  - sla_schedules                TABLE        — SLA contract terms per carrier/lane
  Extends cases_case_type_check to include 'SHIPMENT_EXCEPTION'.
  Extends chk_cases_subject to allow SHIPMENT_EXCEPTION rows.

Revision ID: 0005_sc003_shipment_events
Revises: 0004_sc002_fix
Create Date: 2026-06-25
"""
from __future__ import annotations

import os
from alembic import op

revision      = "0005_sc003_shipment_events"
down_revision = "0004_sc002_fix"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "sc003_shipment_events.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sla_schedules CASCADE")
    op.execute("DROP TABLE IF EXISTS shipment_events CASCADE")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS sla_penalty_amount")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS sla_breach_hours")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS actual_delivery")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS committed_eta")
    # Restore prior two-value constraint
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_case_type_check;
            ALTER TABLE cases ADD CONSTRAINT cases_case_type_check
                CHECK (case_type = ANY (ARRAY['INVOICE_OVERCHARGE','CARRIER_CLAIM']));
        EXCEPTION WHEN others THEN NULL; END; $$
    """)

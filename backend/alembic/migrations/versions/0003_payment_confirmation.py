"""Payment confirmation fields on recovery_instruments + email_notification_log table.

Revision ID: 0003_payment_confirmation
Revises: 0002_sc002_integration
Create Date: 2026-06-25

Adds:
  - recovery_instruments.payment_confirmed      BOOLEAN DEFAULT FALSE
  - recovery_instruments.payment_confirmed_at   TIMESTAMPTZ
  - recovery_instruments.payment_confirmed_ref  TEXT
  - email_notification_log                      TABLE (audit trail for outbound notifications)
"""
from __future__ import annotations

import os
from alembic import op

revision     = "0003_payment_confirmation"
down_revision = "0002_sc002_integration"
branch_labels = None
depends_on    = None

_HERE     = os.path.dirname(os.path.abspath(__file__))
_SQL_FILE = os.path.join(_HERE, "payment_confirmation_schema.sql")


def upgrade() -> None:
    with open(_SQL_FILE, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_notification_log CASCADE")
    op.execute("DROP INDEX  IF EXISTS idx_recovery_instruments_payment_confirmed")
    op.execute("ALTER TABLE recovery_instruments DROP COLUMN IF EXISTS payment_confirmed_ref")
    op.execute("ALTER TABLE recovery_instruments DROP COLUMN IF EXISTS payment_confirmed_at")
    op.execute("ALTER TABLE recovery_instruments DROP COLUMN IF EXISTS payment_confirmed")

"""Add tenant_notification_settings table for Settings -> Notifications.

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-14

Per-tenant email alert toggles. One row per tenant, created on first
read/write with all alerts defaulted to enabled.
"""
from __future__ import annotations
from alembic import op

revision      = "0027"
down_revision = "0026"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_notification_settings (
            tenant_id                  UUID        PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            case_opened_email          BOOLEAN     NOT NULL DEFAULT TRUE,
            overcharge_detected_email  BOOLEAN     NOT NULL DEFAULT TRUE,
            approval_needed_email      BOOLEAN     NOT NULL DEFAULT TRUE,
            recovery_executed_email    BOOLEAN     NOT NULL DEFAULT TRUE,
            updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_notification_settings")

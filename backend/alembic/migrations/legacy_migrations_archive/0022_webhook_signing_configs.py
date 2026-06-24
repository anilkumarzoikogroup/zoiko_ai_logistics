"""
0022 — Webhook signing configs table.

New table:
  - webhook_signing_configs — per-tenant signing secret + IP allow-list
    for inbound webhook channels (§7.4)
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS webhook_signing_configs (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id),
            source_type    TEXT NOT NULL,
            signing_secret TEXT NOT NULL,
            ip_allowlist   JSONB NOT NULL DEFAULT '[]',
            is_active      BOOLEAN NOT NULL DEFAULT true,
            config         JSONB NOT NULL DEFAULT '{}',
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            rotated_at     TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_webhook_signing_tenant_type
        ON webhook_signing_configs (tenant_id, source_type, is_active)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS webhook_signing_configs")

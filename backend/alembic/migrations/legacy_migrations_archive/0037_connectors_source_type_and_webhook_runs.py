"""Add source_type to connectors so webhook deliveries link to a connector.

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-18

Connectors had no stable, unique slug a webhook URL could route on — the
frontend was building every Webhook connector's URL from connector_type
("webhook"), so two carriers would collide on the exact same inbound URL,
and there was no way for the webhook ingestion path to know which connector
a delivery belonged to. That's why the Ingestion Runs panel always showed
0/0: it's wired to the pull-style /sync endpoint, which has no visibility
into webhook deliveries at all.

connectors gains:
  - source_type   TEXT — unique per tenant, used as the
                   /webhooks/ingest/{source_type} path segment

Existing rows are backfilled with a slug derived from their name.
"""
from alembic import op

revision      = "0037"
down_revision = "0036"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE connectors
            ADD COLUMN IF NOT EXISTS source_type TEXT
    """)

    op.execute("""
        UPDATE connectors
        SET source_type = lower(regexp_replace(regexp_replace(name, '[^a-zA-Z0-9]+', '-', 'g'), '(^-|-$)', '', 'g'))
        WHERE source_type IS NULL OR source_type = ''
    """)

    op.execute("""
        ALTER TABLE connectors
            ALTER COLUMN source_type SET DEFAULT '',
            ALTER COLUMN source_type SET NOT NULL
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_connectors_tenant_source_type
            ON connectors(tenant_id, source_type)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_connectors_tenant_source_type")
    op.execute("ALTER TABLE connectors DROP COLUMN IF EXISTS source_type")

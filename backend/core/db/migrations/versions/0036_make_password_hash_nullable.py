"""Make users.password_hash nullable for admin-created users (no-password flow).

When admin creates a user without a password, password_hash is now NULL
instead of an empty string. The login endpoint treats NULL/empty as "no
password set — use forgot-password flow to create one."

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-16
"""

from alembic import op

revision      = "0036"
down_revision = "0035"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")


def downgrade() -> None:
    op.execute("UPDATE users SET password_hash = '' WHERE password_hash IS NULL")
    op.execute("ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL")

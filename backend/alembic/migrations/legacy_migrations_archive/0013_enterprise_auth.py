"""Enterprise authentication tables.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-30

New tables:
  password_reset_tokens    — single-use 15-min TTL recovery tokens
  invitation_tokens        — tenant admin sends invite; user activates
  workspace_access_requests — prospect lead-capture (no tenant created)
  sso_domains              — email domain → IdP mapping for SSO discovery
  step_up_assertions       — short-lived step-up auth records
"""
from __future__ import annotations
from alembic import op

revision      = "0013"
down_revision = "0012"
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # ── SSO domain registry ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS sso_domains (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            domain      TEXT NOT NULL,
            idp_type    TEXT NOT NULL DEFAULT 'oidc'
                          CHECK (idp_type IN ('entra','okta','ping','google','saml','oidc')),
            idp_config  JSONB NOT NULL DEFAULT '{}',
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (domain)
        )
    """)

    # ── Password reset tokens ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  TEXT NOT NULL UNIQUE,
            expires_at  TIMESTAMPTZ NOT NULL,
            used_at     TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_prt_token_hash
            ON password_reset_tokens(token_hash) WHERE used_at IS NULL
    """)

    # ── Invitation tokens ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS invitation_tokens (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email        TEXT NOT NULL,
            role         TEXT NOT NULL DEFAULT 'analyst'
                           CHECK (role IN ('analyst','manager','admin')),
            invited_by   TEXT NOT NULL,
            token_hash   TEXT NOT NULL UNIQUE,
            expires_at   TIMESTAMPTZ NOT NULL,
            accepted_at  TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Workspace access requests (prospects) ─────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS workspace_access_requests (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            full_name      TEXT NOT NULL,
            work_email     TEXT NOT NULL,
            company_name   TEXT NOT NULL,
            company_website TEXT,
            country        TEXT,
            role           TEXT,
            use_case       TEXT,
            team_size      TEXT,
            heard_from     TEXT,
            consent        BOOLEAN NOT NULL DEFAULT FALSE,
            status         TEXT NOT NULL DEFAULT 'PENDING'
                             CHECK (status IN ('PENDING','CONTACTED','QUALIFIED','REJECTED')),
            crm_ref        TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Step-up assertions ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS step_up_assertions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            action      TEXT NOT NULL,
            expires_at  TIMESTAMPTZ NOT NULL,
            used_at     TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    for tbl in ["step_up_assertions", "workspace_access_requests",
                "invitation_tokens", "password_reset_tokens", "sso_domains"]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")

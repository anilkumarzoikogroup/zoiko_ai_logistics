"""P0: Create all 25 Zoiko tables in a single migration.

Revision ID: 0001
Revises: —
Create Date: 2026-05-17

All tenant-scoped tables have RLS enabled and forced.
APPEND-ONLY tables: lineage_records, case_events, evidence_items, audit_worm_index
  — no UPDATE or DELETE rules added; application layer must never issue them.
No raw key material is stored in tenant_keys (key_ciphertext only).
Outbox partial index on shipped_at IS NULL for efficient relay polling.
"""
from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Extensions                                                           #
    # ------------------------------------------------------------------ #
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ------------------------------------------------------------------ #
    # TENANT GROUP                                                         #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE tenants (
        id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        slug          TEXT NOT NULL UNIQUE,
        display_name  TEXT NOT NULL,
        status        TEXT NOT NULL DEFAULT 'ACTIVE'
                        CHECK (status IN ('ACTIVE','SUSPENDED','OFFBOARDED')),
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE tenant_keys (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        key_purpose     TEXT NOT NULL,
        kms_resource    TEXT NOT NULL,
        key_ciphertext  BYTEA NOT NULL,
        -- No raw key material stored here — key_ciphertext is KMS-encrypted DEK
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        rotated_at      TIMESTAMPTZ
    )""")

    # ------------------------------------------------------------------ #
    # INGESTION GROUP                                                      #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE source_records (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        source_type     TEXT NOT NULL,
        canonical_hash  BYTEA NOT NULL,   -- SHA-256 of JCS canonical form, pre-encryption
        ciphertext      BYTEA NOT NULL,   -- AES-256-GCM via KMS DEK
        signature       BYTEA NOT NULL,   -- Ed25519 signature over canonical_hash
        kid             TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (tenant_id, idempotency_key)
    )""")

    op.execute("""
    CREATE TABLE lineage_records (
        -- APPEND-ONLY: no UPDATE or DELETE ever
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL REFERENCES tenants(id),
        entity_type  TEXT NOT NULL,
        entity_id    UUID NOT NULL,
        parent_id    UUID,
        event_type   TEXT NOT NULL,
        payload_hash BYTEA NOT NULL,
        recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # VALIDATION GROUP                                                     #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE validation_results (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id        UUID NOT NULL REFERENCES tenants(id),
        source_record_id UUID NOT NULL REFERENCES source_records(id),
        status           TEXT NOT NULL CHECK (status IN ('PASS','FAIL','WARN')),
        rule_violations  JSONB NOT NULL DEFAULT '[]',
        signature        BYTEA NOT NULL,
        kid              TEXT NOT NULL,
        validated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # CANONICAL GROUP                                                      #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE canonical_invoices (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id        UUID NOT NULL REFERENCES tenants(id),
        source_record_id UUID NOT NULL REFERENCES source_records(id),
        invoice_number   TEXT NOT NULL,
        carrier_id       TEXT NOT NULL,
        total_amount     NUMERIC(18,4) NOT NULL,
        currency         TEXT NOT NULL DEFAULT 'USD',
        canonical_hash   BYTEA NOT NULL,
        signature        BYTEA NOT NULL,
        kid              TEXT NOT NULL,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (tenant_id, invoice_number)
    )""")

    op.execute("""
    CREATE TABLE canonical_shipments (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        invoice_id      UUID NOT NULL REFERENCES canonical_invoices(id),
        origin_city     TEXT NOT NULL,
        dest_city       TEXT NOT NULL,
        weight_lbs      NUMERIC(12,2),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE contract_rates (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL REFERENCES tenants(id),
        carrier_id   TEXT NOT NULL,
        rate_type    TEXT NOT NULL,
        rate_value   NUMERIC(18,4) NOT NULL,
        currency     TEXT NOT NULL DEFAULT 'USD',
        effective_on DATE NOT NULL,
        expires_on   DATE,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # CASE GROUP                                                           #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE cases (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id         UUID NOT NULL REFERENCES tenants(id),
        invoice_id        UUID NOT NULL REFERENCES canonical_invoices(id),
        state             TEXT NOT NULL DEFAULT 'OPENED'
                            CHECK (state IN (
                                'OPENED','EVIDENCE_GATHERING','UNDER_REVIEW',
                                'PENDING_APPROVAL','APPROVED','REJECTED','EXECUTED',
                                'RECONCILED','CLOSED'
                            )),
        opened_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        closed_at         TIMESTAMPTZ,
        UNIQUE (tenant_id, invoice_id)
    )""")

    op.execute("""
    CREATE TABLE case_events (
        -- APPEND-ONLY: no UPDATE or DELETE ever
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL REFERENCES tenants(id),
        case_id      UUID NOT NULL REFERENCES cases(id),
        event_type   TEXT NOT NULL,
        from_state   TEXT,
        to_state     TEXT,
        actor_sub    TEXT NOT NULL,
        payload      JSONB NOT NULL DEFAULT '{}',
        occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # EVIDENCE GROUP                                                       #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE evidence_bundles (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL REFERENCES tenants(id),
        case_id      UUID NOT NULL REFERENCES cases(id),
        bundle_hash  BYTEA NOT NULL,
        signature    BYTEA NOT NULL,
        kid          TEXT NOT NULL,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE evidence_items (
        -- APPEND-ONLY: no UPDATE or DELETE ever
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL REFERENCES tenants(id),
        bundle_id    UUID NOT NULL REFERENCES evidence_bundles(id),
        item_type    TEXT NOT NULL,
        entity_id    UUID NOT NULL,
        item_hash    BYTEA NOT NULL,
        added_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # REASONING GROUP                                                      #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE findings (
        id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id     UUID NOT NULL REFERENCES tenants(id),
        case_id       UUID NOT NULL REFERENCES cases(id),
        bundle_id     UUID NOT NULL REFERENCES evidence_bundles(id),
        confidence    NUMERIC(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
        ai_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        risk_level    TEXT NOT NULL DEFAULT 'MEDIUM',
        ai_reasoning  TEXT NOT NULL DEFAULT '[]',
        rule_trace    JSONB NOT NULL,
        signature     BYTEA NOT NULL,
        kid           TEXT NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE decision_proposals (
        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id      UUID NOT NULL REFERENCES tenants(id),
        case_id        UUID NOT NULL REFERENCES cases(id),
        finding_id     UUID NOT NULL REFERENCES findings(id),
        proposed_action TEXT NOT NULL,
        amount         NUMERIC(18,4),
        currency       TEXT DEFAULT 'USD',
        proposer_sub   TEXT NOT NULL,
        proposal_hash  BYTEA NOT NULL,
        signature      BYTEA NOT NULL,
        kid            TEXT NOT NULL,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # GOVERNANCE GROUP                                                     #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE policy_bundles (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL REFERENCES tenants(id),
        version      TEXT NOT NULL,
        rego_hash    BYTEA NOT NULL,
        active       BOOLEAN NOT NULL DEFAULT FALSE,
        deployed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE governance_decisions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        proposal_id     UUID NOT NULL REFERENCES decision_proposals(id),
        policy_bundle_id UUID NOT NULL REFERENCES policy_bundles(id),
        outcome         TEXT NOT NULL CHECK (
                           outcome IN (
                               'APPROVED','REJECTED',
                               'EXECUTION_READY','ABORTED'
                           )
                       ),
        decision_hash   BYTEA NOT NULL,
        signature       BYTEA NOT NULL,
        kid             TEXT NOT NULL,
        decided_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE approval_tasks (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id        UUID NOT NULL REFERENCES tenants(id),
        proposal_id      UUID NOT NULL REFERENCES decision_proposals(id),
        proposer_sub     TEXT NOT NULL,
        actor_sub        TEXT,        -- NULL until actioned
        -- SoD: actor_sub != proposer_sub enforced at application layer
        status           TEXT NOT NULL DEFAULT 'PENDING'
                           CHECK (status IN ('PENDING','APPROVED','REJECTED')),
        actioned_at      TIMESTAMPTZ,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # TOKEN GROUP                                                          #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE governance_tokens (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id        UUID NOT NULL REFERENCES tenants(id),
        decision_id      UUID NOT NULL REFERENCES governance_decisions(id),
        scope            TEXT NOT NULL,
        tenant_binding   BYTEA NOT NULL,  -- SHA-256(tenant_id || decision_id)
        status           TEXT NOT NULL DEFAULT 'ACTIVE'
                           CHECK (status IN ('ACTIVE','CONSUMED','EXPIRED','REVOKED')),
        expires_at       TIMESTAMPTZ NOT NULL,
        consumed_at      TIMESTAMPTZ,
        token_hash       BYTEA NOT NULL,
        signature        BYTEA NOT NULL,
        kid              TEXT NOT NULL,
        issued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # EXECUTION GROUP                                                      #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE idempotency_keys (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        key_value       TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'IN_PROGRESS'
                          CHECK (status IN ('IN_PROGRESS','COMPLETE')),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at    TIMESTAMPTZ,
        UNIQUE (tenant_id, key_value)
    )""")

    op.execute("""
    CREATE TABLE execution_envelopes (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL REFERENCES tenants(id),
        token_id     UUID NOT NULL REFERENCES governance_tokens(id),
        case_id      UUID NOT NULL REFERENCES cases(id),
        gate_results JSONB NOT NULL,    -- 8-gate pass/fail details
        status       TEXT NOT NULL DEFAULT 'DISPATCHED'
                       CHECK (status IN ('DISPATCHED','CONFIRMED','FAILED')),
        env_hash     BYTEA NOT NULL,
        signature    BYTEA NOT NULL,
        kid          TEXT NOT NULL,
        dispatched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE connector_responses (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        envelope_id     UUID NOT NULL REFERENCES execution_envelopes(id),
        connector_id    TEXT NOT NULL,
        status_code     INTEGER NOT NULL,
        response_body   JSONB,
        received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # RECONCILIATION GROUP                                                 #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE reconciliations (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        case_id         UUID NOT NULL REFERENCES cases(id),
        envelope_id     UUID NOT NULL REFERENCES execution_envelopes(id),
        delta_amount    NUMERIC(18,4) NOT NULL,
        currency        TEXT NOT NULL DEFAULT 'USD',
        recon_hash      BYTEA NOT NULL,
        reconciled_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE outcomes (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id),
        case_id         UUID NOT NULL REFERENCES cases(id),
        recon_id        UUID NOT NULL REFERENCES reconciliations(id),
        outcome_type    TEXT NOT NULL,
        outcome_hash    BYTEA NOT NULL,
        signature       BYTEA NOT NULL,
        kid             TEXT NOT NULL,
        recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # AUDIT GROUP                                                          #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE action_certification_records (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id        UUID NOT NULL REFERENCES tenants(id),
        case_id          UUID NOT NULL REFERENCES cases(id),
        acr_version      TEXT NOT NULL DEFAULT 'v1',
        merkle_root      BYTEA NOT NULL,     -- root of 8-artifact Merkle tree
        artifact_hashes  JSONB NOT NULL,     -- {artifact_type: sha256_hex}
        signature        BYTEA NOT NULL,
        kid              TEXT NOT NULL,
        worm_object_name TEXT,               -- GCS WORM bucket object
        certified_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # INFRASTRUCTURE GROUP                                                 #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE outbox (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL REFERENCES tenants(id),
        topic        TEXT NOT NULL,
        partition_key TEXT NOT NULL,
        payload      JSONB NOT NULL,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        shipped_at   TIMESTAMPTZ     -- NULL = not yet relayed
    )""")

    # Partial index for efficient relay polling (only unshipped rows)
    op.execute("""
    CREATE INDEX idx_outbox_unshipped
        ON outbox (created_at ASC)
        WHERE shipped_at IS NULL
    """)

    op.execute("""
    CREATE TABLE audit_worm_index (
        -- APPEND-ONLY: no UPDATE or DELETE ever
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id    UUID NOT NULL REFERENCES tenants(id),
        acr_id       UUID NOT NULL REFERENCES action_certification_records(id),
        worm_bucket  TEXT NOT NULL,
        object_name  TEXT NOT NULL,
        object_hash  BYTEA NOT NULL,
        indexed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    # ------------------------------------------------------------------ #
    # Row-Level Security — enable + force on all tenant-scoped tables      #
    # ------------------------------------------------------------------ #
    tenant_tables = [
        "tenant_keys", "source_records", "lineage_records",
        "validation_results", "canonical_invoices", "canonical_shipments",
        "contract_rates", "cases", "case_events",
        "evidence_bundles", "evidence_items",
        "findings", "decision_proposals",
        "policy_bundles", "governance_decisions", "approval_tasks",
        "governance_tokens",
        "idempotency_keys", "execution_envelopes", "connector_responses",
        "reconciliations", "outcomes",
        "action_certification_records",
        "outbox", "audit_worm_index",
    ]
    for tbl in tenant_tables:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    tables = [
        "audit_worm_index", "outbox", "action_certification_records",
        "outcomes", "reconciliations",
        "connector_responses", "execution_envelopes", "idempotency_keys",
        "governance_tokens",
        "approval_tasks", "governance_decisions", "policy_bundles",
        "decision_proposals", "findings",
        "evidence_items", "evidence_bundles",
        "case_events", "cases",
        "contract_rates", "canonical_shipments", "canonical_invoices",
        "validation_results",
        "lineage_records", "source_records",
        "tenant_keys", "tenants",
    ]
    for tbl in tables:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")

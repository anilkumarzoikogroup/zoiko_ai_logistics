"""Reapply 0020's source_records / dedup field additions on environments where
migration 0020 never executed.

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-15

Some environments have alembic_version past 0020 without 0020's body ever
having run against this database (e.g. the version table was stamped from a
snapshot taken at a later point in history). That leaves source_records
missing columns like schema_version, channel, deduplication_key, etc., and
the supporting tables (ambiguity_queue, source_record_states,
validation_rule_sets) missing entirely.

Every statement in 0020's upgrade() is already idempotent (ADD COLUMN IF NOT
EXISTS / CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS / INSERT ...
ON CONFLICT DO NOTHING), so it is safe to re-run verbatim here.
"""

from alembic import op

revision      = "0033"
down_revision = "0032"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── source_records — governance / identity fields ─────────────────────
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS schema_version TEXT NOT NULL DEFAULT 'source-record.v1'")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS domain_tag TEXT NOT NULL DEFAULT 'zoiko/v1/source-record'")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS brand_id UUID")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS jurisdiction_code TEXT")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS data_classification TEXT NOT NULL DEFAULT 'confidential'")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS retention_class TEXT NOT NULL DEFAULT 'tier-A'")

    # Channel provenance
    op.execute("""
        ALTER TABLE source_records
        ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'rest_api_push'
        CHECK (channel IN ('rest_api_push','rest_api_pull','webhook','edi','file_upload','ui_entry'))
    """)
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS channel_metadata JSONB NOT NULL DEFAULT '{}'")

    # Source type versioning + external reference
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS source_type_version TEXT NOT NULL DEFAULT 'v1'")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS external_source_ref TEXT")

    # Receipt attribution
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS received_by_service TEXT")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS received_by_user UUID")

    # Encryption envelope metadata
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_iv BYTEA")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_aad TEXT")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_dek_id TEXT")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_size_bytes INTEGER")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_content_type TEXT NOT NULL DEFAULT 'application/json'")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_encoding TEXT NOT NULL DEFAULT 'utf-8'")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_hash_alg TEXT NOT NULL DEFAULT 'sha-256'")

    # Deduplication decision
    op.execute("""
        ALTER TABLE source_records
        ADD COLUMN IF NOT EXISTS deduplication_key TEXT
    """)
    op.execute("""
        ALTER TABLE source_records
        ADD COLUMN IF NOT EXISTS deduplication_outcome TEXT NOT NULL DEFAULT 'FIRST_SEEN'
        CHECK (deduplication_outcome IN ('FIRST_SEEN','DUPLICATE_OF','AMBIGUOUS'))
    """)
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS deduplication_canonical_record_id UUID REFERENCES source_records(id)")

    # Validation state
    op.execute("""
        ALTER TABLE source_records
        ADD COLUMN IF NOT EXISTS validation_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (validation_status IN ('PENDING','VALIDATING','VALIDATED','QUARANTINED','REJECTED'))
    """)
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS validation_result_id UUID")

    # Trace linkage
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS lineage_id UUID")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS correlation_id UUID")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS causation_id UUID")

    # Source record state machine
    op.execute("""
        ALTER TABLE source_records
        ADD COLUMN IF NOT EXISTS record_status TEXT NOT NULL DEFAULT 'RECEIVED'
        CHECK (record_status IN (
            'RECEIVED','PERSISTED','DEDUPED','ENCRYPTED','SIGNED',
            'PENDING_VALIDATION','VALIDATING','VALIDATED',
            'CANONICALIZING','PROCESSED','QUARANTINED','REJECTED'
        ))
    """)

    # Structured signature block
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS signature_block JSONB")

    # Indexes
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_records_ext_ref
        ON source_records (tenant_id, external_source_ref)
        WHERE external_source_ref IS NOT NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_records_validation_status ON source_records (tenant_id, validation_status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_records_record_status ON source_records (tenant_id, record_status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_records_dedup_key ON source_records (tenant_id, deduplication_key) WHERE deduplication_key IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_records_correlation ON source_records (correlation_id) WHERE correlation_id IS NOT NULL")

    # ── ambiguity_queue ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS ambiguity_queue (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id),
            source_record_id    UUID NOT NULL REFERENCES source_records(id),
            original_record_id  UUID NOT NULL REFERENCES source_records(id),
            external_source_ref TEXT NOT NULL,
            reason              TEXT NOT NULL,
            resolution          TEXT CHECK (resolution IN ('USE_LATEST','USE_ORIGINAL','REJECT_BOTH','MANUAL')),
            resolved_by         UUID,
            resolved_at         TIMESTAMPTZ,
            resolution_note     TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ambiguity_queue_tenant ON ambiguity_queue (tenant_id, resolved_at) WHERE resolved_at IS NULL")

    # ── source_record_states ───────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS source_record_states (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id),
            source_record_id UUID NOT NULL REFERENCES source_records(id),
            from_status      TEXT,
            to_status        TEXT NOT NULL,
            actor            TEXT,
            detail           JSONB,
            occurred_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_src_states_record ON source_record_states (source_record_id, occurred_at)")

    # ── validation_rule_sets ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS validation_rule_sets (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            rule_set_id     TEXT NOT NULL,
            version         TEXT NOT NULL,
            source_type     TEXT NOT NULL,
            rules           JSONB NOT NULL DEFAULT '[]',
            status          TEXT NOT NULL DEFAULT 'DRAFT'
                            CHECK (status IN ('DRAFT','ACTIVE','SUPERSEDED','RETIRED')),
            activated_at    TIMESTAMPTZ,
            superseded_at   TIMESTAMPTZ,
            authored_by     UUID,
            signature       TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (rule_set_id, version)
        )
    """)
    # Backfill columns on environments where validation_rule_sets pre-existed
    # with an older shape (CREATE TABLE IF NOT EXISTS above no-ops there).
    op.execute("ALTER TABLE validation_rule_sets ADD COLUMN IF NOT EXISTS rule_set_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE validation_rule_sets ADD COLUMN IF NOT EXISTS version TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE validation_rule_sets ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE validation_rule_sets ADD COLUMN IF NOT EXISTS rules JSONB NOT NULL DEFAULT '[]'")
    op.execute("""
        ALTER TABLE validation_rule_sets
        ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','ACTIVE','SUPERSEDED','RETIRED'))
    """)
    op.execute("ALTER TABLE validation_rule_sets ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ")
    op.execute("ALTER TABLE validation_rule_sets ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ")
    op.execute("ALTER TABLE validation_rule_sets ADD COLUMN IF NOT EXISTS authored_by UUID")
    op.execute("ALTER TABLE validation_rule_sets ADD COLUMN IF NOT EXISTS signature TEXT")
    op.execute("ALTER TABLE validation_rule_sets ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE validation_rule_sets
                ADD CONSTRAINT validation_rule_sets_rule_set_id_version_key
                UNIQUE (rule_set_id, version);
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_rule_sets_active ON validation_rule_sets (source_type, status) WHERE status = 'ACTIVE'")

    # Some environments' validation_rule_sets has an extra rule_set_name
    # column (not part of this model) with a NOT NULL constraint that would
    # reject the seed INSERT below — relax it if present.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='validation_rule_sets' AND column_name='rule_set_name'
            ) THEN
                ALTER TABLE validation_rule_sets ALTER COLUMN rule_set_name DROP NOT NULL;
            END IF;
        END $$;
    """)

    # validation_results — rule_set columns
    op.execute("ALTER TABLE validation_results ADD COLUMN IF NOT EXISTS rule_set_id TEXT")
    op.execute("ALTER TABLE validation_results ADD COLUMN IF NOT EXISTS rule_set_version TEXT")
    op.execute("ALTER TABLE validation_results ADD COLUMN IF NOT EXISTS validation_service_version TEXT NOT NULL DEFAULT '1.0.0'")

    # Seed default ACTIVE rule set
    op.execute("""
        INSERT INTO validation_rule_sets (rule_set_id, version, source_type, status, activated_at, rules)
        VALUES (
            'carrier_invoice_validation', 'v1.0.0', 'INVOICE', 'ACTIVE', NOW(),
            '[
                {"rule_id":"R001","name":"contract_rate_check","description":"Invoice total must not exceed contract rate by more than 1%","severity":"HIGH"},
                {"rule_id":"R002","name":"currency_valid","description":"Currency must be a valid ISO-4217 code","severity":"MEDIUM"},
                {"rule_id":"R003","name":"carrier_known","description":"carrier_id must exist in reference data","severity":"HIGH"},
                {"rule_id":"R004","name":"amount_positive","description":"Invoice total must be positive","severity":"HIGH"}
            ]'::jsonb
        )
        ON CONFLICT (rule_set_id, version) DO NOTHING
    """)


def downgrade() -> None:
    # All statements above are re-applications of 0020 — downgrading 0020
    # already reverses this state. No-op here to avoid destroying data on
    # environments where 0020 ran correctly.
    pass

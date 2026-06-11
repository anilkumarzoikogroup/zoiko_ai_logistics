"""
0020 — Tier-0 Ingestion: extend source_records with all spec-required fields.

Adds to source_records:
  - schema_version, domain_tag
  - brand_id, jurisdiction_code
  - data_residency_region, data_classification, retention_class
  - channel, channel_metadata (JSONB)
  - source_type_version, external_source_ref
  - received_at, received_by_service, received_by_user
  - raw_payload_iv, raw_payload_aad, raw_payload_dek_id
  - raw_payload_size_bytes, raw_payload_content_type, raw_payload_encoding
  - raw_payload_hash_alg
  - deduplication_key, deduplication_outcome, deduplication_canonical_record_id
  - validation_status, validation_result_id
  - lineage_id, correlation_id, causation_id
  - record_status (source record state machine)
  - signature_block (JSONB — {alg, key_id, signature})

New tables:
  - dedup_index         — hot-path deduplication lookup
  - source_record_states — append-only state transition log
"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------ #
    # 1. Extend source_records                                             #
    # ------------------------------------------------------------------ #

    # Governance / identity fields
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

    # Encryption envelope metadata (IV and AAD are stored separately for auditability)
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_iv BYTEA")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_aad TEXT")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_dek_id TEXT")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_size_bytes INTEGER")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_content_type TEXT NOT NULL DEFAULT 'application/json'")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_encoding TEXT NOT NULL DEFAULT 'utf-8'")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS raw_payload_hash_alg TEXT NOT NULL DEFAULT 'sha-256'")

    # Deduplication decision (mirrors dedup_index outcome onto the record itself)
    op.execute("""
        ALTER TABLE source_records
        ADD COLUMN IF NOT EXISTS deduplication_key TEXT
    """)
    op.execute("""
        ALTER TABLE source_records
        ADD COLUMN IF NOT EXISTS deduplication_outcome TEXT NOT NULL DEFAULT 'FIRST_SEEN'
        CHECK (deduplication_outcome IN ('FIRST_SEEN','DUPLICATE_OF','AMBIGUOUS'))
    """)
    # Self-referencing FK: points to the original record when this is a DUPLICATE_OF
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS deduplication_canonical_record_id UUID REFERENCES source_records(id)")

    # Validation state (denormalised onto source_record for fast dashboard queries)
    op.execute("""
        ALTER TABLE source_records
        ADD COLUMN IF NOT EXISTS validation_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (validation_status IN ('PENDING','VALIDATING','VALIDATED','QUARANTINED','REJECTED'))
    """)
    # No FK constraint — validation_results.source_record_id already references us (circular avoided)
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS validation_result_id UUID")

    # Trace linkage
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS lineage_id UUID")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS correlation_id UUID")
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS causation_id UUID")

    # Source record state machine (coarser grain than validation_status)
    op.execute("""
        ALTER TABLE source_records
        ADD COLUMN IF NOT EXISTS record_status TEXT NOT NULL DEFAULT 'RECEIVED'
        CHECK (record_status IN (
            'RECEIVED','PERSISTED','DEDUPED','ENCRYPTED','SIGNED',
            'PENDING_VALIDATION','VALIDATING','VALIDATED',
            'CANONICALIZING','PROCESSED','QUARANTINED','REJECTED'
        ))
    """)

    # Structured signature block (spec §8.1: {alg, key_id, signature})
    op.execute("ALTER TABLE source_records ADD COLUMN IF NOT EXISTS signature_block JSONB")

    # Index: fast lookup by external_source_ref per tenant
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_records_ext_ref
        ON source_records (tenant_id, external_source_ref)
        WHERE external_source_ref IS NOT NULL
    """)
    # Index: dashboard queries by validation_status
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_records_validation_status ON source_records (tenant_id, validation_status)")
    # Index: dashboard queries by record_status
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_records_record_status ON source_records (tenant_id, record_status)")
    # Index: dedup key lookups
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_records_dedup_key ON source_records (tenant_id, deduplication_key) WHERE deduplication_key IS NOT NULL")
    # Index: correlation tracing
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_records_correlation ON source_records (correlation_id) WHERE correlation_id IS NOT NULL")

    # ------------------------------------------------------------------ #
    # 2. dedup_index — hot-path deduplication table                       #
    #    The dedup key is the authoritative lookup.                        #
    #    Redis accelerates reads; this table is the durable audit record.  #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE IF NOT EXISTS dedup_index (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id),
            deduplication_key   TEXT NOT NULL,
            outcome             TEXT NOT NULL CHECK (outcome IN ('FIRST_SEEN','DUPLICATE_OF','AMBIGUOUS')),
            source_record_id    UUID NOT NULL REFERENCES source_records(id),
            original_record_id  UUID REFERENCES source_records(id),  -- set when DUPLICATE_OF
            external_source_ref TEXT,
            payload_hash        TEXT NOT NULL,
            source_type         TEXT NOT NULL,
            source_type_version TEXT NOT NULL DEFAULT 'v1',
            decided_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, deduplication_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dedup_index_tenant ON dedup_index (tenant_id, external_source_ref)")

    # ------------------------------------------------------------------ #
    # 3. ambiguity_queue — holds AMBIGUOUS records for operator resolution #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # 4. source_record_states — append-only FSM transition log            #
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # 5. validation_rule_sets — versioned, signed validation rule catalog  #
    # ------------------------------------------------------------------ #
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_rule_sets_active ON validation_rule_sets (source_type, status) WHERE status = 'ACTIVE'")

    # Add rule_set columns to validation_results so every result records which rules were used
    op.execute("ALTER TABLE validation_results ADD COLUMN IF NOT EXISTS rule_set_id TEXT")
    op.execute("ALTER TABLE validation_results ADD COLUMN IF NOT EXISTS rule_set_version TEXT")
    op.execute("ALTER TABLE validation_results ADD COLUMN IF NOT EXISTS validation_service_version TEXT NOT NULL DEFAULT '1.0.0'")

    # Seed a default ACTIVE rule set for carrier invoices so existing validation still works
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


def downgrade():
    op.execute("DROP TABLE IF EXISTS source_record_states")
    op.execute("DROP TABLE IF EXISTS ambiguity_queue")
    op.execute("DROP TABLE IF EXISTS dedup_index")
    op.execute("DROP TABLE IF EXISTS validation_rule_sets")

    for col in [
        "schema_version","domain_tag","brand_id","jurisdiction_code",
        "data_residency_region","data_classification","retention_class",
        "channel","channel_metadata","source_type_version","external_source_ref",
        "received_at","received_by_service","received_by_user",
        "raw_payload_iv","raw_payload_aad","raw_payload_dek_id",
        "raw_payload_size_bytes","raw_payload_content_type","raw_payload_encoding",
        "raw_payload_hash_alg","deduplication_key","deduplication_outcome",
        "deduplication_canonical_record_id","validation_status","validation_result_id",
        "lineage_id","correlation_id","causation_id","record_status","signature_block",
    ]:
        op.execute(f"ALTER TABLE source_records DROP COLUMN IF EXISTS {col}")

    for col in ["rule_set_id","rule_set_version","validation_service_version"]:
        op.execute(f"ALTER TABLE validation_results DROP COLUMN IF EXISTS {col}")

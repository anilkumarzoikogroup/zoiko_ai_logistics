"""Clarification 07 Slice 1 — Multi-Tenant Data Residency, Retention, Legal Hold,
Crypto-Shredding, Archive and Restore foundation.

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-14

Changes:
  - tenants: add data_residency_region
  - All governed tables: add data_residency_region, retention_class,
    legal_hold_status, correlation_id, trace_id, updated_by
  - Class A tables: add retention_until, archive_after, purge_after,
    crypto_shred_status, archive_eligible
  - legal_hold_records: upgrade to full C07 model
  - New tables: retention_policies, crypto_shred_requests, restore_jobs,
    restore_verification_records, archive_jobs, purge_jobs
"""

from alembic import op

revision     = "0030"
down_revision = "0029"
branch_labels = None
depends_on    = None

# ── Helper ────────────────────────────────────────────────────────────────────

def _add(table: str, col: str, defn: str):
    op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {defn}")


# ── Mandatory C07 fields — added to every governed table ─────────────────────

_MANDATORY_TEXT = [
    ("data_residency_region", "TEXT NOT NULL DEFAULT 'ap-south-1'"),
    ("retention_class",       "TEXT NOT NULL DEFAULT 'tier-B-operational'"),
    ("legal_hold_status",     "TEXT NOT NULL DEFAULT 'NONE' CHECK (legal_hold_status IN ('NONE','HELD'))"),
    ("updated_by",            "TEXT"),
]
_MANDATORY_UUID = [
    ("correlation_id", "UUID"),
    ("trace_id",       "UUID"),
]

# Class A retention / crypto fields
_CLASS_A_COLS = [
    ("retention_until",    "TIMESTAMPTZ"),
    ("archive_after",      "TIMESTAMPTZ"),
    ("purge_after",        "TIMESTAMPTZ"),
    ("crypto_shred_status","TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (crypto_shred_status IN ('ACTIVE','SHREDDED','EXEMPT'))"),
    ("archive_eligible",   "BOOLEAN NOT NULL DEFAULT FALSE"),
]

# Tables that get the full mandatory set
_GOVERNED_TABLES = [
    "cases",
    "evidence_bundles",
    "findings",
    "action_certification_records",
    "governance_tokens",
    "validation_results",
    # Phase 6 recovery tables
    "expected_recoveries",
    "recovery_instruments",
    "recovery_matches",
    "ledger_entries",
    "write_offs",
    "recovery_proofs",
]

# Tables that also get Class A retention/crypto columns
_CLASS_A_TABLES = [
    "evidence_bundles",
    "action_certification_records",
    "ledger_entries",
    "recovery_proofs",
    "source_records",
]


def upgrade() -> None:
    # ── 1. tenants — residency anchor ─────────────────────────────────────────
    _add("tenants", "data_residency_region",
         "TEXT NOT NULL DEFAULT 'ap-south-1'")
    _add("tenants", "residency_assigned_at", "TIMESTAMPTZ")
    _add("tenants", "residency_assigned_by", "TEXT")

    # ── 2. Mandatory fields on all governed tables ─────────────────────────────
    for table in _GOVERNED_TABLES:
        for col, defn in _MANDATORY_TEXT + _MANDATORY_UUID:
            _add(table, col, defn)

    # ── 3. Class A retention + crypto fields ──────────────────────────────────
    for table in _CLASS_A_TABLES:
        for col, defn in _CLASS_A_COLS:
            _add(table, col, defn)

    # ── 4. Upgrade legal_hold_records to full C07 model ───────────────────────
    # Some environments are missing this table even though alembic_version is
    # past 0019 (which originally created it) — recreate defensively so the
    # ADD COLUMN calls below have a table to target.
    op.execute("""
        CREATE TABLE IF NOT EXISTS legal_hold_records (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id      UUID REFERENCES cases(id),
            subject_type TEXT NOT NULL DEFAULT 'case',
            subject_id   UUID NOT NULL,
            reason       TEXT NOT NULL DEFAULT '',
            applied_by   TEXT NOT NULL DEFAULT '',
            applied_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            lifted_at    TIMESTAMPTZ,
            lifted_by    TEXT NOT NULL DEFAULT ''
        )
    """)
    _add("legal_hold_records", "hold_scope",    "TEXT NOT NULL DEFAULT 'case'")
    _add("legal_hold_records", "reason_code",   "TEXT NOT NULL DEFAULT 'operator_hold'")
    _add("legal_hold_records", "status",        "TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','RELEASED'))")
    _add("legal_hold_records", "approved_by",   "TEXT")
    _add("legal_hold_records", "effective_from","TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    _add("legal_hold_records", "evidence_id",   "UUID")
    _add("legal_hold_records", "correlation_id","UUID")
    _add("legal_hold_records", "trace_id",      "UUID")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_legal_hold_scope
        ON legal_hold_records (tenant_id, subject_id, status)
        WHERE status = 'ACTIVE'
    """)

    # ── 5. retention_policies ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS retention_policies (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id),
            policy_name      TEXT NOT NULL,
            data_class       TEXT NOT NULL,
            retention_class  TEXT NOT NULL,
            retention_days   INTEGER NOT NULL,
            archive_after_days INTEGER,
            purge_after_days   INTEGER,
            status           TEXT NOT NULL DEFAULT 'ACTIVE'
                             CHECK (status IN ('ACTIVE','SUPERSEDED','RETIRED')),
            created_by       TEXT NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, policy_name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_retention_policies_tenant ON retention_policies (tenant_id, status)")

    # ── 6. crypto_shred_requests ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS crypto_shred_requests (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id),
            subject_ref         TEXT NOT NULL,
            affected_key_ids    JSONB NOT NULL DEFAULT '[]',
            affected_record_ids JSONB NOT NULL DEFAULT '[]',
            legal_hold_checked  BOOLEAN NOT NULL DEFAULT FALSE,
            legal_hold_blocked  BOOLEAN NOT NULL DEFAULT FALSE,
            status              TEXT NOT NULL DEFAULT 'PENDING'
                                CHECK (status IN ('PENDING','IN_PROGRESS','COMPLETED','BLOCKED','FAILED')),
            requested_by        TEXT NOT NULL,
            completed_at        TIMESTAMPTZ,
            evidence_id         UUID,
            correlation_id      UUID,
            trace_id            UUID,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_crypto_shred_tenant ON crypto_shred_requests (tenant_id, status)")

    # ── 7. restore_jobs ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS restore_jobs (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id),
            restore_type   TEXT NOT NULL CHECK (restore_type IN (
                               'tenant_restore','case_restore','source_record_restore',
                               'evidence_restore','acr_restore','ledger_recovery_restore',
                               'regional_dr_restore','archive_restore','projection_rebuild'
                           )),
            restored_scope TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN (
                               'PENDING','IN_PROGRESS','DATA_RESTORED',
                               'VERIFICATION_PENDING','VERIFICATION_PASSED',
                               'VERIFICATION_FAILED','APPROVED_FOR_USE','FAILED'
                           )),
            requested_by   TEXT NOT NULL,
            approved_by    TEXT,
            approved_at    TIMESTAMPTZ,
            evidence_id    UUID,
            correlation_id UUID,
            trace_id       UUID,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_restore_jobs_tenant ON restore_jobs (tenant_id, status)")

    # ── 8. restore_verification_records ──────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS restore_verification_records (
            id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restore_job_id                  UUID NOT NULL REFERENCES restore_jobs(id),
            tenant_id                       UUID NOT NULL REFERENCES tenants(id),
            source_records_verified         BOOLEAN NOT NULL DEFAULT FALSE,
            evidence_chain_verified         BOOLEAN NOT NULL DEFAULT FALSE,
            acr_verified                    BOOLEAN NOT NULL DEFAULT FALSE,
            ledger_continuity_verified      BOOLEAN NOT NULL DEFAULT FALSE,
            tenant_isolation_verified       BOOLEAN NOT NULL DEFAULT FALSE,
            residency_verified              BOOLEAN NOT NULL DEFAULT FALSE,
            permissions_verified            BOOLEAN NOT NULL DEFAULT FALSE,
            legal_hold_verified             BOOLEAN NOT NULL DEFAULT FALSE,
            indexes_rebuilt                 BOOLEAN NOT NULL DEFAULT FALSE,
            projection_consistency_verified BOOLEAN NOT NULL DEFAULT FALSE,
            verification_status             TEXT NOT NULL DEFAULT 'PENDING'
                                            CHECK (verification_status IN ('PENDING','PASSED','FAILED')),
            verified_at                     TIMESTAMPTZ,
            evidence_id                     UUID,
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (restore_job_id)
        )
    """)

    # ── 9. archive_jobs ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS archive_jobs (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id),
            archive_scope       TEXT NOT NULL,
            record_ids          JSONB NOT NULL DEFAULT '[]',
            status              TEXT NOT NULL DEFAULT 'PENDING'
                                CHECK (status IN ('PENDING','IN_PROGRESS','COMPLETED','FAILED')),
            requested_by        TEXT NOT NULL,
            retention_policy_id UUID REFERENCES retention_policies(id),
            legal_hold_checked  BOOLEAN NOT NULL DEFAULT FALSE,
            integrity_metadata  JSONB NOT NULL DEFAULT '{}',
            completed_at        TIMESTAMPTZ,
            evidence_id         UUID,
            correlation_id      UUID,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_archive_jobs_tenant ON archive_jobs (tenant_id, status)")

    # ── 10. purge_jobs ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS purge_jobs (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id),
            purge_scope         TEXT NOT NULL,
            record_count        INTEGER NOT NULL DEFAULT 0,
            retention_policy_id UUID REFERENCES retention_policies(id),
            legal_hold_checked  BOOLEAN NOT NULL DEFAULT FALSE,
            legal_hold_blocked  BOOLEAN NOT NULL DEFAULT FALSE,
            approval_id         TEXT,
            approved_by         TEXT,
            approved_at         TIMESTAMPTZ,
            status              TEXT NOT NULL DEFAULT 'PENDING'
                                CHECK (status IN ('PENDING','APPROVED','IN_PROGRESS','COMPLETED','BLOCKED','FAILED')),
            completed_at        TIMESTAMPTZ,
            evidence_id         UUID,
            correlation_id      UUID,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_purge_jobs_tenant ON purge_jobs (tenant_id, status)")


def downgrade() -> None:
    for t in ["purge_jobs","archive_jobs","restore_verification_records",
              "restore_jobs","crypto_shred_requests","retention_policies"]:
        op.execute(f"DROP TABLE IF EXISTS {t}")

    for col in ["hold_scope","reason_code","status","approved_by",
                "effective_from","evidence_id","correlation_id","trace_id"]:
        op.execute(f"ALTER TABLE legal_hold_records DROP COLUMN IF EXISTS {col}")

    for table in _CLASS_A_TABLES:
        for col, _ in _CLASS_A_COLS:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")

    for table in _GOVERNED_TABLES:
        for col, _ in _MANDATORY_TEXT + _MANDATORY_UUID:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")

    for col in ["data_residency_region","residency_assigned_at","residency_assigned_by"]:
        op.execute(f"ALTER TABLE tenants DROP COLUMN IF EXISTS {col}")

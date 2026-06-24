"""Clarification 07 — Remaining field gaps after Slice 1 foundation (0030).

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-14

Fixes:
  Gap 1 — source_records missing legal_hold_status, trace_id, updated_by
           (was in _CLASS_A_TABLES but not _GOVERNED_TABLES in 0030)

  Gap 2 — §6.2 Class A mandatory fields not yet on Class A tables:
           immutable_after_status, integrity_hash, signature_key_id,
           supersedes_id, superseded_by_id

  Gap 3 — §6.3 Crypto-payload fields not yet on encrypted-payload tables:
           payload_key_region, payload_encryption_alg
           payload_hash_alg (evidence_bundles only — source_records already
           has raw_payload_hash_alg from migration 0020)
"""

from alembic import op

revision      = "0031"
down_revision = "0030"
branch_labels = None
depends_on    = None


def _add(table: str, col: str, defn: str):
    op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {defn}")


# Class A tables that hold immutable evidence-grade records
_CLASS_A_TABLES = [
    "source_records",
    "evidence_bundles",
    "action_certification_records",
    "ledger_entries",
    "recovery_proofs",
]

# Tables that carry encrypted payloads
_ENCRYPTED_PAYLOAD_TABLES = [
    "source_records",
    "evidence_bundles",
]


def upgrade() -> None:

    # ── Gap 1: source_records — mandatory governed-table fields ───────────────
    # 0030 added these to 12 tables but left source_records out of
    # _GOVERNED_TABLES (it was only in _CLASS_A_TABLES).
    _add("source_records", "legal_hold_status",
         "TEXT NOT NULL DEFAULT 'NONE' CHECK (legal_hold_status IN ('NONE','HELD'))")
    _add("source_records", "trace_id",  "UUID")
    _add("source_records", "updated_by", "TEXT")

    # ── Gap 2: §6.2 Class A mandatory fields ──────────────────────────────────
    for table in _CLASS_A_TABLES:
        # Declares at which FSM state the record becomes immutable
        _add(table, "immutable_after_status", "TEXT")

        # SHA-256 of the record's own canonical bytes — enables self-verification
        # after archive or restore without touching source data
        _add(table, "integrity_hash", "TEXT")

        # KMS key ID used to sign this record's integrity_hash
        _add(table, "signature_key_id", "TEXT")

        # Supersession chain — Class A records are corrected by supersession,
        # never by UPDATE. supersedes_id points to the record this row replaces;
        # superseded_by_id points to the row that replaced this one.
        _add(table, "supersedes_id",    "UUID")
        _add(table, "superseded_by_id", "UUID")

    # Partial index: fast lookup of live (non-superseded) Class A records
    for table in _CLASS_A_TABLES:
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table}_live
            ON {table} (tenant_id, superseded_by_id)
            WHERE superseded_by_id IS NULL
        """)

    # ── Gap 3: §6.3 Crypto-payload fields on encrypted-payload tables ─────────
    for table in _ENCRYPTED_PAYLOAD_TABLES:
        # KMS region that holds the DEK — required for cross-region shred
        _add(table, "payload_key_region", "TEXT")

        # Encryption algorithm used for the payload (e.g. AES-256-GCM)
        _add(table, "payload_encryption_alg",
             "TEXT NOT NULL DEFAULT 'AES-256-GCM'")

    # evidence_bundles needs payload_hash_alg; source_records already has
    # raw_payload_hash_alg from migration 0020 (same semantic, different name)
    _add("evidence_bundles", "payload_hash_alg",
         "TEXT NOT NULL DEFAULT 'sha-256'")

    # Indexes for legal hold queries on source_records
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_records_legal_hold
        ON source_records (tenant_id, legal_hold_status)
        WHERE legal_hold_status = 'HELD'
    """)

    # Indexes for integrity verification queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_records_integrity
        ON source_records (tenant_id, integrity_hash)
        WHERE integrity_hash IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_evidence_bundles_integrity
        ON evidence_bundles (tenant_id, integrity_hash)
        WHERE integrity_hash IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_acr_integrity
        ON action_certification_records (tenant_id, integrity_hash)
        WHERE integrity_hash IS NOT NULL
    """)


def downgrade() -> None:
    for table in _CLASS_A_TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_live")
        for col in ["immutable_after_status","integrity_hash","signature_key_id",
                    "supersedes_id","superseded_by_id"]:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")

    for table in _ENCRYPTED_PAYLOAD_TABLES:
        for col in ["payload_key_region","payload_encryption_alg"]:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")

    op.execute("ALTER TABLE evidence_bundles DROP COLUMN IF EXISTS payload_hash_alg")

    for col in ["legal_hold_status","trace_id","updated_by"]:
        op.execute(f"ALTER TABLE source_records DROP COLUMN IF EXISTS {col}")

    for table in ["source_records","evidence_bundles","action_certification_records"]:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_legal_hold")
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_integrity")

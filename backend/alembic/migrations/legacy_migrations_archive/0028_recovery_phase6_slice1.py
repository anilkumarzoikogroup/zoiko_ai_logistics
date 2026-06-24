"""Clarification 06 Slice 1 — financial recovery layer core schema.

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-14

Adds the Slice-1 tables for the financial recovery / reconciliation layer:
expected_recoveries, recovery_instruments, recovery_matches, ledger_entries,
write_offs, recovery_proofs. No RLS — tenant scoping via tenant_id filter,
matching the precedent set by carriers/api_keys/tenant_notification_settings
(0018/0026/0027).
"""
from __future__ import annotations
from alembic import op

revision      = "0028"
down_revision = "0027"
branch_labels = None
depends_on    = None


_RECOVERY_METHODS = """(
    'carrier_credit_memo','settlement_offset','refund_payment','invoice_adjustment',
    'future_bill_credit','partner_statement_credit','internal_adjustment','write_off',
    'chargeback_reversal','manual_recovery_evidence'
)"""


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS expected_recoveries (
            id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id                       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id                         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            authorization_decision_id       UUID NULL,
            counterparty_type               TEXT NOT NULL DEFAULT 'carrier',
            counterparty_id                 UUID NULL REFERENCES carriers(id),
            expected_amount                 NUMERIC(18,4) NOT NULL,
            currency                        TEXT NOT NULL DEFAULT 'INR',
            expected_recovery_method        TEXT NOT NULL DEFAULT 'carrier_credit_memo'
                CHECK (expected_recovery_method IN {_RECOVERY_METHODS}),
            expected_invoice_id             UUID NULL REFERENCES canonical_invoices(id),
            expected_external_invoice_ref   TEXT,
            tolerance_policy_id             TEXT NOT NULL DEFAULT 'recovery-match-tolerance-v1',
            status                          TEXT NOT NULL DEFAULT 'EXPECTED'
                CHECK (status IN (
                    'EXPECTED','AWAITING_INSTRUMENT','INSTRUMENT_RECEIVED','MATCHING',
                    'MATCHED_FULL','MATCHED_PARTIAL','OVER_RECOVERED','MISMATCHED',
                    'UNRECOVERABLE_PENDING_APPROVAL','WRITTEN_OFF','LEDGER_PENDING',
                    'LEDGER_CLOSED','ACR_READY'
                )),
            superseded_by                   UUID NULL REFERENCES expected_recoveries(id),
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_expected_recoveries_tenant_case
            ON expected_recoveries (tenant_id, case_id)
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS recovery_instruments (
            id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id                       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            instrument_type                 TEXT NOT NULL
                CHECK (instrument_type IN {_RECOVERY_METHODS}),
            counterparty_type               TEXT NOT NULL DEFAULT 'carrier',
            counterparty_id                 UUID NULL REFERENCES carriers(id),
            source_record_id                UUID NULL REFERENCES source_records(id),
            external_reference              TEXT,
            related_external_invoice_ref    TEXT,
            related_case_id                 UUID NULL REFERENCES cases(id),
            instrument_amount               NUMERIC(18,4) NOT NULL,
            currency                        TEXT NOT NULL DEFAULT 'INR',
            instrument_date                 DATE,
            received_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            status                          TEXT NOT NULL DEFAULT 'AVAILABLE'
                CHECK (status IN ('AVAILABLE','CONSUMED','REVERSED')),
            created_by                      TEXT NOT NULL,
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_recovery_instruments_tenant_case
            ON recovery_instruments (tenant_id, related_case_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS recovery_matches (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id                UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            expected_recovery_id     UUID NOT NULL REFERENCES expected_recoveries(id),
            recovery_instrument_id   UUID NOT NULL REFERENCES recovery_instruments(id),
            match_tier               SMALLINT NOT NULL,
            match_method             TEXT NOT NULL,
            match_confidence         NUMERIC(5,4) NOT NULL DEFAULT 1.0,
            matched_amount           NUMERIC(18,4) NOT NULL,
            expected_amount          NUMERIC(18,4) NOT NULL,
            variance                 NUMERIC(18,4) NOT NULL DEFAULT 0,
            currency                 TEXT NOT NULL DEFAULT 'INR',
            allocation_status        TEXT NOT NULL
                CHECK (allocation_status IN ('FULL','PARTIAL','OVER','MISMATCH','REVIEW_REQUIRED','REVERSED')),
            matched_by               TEXT NOT NULL,
            matched_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_recovery_matches_tenant_expected
            ON recovery_matches (tenant_id, expected_recovery_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS ledger_entries (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id                   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id                     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            entry_type                  TEXT NOT NULL
                CHECK (entry_type IN (
                    'RECOVERY_RECEIVABLE_CREATED','RECOVERY_CREDIT_APPLIED','RECOVERY_REFUND_RECEIVED',
                    'RECOVERY_PARTIAL_APPLIED','RECOVERY_WRITE_OFF_POSTED','OVER_RECOVERY_PENDING_REVIEW',
                    'LEDGER_EXEMPT_APPROVED','REVERSAL'
                )),
            amount                      NUMERIC(18,4) NOT NULL,
            currency                    TEXT NOT NULL DEFAULT 'INR',
            debit_account               TEXT NOT NULL,
            credit_account              TEXT NOT NULL,
            source_recovery_match_id    UUID NULL REFERENCES recovery_matches(id),
            reversal_of_entry_id        UUID NULL REFERENCES ledger_entries(id),
            status                      TEXT NOT NULL DEFAULT 'POSTED'
                CHECK (status IN ('POSTED','EXPORT_PENDING','EXPORTED','EXPORT_CONFIRMED','EXEMPT')),
            posted_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_ledger_entries_tenant_case
            ON ledger_entries (tenant_id, case_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS write_offs (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id                UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id                  UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            expected_recovery_id     UUID NOT NULL REFERENCES expected_recoveries(id),
            amount                   NUMERIC(18,4) NOT NULL,
            currency                 TEXT NOT NULL DEFAULT 'INR',
            reason_code              TEXT NOT NULL
                CHECK (reason_code IN (
                    'counterparty_rejection','below_pursuit_threshold','window_expired',
                    'insufficient_documentation','uneconomic_pursuit','commercial_decision',
                    'residual_immateriality'
                )),
            policy_version_id        TEXT NOT NULL DEFAULT 'writeoff-policy-v1',
            authorized_by            TEXT,
            authorized_at            TIMESTAMPTZ,
            ledger_entry_id          UUID NULL REFERENCES ledger_entries(id),
            status                   TEXT NOT NULL DEFAULT 'REQUESTED'
                CHECK (status IN ('REQUESTED','AUTHORIZED','POSTED','REJECTED')),
            created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_write_offs_tenant_case
            ON write_offs (tenant_id, case_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS recovery_proofs (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id                   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id                     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            claimed_amount              NUMERIC(18,4) NOT NULL,
            currency                    TEXT NOT NULL DEFAULT 'INR',
            expected_recovery_ids       JSONB NOT NULL DEFAULT '[]',
            recovery_instrument_ids     JSONB NOT NULL DEFAULT '[]',
            recovery_match_ids          JSONB NOT NULL DEFAULT '[]',
            ledger_entry_ids            JSONB NOT NULL DEFAULT '[]',
            total_expected              NUMERIC(18,4) NOT NULL,
            total_recovered             NUMERIC(18,4) NOT NULL DEFAULT 0,
            total_unrecovered           NUMERIC(18,4) NOT NULL DEFAULT 0,
            recovery_status             TEXT NOT NULL
                CHECK (recovery_status IN (
                    'RECOVERED_FULL','RECOVERED_PARTIAL','UNRECOVERABLE_APPROVED','REJECTED_BY_COUNTERPARTY',
                    'OVER_RECOVERED','MISMATCHED','AWAITING_INSTRUMENT','LEDGER_PENDING'
                )),
            ledger_status               TEXT NOT NULL
                CHECK (ledger_status IN ('LEDGER_PENDING','LEDGER_CLOSED','LEDGER_EXEMPT')),
            acr_ready                   BOOLEAN NOT NULL DEFAULT FALSE,
            superseded_by               UUID NULL REFERENCES recovery_proofs(id),
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_recovery_proofs_tenant_case
            ON recovery_proofs (tenant_id, case_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recovery_proofs")
    op.execute("DROP TABLE IF EXISTS write_offs")
    op.execute("DROP TABLE IF EXISTS ledger_entries")
    op.execute("DROP TABLE IF EXISTS recovery_matches")
    op.execute("DROP TABLE IF EXISTS recovery_instruments")
    op.execute("DROP TABLE IF EXISTS expected_recoveries")

"""Add all missing domain tables: identity, ingestion, canonical truth,
   case management, decision, governance, execution, evaluation.

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-09
"""
from __future__ import annotations
from alembic import op

revision      = "0019"
down_revision = "0018"
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # ── Identity & Tenant ──────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_units (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            code        TEXT NOT NULL DEFAULT '',
            parent_id   UUID REFERENCES business_units(id),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, name)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS approval_groups (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name          TEXT NOT NULL,
            description   TEXT NOT NULL DEFAULT '',
            min_approvers INT  NOT NULL DEFAULT 1,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, name)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS approval_group_members (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            approval_group_id UUID NOT NULL REFERENCES approval_groups(id) ON DELETE CASCADE,
            user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            added_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (approval_group_id, user_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS threshold_profiles (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            currency        TEXT NOT NULL DEFAULT 'USD',
            auto_approve_below   NUMERIC(18,4) NOT NULL DEFAULT 0,
            require_approval_above NUMERIC(18,4) NOT NULL DEFAULT 1000,
            escalate_above   NUMERIC(18,4) NOT NULL DEFAULT 10000,
            approval_group_id UUID REFERENCES approval_groups(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, name)
        )
    """)

    # ── Ingestion & Connectors ─────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS connectors (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name                TEXT NOT NULL,
            connector_type      TEXT NOT NULL DEFAULT 'API',
            auth_method         TEXT NOT NULL DEFAULT 'API_KEY',
            trust_tier          TEXT NOT NULL DEFAULT 'T2',
            certification_state TEXT NOT NULL DEFAULT 'Draft',
            operational_state   TEXT NOT NULL DEFAULT 'healthy',
            endpoint_url        TEXT NOT NULL DEFAULT '',
            credentials_ref     TEXT NOT NULL DEFAULT '',
            rate_limit_rps      INT  NOT NULL DEFAULT 10,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, name)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_runs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            connector_id    UUID NOT NULL REFERENCES connectors(id),
            status          TEXT NOT NULL DEFAULT 'RUNNING',
            records_received INT NOT NULL DEFAULT 0,
            records_accepted INT NOT NULL DEFAULT 0,
            records_rejected INT NOT NULL DEFAULT 0,
            started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at    TIMESTAMPTZ,
            error_detail    TEXT NOT NULL DEFAULT ''
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS quarantine_items (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            source_record_id UUID REFERENCES source_records(id),
            reason           TEXT NOT NULL DEFAULT '',
            raw_payload      JSONB NOT NULL DEFAULT '{}',
            quarantined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            released_at      TIMESTAMPTZ,
            released_by      TEXT NOT NULL DEFAULT ''
        )
    """)

    # ── Canonical Truth Domain ─────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS facilities (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            facility_type TEXT NOT NULL DEFAULT 'WAREHOUSE',
            address     TEXT NOT NULL DEFAULT '',
            country     TEXT NOT NULL DEFAULT '',
            latitude    NUMERIC(10,6),
            longitude   NUMERIC(10,6),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, name)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            shipment_number     TEXT NOT NULL DEFAULT '',
            origin_facility_id  UUID REFERENCES facilities(id),
            dest_facility_id    UUID REFERENCES facilities(id),
            carrier_id          UUID REFERENCES carriers(id),
            status              TEXT NOT NULL DEFAULT 'PENDING',
            transport_mode      TEXT NOT NULL DEFAULT 'TRUCKLOAD',
            scheduled_pickup    TIMESTAMPTZ,
            actual_pickup       TIMESTAMPTZ,
            scheduled_delivery  TIMESTAMPTZ,
            actual_delivery     TIMESTAMPTZ,
            total_weight_kg     NUMERIC(12,4) NOT NULL DEFAULT 0,
            total_volume_m3     NUMERIC(12,4) NOT NULL DEFAULT 0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS shipment_legs (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            shipment_id    UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
            tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            leg_sequence   INT  NOT NULL DEFAULT 1,
            carrier_id     UUID REFERENCES carriers(id),
            origin         TEXT NOT NULL DEFAULT '',
            destination    TEXT NOT NULL DEFAULT '',
            transport_mode TEXT NOT NULL DEFAULT 'TRUCKLOAD',
            departure_at   TIMESTAMPTZ,
            arrival_at     TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS invoice_lines (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            canonical_invoice_id UUID REFERENCES canonical_invoices(id) ON DELETE CASCADE,
            line_number         INT  NOT NULL DEFAULT 1,
            charge_code         TEXT NOT NULL DEFAULT '',
            description         TEXT NOT NULL DEFAULT '',
            quantity            NUMERIC(12,4) NOT NULL DEFAULT 1,
            unit_price          NUMERIC(18,4) NOT NULL DEFAULT 0,
            total_amount        NUMERIC(18,4) NOT NULL DEFAULT 0,
            currency            TEXT NOT NULL DEFAULT 'USD',
            is_disputed         BOOLEAN NOT NULL DEFAULT FALSE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS contract_clauses (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            contract_rate_id UUID REFERENCES contract_rates(id) ON DELETE CASCADE,
            clause_type      TEXT NOT NULL DEFAULT 'RATE',
            description      TEXT NOT NULL DEFAULT '',
            value_expression TEXT NOT NULL DEFAULT '',
            effective_from   DATE,
            effective_to     DATE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id         UUID REFERENCES cases(id),
            shipment_id     UUID REFERENCES shipments(id),
            claim_type      TEXT NOT NULL DEFAULT 'OVERCHARGE',
            claimed_amount  NUMERIC(18,4) NOT NULL DEFAULT 0,
            approved_amount NUMERIC(18,4),
            currency        TEXT NOT NULL DEFAULT 'USD',
            status          TEXT NOT NULL DEFAULT 'OPEN',
            filed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at     TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS proofs_of_delivery (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            shipment_id     UUID REFERENCES shipments(id),
            signed_by       TEXT NOT NULL DEFAULT '',
            signed_at       TIMESTAMPTZ,
            document_url    TEXT NOT NULL DEFAULT '',
            content_hash    TEXT NOT NULL DEFAULT '',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Case & Task Management ─────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            task_type       TEXT NOT NULL DEFAULT 'REVIEW',
            assigned_to     TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'PENDING',
            due_at          TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ,
            notes           TEXT NOT NULL DEFAULT '',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS case_timeline_entries (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            event_type  TEXT NOT NULL,
            actor       TEXT NOT NULL DEFAULT 'system',
            summary     TEXT NOT NULL DEFAULT '',
            payload     JSONB NOT NULL DEFAULT '{}',
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Decision & Reasoning ───────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS rule_traces (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id         UUID REFERENCES cases(id),
            validator_name  TEXT NOT NULL DEFAULT '',
            rule_id         TEXT NOT NULL DEFAULT '',
            input_payload   JSONB NOT NULL DEFAULT '{}',
            output_payload  JSONB NOT NULL DEFAULT '{}',
            result          TEXT NOT NULL DEFAULT 'PASS',
            executed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS confidence_assessments (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            subject_type        TEXT NOT NULL,
            subject_id          UUID NOT NULL,
            score               NUMERIC(5,4) NOT NULL DEFAULT 0,
            calibration_version TEXT NOT NULL DEFAULT '1.0',
            model_id            TEXT NOT NULL DEFAULT '',
            assessed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS explanation_artifacts (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id      UUID REFERENCES cases(id),
            subject_type TEXT NOT NULL DEFAULT 'finding',
            subject_id   UUID,
            explanation  TEXT NOT NULL DEFAULT '',
            format       TEXT NOT NULL DEFAULT 'markdown',
            generated_by TEXT NOT NULL DEFAULT 'system',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Document Management ────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id         UUID REFERENCES cases(id),
            document_type   TEXT NOT NULL DEFAULT 'INVOICE',
            file_name       TEXT NOT NULL DEFAULT '',
            mime_type       TEXT NOT NULL DEFAULT '',
            content_hash    TEXT NOT NULL DEFAULT '',
            storage_uri     TEXT NOT NULL DEFAULT '',
            size_bytes      BIGINT NOT NULL DEFAULT 0,
            retention_class TEXT NOT NULL DEFAULT 'STANDARD',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS retention_markers (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            subject_type    TEXT NOT NULL,
            subject_id      UUID NOT NULL,
            retention_class TEXT NOT NULL DEFAULT 'STANDARD',
            retain_until    TIMESTAMPTZ,
            reason          TEXT NOT NULL DEFAULT '',
            applied_by      TEXT NOT NULL DEFAULT 'system',
            applied_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

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

    # ── Governance ─────────────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_packs (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            version      TEXT NOT NULL DEFAULT '1.0',
            policy_data  JSONB NOT NULL DEFAULT '{}',
            status       TEXT NOT NULL DEFAULT 'Draft',
            promoted_by  TEXT NOT NULL DEFAULT '',
            promoted_at  TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, name, version)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS override_records (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            case_id         UUID REFERENCES cases(id),
            override_type   TEXT NOT NULL DEFAULT 'MANUAL',
            original_decision TEXT NOT NULL DEFAULT '',
            override_decision TEXT NOT NULL DEFAULT '',
            reason          TEXT NOT NULL DEFAULT '',
            actor           TEXT NOT NULL DEFAULT '',
            approved_by     TEXT NOT NULL DEFAULT '',
            occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Execution ──────────────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS dispatch_tickets (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id             UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            execution_envelope_id UUID REFERENCES execution_envelopes(id),
            connector_id          UUID REFERENCES connectors(id),
            idempotency_key       TEXT NOT NULL DEFAULT '',
            status                TEXT NOT NULL DEFAULT 'PREPARED',
            retry_count           INT  NOT NULL DEFAULT 0,
            last_error            TEXT NOT NULL DEFAULT '',
            dispatched_at         TIMESTAMPTZ,
            acknowledged_at       TIMESTAMPTZ,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS external_acknowledgments (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            dispatch_ticket_id UUID REFERENCES dispatch_tickets(id),
            case_id          UUID REFERENCES cases(id),
            ack_reference    TEXT NOT NULL DEFAULT '',
            ack_payload      JSONB NOT NULL DEFAULT '{}',
            received_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Evaluation & Drift ─────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_runs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            run_type         TEXT NOT NULL DEFAULT 'PRECISION',
            model_version    TEXT NOT NULL DEFAULT '',
            cases_evaluated  INT  NOT NULL DEFAULT 0,
            precision_score  NUMERIC(5,4),
            recall_score     NUMERIC(5,4),
            override_rate    NUMERIC(5,4),
            recovery_amount  NUMERIC(18,4),
            status           TEXT NOT NULL DEFAULT 'RUNNING',
            started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at     TIMESTAMPTZ,
            result_payload   JSONB NOT NULL DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS drift_signals (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            evaluation_run_id UUID REFERENCES evaluation_runs(id),
            signal_type       TEXT NOT NULL DEFAULT 'PRECISION_DROP',
            severity          TEXT NOT NULL DEFAULT 'LOW',
            metric_name       TEXT NOT NULL DEFAULT '',
            baseline_value    NUMERIC(10,6),
            current_value     NUMERIC(10,6),
            delta             NUMERIC(10,6),
            description       TEXT NOT NULL DEFAULT '',
            detected_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reviewed_at       TIMESTAMPTZ,
            reviewed_by       TEXT NOT NULL DEFAULT ''
        )
    """)


def downgrade() -> None:
    tables = [
        "drift_signals", "evaluation_runs",
        "external_acknowledgments", "dispatch_tickets",
        "override_records", "policy_packs",
        "legal_hold_records", "retention_markers", "documents",
        "explanation_artifacts", "confidence_assessments", "rule_traces",
        "case_timeline_entries", "tasks",
        "proofs_of_delivery", "claims", "contract_clauses",
        "invoice_lines", "shipment_legs", "shipments", "facilities",
        "quarantine_items", "ingestion_runs", "connectors",
        "threshold_profiles", "approval_group_members",
        "approval_groups", "business_units",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

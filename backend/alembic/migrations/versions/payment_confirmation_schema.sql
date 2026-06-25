-- Migration 0003 — Payment confirmation on recovery instruments + email notification log
--
-- Adds:
--   recovery_instruments.payment_confirmed      BOOLEAN  — set true when carrier confirms actual payment
--   recovery_instruments.payment_confirmed_at   TIMESTAMPTZ — when confirmation was received
--   recovery_instruments.payment_confirmed_ref  TEXT    — carrier's payment reference / bank ref
--   email_notification_log                      TABLE   — audit trail of every outbound notification

ALTER TABLE recovery_instruments
    ADD COLUMN IF NOT EXISTS payment_confirmed      BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS payment_confirmed_at   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS payment_confirmed_ref  TEXT;

-- Index for fast "show all confirmed instruments for case X" lookup
CREATE INDEX IF NOT EXISTS idx_recovery_instruments_payment_confirmed
    ON recovery_instruments (related_case_id, payment_confirmed)
    WHERE payment_confirmed = TRUE;

-- Email notification audit log (append-only, never DELETE)
CREATE TABLE IF NOT EXISTS email_notification_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    event_type      TEXT        NOT NULL,   -- overcharge_detected | approval_needed | recovery_executed | payment_confirmed | claim_submitted
    recipient_email TEXT        NOT NULL,
    recipient_role  TEXT,
    case_id         UUID,
    subject         TEXT,
    amount          NUMERIC(18,2),
    currency        TEXT,
    status          TEXT        NOT NULL DEFAULT 'SENT',  -- SENT | FAILED | SKIPPED
    error_detail    TEXT,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_notification_log_tenant_case
    ON email_notification_log (tenant_id, case_id);
CREATE INDEX IF NOT EXISTS idx_email_notification_log_event
    ON email_notification_log (event_type, sent_at DESC);

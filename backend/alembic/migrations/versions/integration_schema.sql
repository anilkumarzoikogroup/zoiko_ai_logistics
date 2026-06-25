-- ===== SC-002 lift: cases table gains claim awareness =====
-- Compatible with PostgreSQL 13+.  No PostgreSQL-17-only ADD CONSTRAINT NOT NULL syntax.

ALTER TABLE cases ADD COLUMN IF NOT EXISTS claim_id UUID;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_type TEXT NOT NULL DEFAULT 'INVOICE_OVERCHARGE'::text;

CREATE TABLE IF NOT EXISTS claim_lines (
    id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    claim_id UUID NOT NULL,
    line_number INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT ''::text,
    claimed_amount NUMERIC NOT NULL,
    currency TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS claims (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID,
    shipment_id UUID,
    claim_type TEXT NOT NULL DEFAULT 'OVERCHARGE'::text,
    claimed_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    approved_amount NUMERIC(18,4),
    currency TEXT NOT NULL DEFAULT 'USD'::text,
    status TEXT NOT NULL DEFAULT 'OPEN'::text,
    filed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    source_record_id UUID,
    carrier_id TEXT NOT NULL DEFAULT ''::text,
    claim_hash BYTEA,
    claim_reference TEXT NOT NULL DEFAULT ''::text
);

ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_pkey PRIMARY KEY (id);
ALTER TABLE claims ADD CONSTRAINT claims_pkey PRIMARY KEY (id);

-- Idempotent constraint additions using DO blocks (safe on PG 13+)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='cases_case_type_check' AND conrelid='cases'::regclass) THEN
        ALTER TABLE cases ADD CONSTRAINT cases_case_type_check
            CHECK (case_type = ANY (ARRAY['INVOICE_OVERCHARGE'::text, 'CARRIER_CLAIM'::text]));
    END IF;
END; $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_cases_subject' AND conrelid='cases'::regclass) THEN
        ALTER TABLE cases ADD CONSTRAINT chk_cases_subject CHECK (
            ((case_type = 'INVOICE_OVERCHARGE'::text) AND (invoice_id IS NOT NULL) AND (claim_id IS NULL))
            OR
            ((case_type = 'CARRIER_CLAIM'::text)      AND (claim_id IS NOT NULL)  AND (invoice_id IS NULL))
        );
    END IF;
END; $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_claims_status' AND conrelid='claims'::regclass) THEN
        ALTER TABLE claims ADD CONSTRAINT chk_claims_status
            CHECK (status = ANY (ARRAY['OPEN','SUBMITTED','UNDER_CARRIER_REVIEW','COUNTERED',
                                       'PARTIALLY_ACCEPTED','ACCEPTED','REJECTED','WITHDRAWN','CLOSED']));
    END IF;
END; $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='cases_claim_id_fkey' AND conrelid='cases'::regclass) THEN
        ALTER TABLE cases ADD CONSTRAINT cases_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES claims(id);
    END IF;
END; $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='claim_lines_claim_id_fkey' AND conrelid='claim_lines'::regclass) THEN
        ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES claims(id);
    END IF;
END; $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='claim_lines_tenant_id_fkey' AND conrelid='claim_lines'::regclass) THEN
        ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
    END IF;
END; $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='claims_case_id_fkey' AND conrelid='claims'::regclass) THEN
        ALTER TABLE claims ADD CONSTRAINT claims_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
    END IF;
END; $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='claims_tenant_id_fkey' AND conrelid='claims'::regclass) THEN
        ALTER TABLE claims ADD CONSTRAINT claims_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
END; $$;

-- Use standard SET NOT NULL instead of PG-17-only ADD CONSTRAINT ... NOT NULL
ALTER TABLE cases ALTER COLUMN case_type SET NOT NULL;

-- Unique indexes required by ON CONFLICT clauses in application code
CREATE UNIQUE INDEX IF NOT EXISTS uq_cases_tenant_claim
    ON cases (tenant_id, claim_id)
    WHERE claim_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_claim_lines_tenant
    ON claim_lines (tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_claim_lines_claim_line
    ON claim_lines (claim_id, line_number);

CREATE UNIQUE INDEX IF NOT EXISTS uq_claims_tenant_reference
    ON claims (tenant_id, claim_reference)
    WHERE claim_reference <> '';

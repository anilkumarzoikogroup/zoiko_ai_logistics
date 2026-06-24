-- ===== SC-002 lift: cases table gains claim awareness =====

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
ALTER TABLE cases ADD CONSTRAINT cases_case_type_check CHECK ((case_type = ANY (ARRAY['INVOICE_OVERCHARGE'::text, 'CARRIER_CLAIM'::text])));
ALTER TABLE cases ADD CONSTRAINT chk_cases_subject CHECK ((((case_type = 'INVOICE_OVERCHARGE'::text) AND (invoice_id IS NOT NULL) AND (claim_id IS NULL)) OR ((case_type = 'CARRIER_CLAIM'::text) AND (claim_id IS NOT NULL) AND (invoice_id IS NULL))));
ALTER TABLE claims ADD CONSTRAINT chk_claims_status CHECK ((status = ANY (ARRAY['OPEN'::text, 'SUBMITTED'::text, 'UNDER_CARRIER_REVIEW'::text, 'COUNTERED'::text, 'PARTIALLY_ACCEPTED'::text, 'ACCEPTED'::text, 'REJECTED'::text, 'WITHDRAWN'::text, 'CLOSED'::text])));
ALTER TABLE cases ADD CONSTRAINT cases_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES claims(id);
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES claims(id);
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE claims ADD CONSTRAINT claims_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE claims ADD CONSTRAINT claims_shipment_id_fkey FOREIGN KEY (shipment_id) REFERENCES shipments(id);
ALTER TABLE claims ADD CONSTRAINT claims_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE claims ADD CONSTRAINT claims_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE cases ADD CONSTRAINT cases_case_type_not_null NOT NULL case_type;
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_claim_id_not_null NOT NULL claim_id;
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_claimed_amount_not_null NOT NULL claimed_amount;
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_created_at_not_null NOT NULL created_at;
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_currency_not_null NOT NULL currency;
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_description_not_null NOT NULL description;
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_id_not_null NOT NULL id;
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_line_number_not_null NOT NULL line_number;
ALTER TABLE claim_lines ADD CONSTRAINT claim_lines_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE claims ADD CONSTRAINT claims_carrier_id_not_null NOT NULL carrier_id;
ALTER TABLE claims ADD CONSTRAINT claims_claim_reference_not_null NOT NULL claim_reference;
ALTER TABLE claims ADD CONSTRAINT claims_claim_type_not_null NOT NULL claim_type;
ALTER TABLE claims ADD CONSTRAINT claims_claimed_amount_not_null NOT NULL claimed_amount;
ALTER TABLE claims ADD CONSTRAINT claims_created_at_not_null NOT NULL created_at;
ALTER TABLE claims ADD CONSTRAINT claims_currency_not_null NOT NULL currency;
ALTER TABLE claims ADD CONSTRAINT claims_filed_at_not_null NOT NULL filed_at;
ALTER TABLE claims ADD CONSTRAINT claims_id_not_null NOT NULL id;
ALTER TABLE claims ADD CONSTRAINT claims_status_not_null NOT NULL status;
ALTER TABLE claims ADD CONSTRAINT claims_tenant_id_not_null NOT NULL tenant_id;
CREATE UNIQUE INDEX uq_cases_tenant_claim ON public.cases USING btree (tenant_id, claim_id) WHERE (claim_id IS NOT NULL);
CREATE INDEX ix_claim_lines_tenant ON public.claim_lines USING btree (tenant_id);
CREATE UNIQUE INDEX uq_claim_lines_claim_line ON public.claim_lines USING btree (claim_id, line_number);
CREATE UNIQUE INDEX uq_claims_tenant_reference ON public.claims USING btree (tenant_id, claim_reference) WHERE (claim_reference <> ''::text);

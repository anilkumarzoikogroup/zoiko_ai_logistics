-- ============================================================
-- Zoiko unified baseline schema (105 shared platform-spine tables)
-- Generated from live DB introspection + validated against a throwaway
-- database (zoiko_schema_test) for exact structural fidelity.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


CREATE TABLE IF NOT EXISTS action_certification_records (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    acr_version TEXT NOT NULL DEFAULT 'v1'::text,
    merkle_root BYTEA NOT NULL,
    artifact_hashes JSONB NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    worm_object_name TEXT,
    certified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    closure_reason TEXT,
    recovered_amount NUMERIC(18,4),
    currency TEXT NOT NULL DEFAULT 'USD'::text,
    supersedes_acr_id UUID,
    superseded_by_acr_id UUID,
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID,
    retention_until TIMESTAMP WITH TIME ZONE,
    archive_after TIMESTAMP WITH TIME ZONE,
    purge_after TIMESTAMP WITH TIME ZONE,
    crypto_shred_status TEXT NOT NULL DEFAULT 'ACTIVE'::text,
    archive_eligible BOOLEAN NOT NULL DEFAULT false,
    immutable_after_status TEXT,
    integrity_hash TEXT,
    signature_key_id TEXT,
    supersedes_id UUID,
    superseded_by_id UUID
);

CREATE TABLE IF NOT EXISTS action_intents (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    proposal_id UUID,
    action_type TEXT NOT NULL,
    policy_version TEXT NOT NULL DEFAULT 'v1.0.0'::text,
    agent_id TEXT NOT NULL DEFAULT 'zoiko.agent.freight_dispute.v1'::text,
    declared_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    rationale TEXT
);

CREATE TABLE IF NOT EXISTS action_plans (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    recommended_action TEXT NOT NULL,
    expected_outcome TEXT NOT NULL,
    claimed_amount NUMERIC(18,4),
    currency TEXT NOT NULL DEFAULT 'USD'::text,
    evidence_bundle_id UUID,
    risk_level TEXT NOT NULL DEFAULT 'medium'::text,
    authorization_required BOOLEAN NOT NULL DEFAULT true,
    required_approval_policy_id TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_tool_permissions (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tool_name TEXT NOT NULL,
    allowed BOOLEAN NOT NULL DEFAULT true,
    description TEXT NOT NULL DEFAULT ''::text,
    requires_approval BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ambiguity_queue (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_record_id UUID NOT NULL,
    original_record_id UUID NOT NULL,
    external_source_ref TEXT NOT NULL,
    reason TEXT NOT NULL,
    resolution TEXT,
    resolved_by UUID,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    scopes TEXT NOT NULL DEFAULT 'read:*'::text,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS approval_decisions (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    approval_request_id UUID NOT NULL,
    actor_sub TEXT NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT,
    decided_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approval_group_members (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    approval_group_id UUID NOT NULL,
    user_id UUID NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approval_groups (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''::text,
    min_approvers INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    approval_level TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    approver_1_sub TEXT,
    approver_2_sub TEXT,
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    deadline_at TIMESTAMP WITH TIME ZONE NOT NULL,
    actioned_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS approval_tasks (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    proposer_sub TEXT NOT NULL,
    actor_sub TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    actioned_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    approval_level TEXT DEFAULT 'SINGLE'::text,
    deadline_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS approval_thresholds (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'::text,
    auto_approve_below NUMERIC(15,2),
    dual_auth_above NUMERIC(15,2),
    escalate_after_hours INTEGER NOT NULL DEFAULT 24,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS archive_jobs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    archive_scope TEXT NOT NULL,
    record_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    requested_by TEXT NOT NULL,
    retention_policy_id UUID,
    legal_hold_checked BOOLEAN NOT NULL DEFAULT false,
    integrity_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    completed_at TIMESTAMP WITH TIME ZONE,
    evidence_id UUID,
    correlation_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS assertion_results (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    assertion_name TEXT NOT NULL,
    gate_number INTEGER,
    expected TEXT,
    actual TEXT,
    passed BOOLEAN NOT NULL DEFAULT false,
    error_message TEXT,
    duration_ms INTEGER,
    asserted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_chains (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    acr_id UUID,
    chain_root_hash BYTEA NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    events_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    sealed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    sealed_by TEXT NOT NULL DEFAULT 'system'::text
);

CREATE TABLE IF NOT EXISTS audit_worm_index (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    acr_id UUID NOT NULL,
    worm_bucket TEXT NOT NULL,
    object_name TEXT NOT NULL,
    object_hash BYTEA NOT NULL,
    indexed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS authorization_decisions (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    action_plan_id UUID NOT NULL,
    action_type TEXT NOT NULL,
    decision TEXT NOT NULL,
    policy_version_id TEXT NOT NULL,
    required_approvals JSONB NOT NULL DEFAULT '[]'::jsonb,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    decided_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    decided_by TEXT NOT NULL,
    evidence_id UUID
);

CREATE TABLE IF NOT EXISTS batch_artifacts (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    channel TEXT NOT NULL DEFAULT 'file_upload'::text,
    submitted_by_user_id UUID,
    declared_schema TEXT NOT NULL DEFAULT 'freight-invoice-batch-v1'::text,
    declared_record_count INTEGER NOT NULL DEFAULT 0,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    batch_payload_hash TEXT,
    batch_payload_size_bytes BIGINT,
    processing_status TEXT NOT NULL DEFAULT 'RECEIVED'::text,
    total_records INTEGER NOT NULL DEFAULT 0,
    first_seen_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    ambiguous_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    quarantined_count INTEGER NOT NULL DEFAULT 0,
    processed_count INTEGER NOT NULL DEFAULT 0,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_detail TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS batch_records (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    source_record_id UUID,
    record_index INTEGER NOT NULL,
    external_source_ref TEXT,
    outcome TEXT NOT NULL DEFAULT 'PENDING'::text,
    error_detail TEXT,
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS business_units (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    code TEXT NOT NULL DEFAULT ''::text,
    parent_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS canonical_invoices (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_record_id UUID NOT NULL,
    invoice_number TEXT NOT NULL,
    carrier_id TEXT NOT NULL,
    total_amount NUMERIC(18,4) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD'::text,
    canonical_hash BYTEA NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    predecessor_version_hash BYTEA,
    invoice_date TEXT NOT NULL DEFAULT ''::text,
    transport_mode TEXT NOT NULL DEFAULT ''::text,
    charge_lines JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS canonical_shipments (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    origin_city TEXT NOT NULL,
    dest_city TEXT NOT NULL,
    weight_lbs NUMERIC(12,2),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    mode TEXT NOT NULL DEFAULT 'TRUCKLOAD'::text,
    equipment_type TEXT NOT NULL DEFAULT ''::text
);

CREATE TABLE IF NOT EXISTS carriers (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT ''::text,
    address TEXT NOT NULL DEFAULT ''::text,
    contact_person TEXT NOT NULL DEFAULT ''::text,
    contact_phone TEXT NOT NULL DEFAULT ''::text,
    cc_emails TEXT NOT NULL DEFAULT ''::text,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS case_candidates (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    candidate_type TEXT NOT NULL,
    finding_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    grouping_key TEXT NOT NULL,
    aggregate_amount NUMERIC(18,4),
    currency TEXT NOT NULL DEFAULT 'USD'::text,
    recommended_case_type TEXT NOT NULL,
    recommended_priority TEXT NOT NULL DEFAULT 'medium'::text,
    promotion_policy_id TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    promoted_case_id UUID,
    rejection_reason TEXT,
    decided_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS case_events (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT,
    actor_sub TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS case_timeline_entries (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system'::text,
    summary TEXT NOT NULL DEFAULT ''::text,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cases (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    invoice_id UUID,
    state TEXT NOT NULL DEFAULT 'NEW'::text,
    opened_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    closed_at TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL DEFAULT 1,
    closure_reason TEXT,
    primary_case_id UUID,
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID
);

CREATE TABLE IF NOT EXISTS certification_runs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID,
    run_type TEXT NOT NULL,
    target_service TEXT NOT NULL,
    policy_version TEXT NOT NULL DEFAULT 'v1.0.0'::text,
    total_assertions INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'RUNNING'::text,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    completed_at TIMESTAMP WITH TIME ZONE,
    triggered_by TEXT NOT NULL DEFAULT 'system'::text
);



CREATE TABLE IF NOT EXISTS confidence_assessments (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id UUID NOT NULL,
    score NUMERIC(5,4) NOT NULL DEFAULT 0,
    calibration_version TEXT NOT NULL DEFAULT '1.0'::text,
    model_id TEXT NOT NULL DEFAULT ''::text,
    assessed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS connector_responses (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    envelope_id UUID NOT NULL,
    connector_id TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_body JSONB,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS connectors (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    connector_type TEXT NOT NULL DEFAULT 'API'::text,
    auth_method TEXT NOT NULL DEFAULT 'API_KEY'::text,
    trust_tier TEXT NOT NULL DEFAULT 'T2'::text,
    certification_state TEXT NOT NULL DEFAULT 'Draft'::text,
    operational_state TEXT NOT NULL DEFAULT 'healthy'::text,
    endpoint_url TEXT NOT NULL DEFAULT ''::text,
    credentials_ref TEXT NOT NULL DEFAULT ''::text,
    rate_limit_rps INTEGER NOT NULL DEFAULT 10,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    source_type TEXT NOT NULL DEFAULT ''::text
);

CREATE TABLE IF NOT EXISTS contract_clauses (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    contract_rate_id UUID,
    clause_type TEXT NOT NULL DEFAULT 'RATE'::text,
    description TEXT NOT NULL DEFAULT ''::text,
    value_expression TEXT NOT NULL DEFAULT ''::text,
    effective_from DATE,
    effective_to DATE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contract_rates (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    carrier_id TEXT NOT NULL,
    rate_type TEXT NOT NULL,
    rate_value NUMERIC(18,4) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD'::text,
    effective_on DATE NOT NULL,
    expires_on DATE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    lane_hash VARCHAR(71),
    base_rate NUMERIC(15,2),
    effective_from DATE,
    effective_to DATE,
    governing_jurisdiction TEXT,
    payload_hash VARCHAR(71),
    version INTEGER NOT NULL DEFAULT 1,
    supersedes_id UUID,
    superseded_at TIMESTAMP WITH TIME ZONE,
    source_document_id UUID
);

CREATE TABLE IF NOT EXISTS crypto_shred_requests (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    subject_ref TEXT NOT NULL,
    affected_key_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    affected_record_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    legal_hold_checked BOOLEAN NOT NULL DEFAULT false,
    legal_hold_blocked BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    requested_by TEXT NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    evidence_id UUID,
    correlation_id UUID,
    trace_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS decision_proposals (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    finding_id UUID NOT NULL,
    proposed_action TEXT NOT NULL,
    amount NUMERIC(18,4),
    currency TEXT DEFAULT 'USD'::text,
    proposer_sub TEXT NOT NULL,
    proposal_hash BYTEA NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    reasoning_trace_id UUID,
    governance_envelope JSONB,
    action_intent_id UUID
);

CREATE TABLE IF NOT EXISTS dedup_index (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    deduplication_key TEXT NOT NULL,
    outcome TEXT NOT NULL,
    source_record_id UUID NOT NULL,
    original_record_id UUID,
    external_source_ref TEXT,
    payload_hash TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_type_version TEXT NOT NULL DEFAULT 'v1'::text,
    decided_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dispatch_tickets (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    execution_envelope_id UUID,
    connector_id UUID,
    idempotency_key TEXT NOT NULL DEFAULT ''::text,
    status TEXT NOT NULL DEFAULT 'PREPARED'::text,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT ''::text,
    dispatched_at TIMESTAMP WITH TIME ZONE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID,
    document_type TEXT NOT NULL DEFAULT 'INVOICE'::text,
    file_name TEXT NOT NULL DEFAULT ''::text,
    mime_type TEXT NOT NULL DEFAULT ''::text,
    content_hash TEXT NOT NULL DEFAULT ''::text,
    storage_uri TEXT NOT NULL DEFAULT ''::text,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    retention_class TEXT NOT NULL DEFAULT 'STANDARD'::text,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS drift_signals (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    evaluation_run_id UUID,
    signal_type TEXT NOT NULL DEFAULT 'PRECISION_DROP'::text,
    severity TEXT NOT NULL DEFAULT 'LOW'::text,
    metric_name TEXT NOT NULL DEFAULT ''::text,
    baseline_value NUMERIC(10,6),
    current_value NUMERIC(10,6),
    delta NUMERIC(10,6),
    description TEXT NOT NULL DEFAULT ''::text,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    reviewed_by TEXT NOT NULL DEFAULT ''::text
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    run_type TEXT NOT NULL DEFAULT 'PRECISION'::text,
    model_version TEXT NOT NULL DEFAULT ''::text,
    cases_evaluated INTEGER NOT NULL DEFAULT 0,
    precision_score NUMERIC(5,4),
    recall_score NUMERIC(5,4),
    override_rate NUMERIC(5,4),
    recovery_amount NUMERIC(18,4),
    status TEXT NOT NULL DEFAULT 'RUNNING'::text,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    completed_at TIMESTAMP WITH TIME ZONE,
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS evidence_bundle_leaves (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    bundle_id UUID NOT NULL,
    bundle_version INTEGER NOT NULL,
    leaf_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    leaf_hash BYTEA NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_bundles (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    bundle_hash BYTEA NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    completeness_status TEXT NOT NULL DEFAULT 'INCOMPLETE'::text,
    bundle_version INTEGER NOT NULL DEFAULT 1,
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID,
    retention_until TIMESTAMP WITH TIME ZONE,
    archive_after TIMESTAMP WITH TIME ZONE,
    purge_after TIMESTAMP WITH TIME ZONE,
    crypto_shred_status TEXT NOT NULL DEFAULT 'ACTIVE'::text,
    archive_eligible BOOLEAN NOT NULL DEFAULT false,
    immutable_after_status TEXT,
    integrity_hash TEXT,
    signature_key_id TEXT,
    supersedes_id UUID,
    superseded_by_id UUID,
    payload_key_region TEXT,
    payload_encryption_alg TEXT NOT NULL DEFAULT 'AES-256-GCM'::text,
    payload_hash_alg TEXT NOT NULL DEFAULT 'sha-256'::text
);

CREATE TABLE IF NOT EXISTS evidence_items (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    bundle_id UUID NOT NULL,
    item_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    item_hash BYTEA NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    signature BYTEA,
    kid TEXT
);

CREATE TABLE IF NOT EXISTS execution_envelopes (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    token_id UUID NOT NULL,
    case_id UUID,
    gate_results JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'DISPATCHED'::text,
    env_hash BYTEA NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    dispatched_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    scope TEXT,
    amount NUMERIC(18,4),
    currency TEXT DEFAULT 'INR'::text,
    actor_sub TEXT,
    connector_ref TEXT,
    action_plan_id UUID,
    idempotency_key TEXT,
    request_payload_hash BYTEA,
    response_payload_hash BYTEA
);

CREATE TABLE IF NOT EXISTS expected_recoveries (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    authorization_decision_id UUID,
    counterparty_type TEXT NOT NULL DEFAULT 'carrier'::text,
    counterparty_id UUID,
    expected_amount NUMERIC(18,4) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'::text,
    expected_recovery_method TEXT NOT NULL DEFAULT 'carrier_credit_memo'::text,
    expected_invoice_id UUID,
    expected_external_invoice_ref TEXT,
    tolerance_policy_id TEXT NOT NULL DEFAULT 'recovery-match-tolerance-v1'::text,
    status TEXT NOT NULL DEFAULT 'EXPECTED'::text,
    superseded_by UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID
);

CREATE TABLE IF NOT EXISTS explanation_artifacts (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID,
    subject_type TEXT NOT NULL DEFAULT 'finding'::text,
    subject_id UUID,
    explanation TEXT NOT NULL DEFAULT ''::text,
    format TEXT NOT NULL DEFAULT 'markdown'::text,
    generated_by TEXT NOT NULL DEFAULT 'system'::text,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS external_acknowledgments (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    dispatch_ticket_id UUID,
    case_id UUID,
    ack_reference TEXT NOT NULL DEFAULT ''::text,
    ack_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS external_responses (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    execution_attempt_id UUID,
    source_record_id UUID,
    response_type TEXT NOT NULL,
    payload_hash BYTEA NOT NULL,
    status TEXT NOT NULL DEFAULT 'RECEIVED'::text,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facilities (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    facility_type TEXT NOT NULL DEFAULT 'WAREHOUSE'::text,
    address TEXT NOT NULL DEFAULT ''::text,
    country TEXT NOT NULL DEFAULT ''::text,
    latitude NUMERIC(10,6),
    longitude NUMERIC(10,6),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS findings (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    bundle_id UUID NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    ai_confidence DOUBLE PRECISION DEFAULT 0.0,
    risk_level TEXT DEFAULT 'MEDIUM'::text,
    ai_reasoning TEXT DEFAULT '[]'::text,
    rule_trace JSONB NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    finding_type TEXT,
    severity TEXT,
    source_record_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    canonical_record_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    rule_set_version TEXT,
    recommended_action TEXT,
    superseded_by UUID,
    finding_hash BYTEA,
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID
);

CREATE TABLE IF NOT EXISTS governance_decisions (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    policy_bundle_id UUID NOT NULL,
    outcome TEXT NOT NULL,
    decision_hash BYTEA NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    decided_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    approval_chain_hash BYTEA,
    policy_version TEXT NOT NULL DEFAULT 'v1.0.0'::text
);

CREATE TABLE IF NOT EXISTS governance_tokens (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    decision_id UUID NOT NULL,
    scope TEXT NOT NULL,
    tenant_binding BYTEA NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'::text,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    token_hash BYTEA NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    approval_chain_hash BYTEA,
    policy_version TEXT NOT NULL DEFAULT 'v1.0.0'::text,
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    key_value TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS'::text,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    connector_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING'::text,
    records_received INTEGER NOT NULL DEFAULT 0,
    records_accepted INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    completed_at TIMESTAMP WITH TIME ZONE,
    error_detail TEXT NOT NULL DEFAULT ''::text
);

CREATE TABLE IF NOT EXISTS invitation_tokens (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'analyst'::text,
    invited_by TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    accepted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    canonical_invoice_id UUID,
    line_number INTEGER NOT NULL DEFAULT 1,
    charge_code TEXT NOT NULL DEFAULT ''::text,
    description TEXT NOT NULL DEFAULT ''::text,
    quantity NUMERIC(12,4) NOT NULL DEFAULT 1,
    unit_price NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD'::text,
    is_disputed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    entry_type TEXT NOT NULL,
    amount NUMERIC(18,4) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'::text,
    debit_account TEXT NOT NULL,
    credit_account TEXT NOT NULL,
    source_recovery_match_id UUID,
    reversal_of_entry_id UUID,
    status TEXT NOT NULL DEFAULT 'POSTED'::text,
    posted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID,
    retention_until TIMESTAMP WITH TIME ZONE,
    archive_after TIMESTAMP WITH TIME ZONE,
    purge_after TIMESTAMP WITH TIME ZONE,
    crypto_shred_status TEXT NOT NULL DEFAULT 'ACTIVE'::text,
    archive_eligible BOOLEAN NOT NULL DEFAULT false,
    immutable_after_status TEXT,
    integrity_hash TEXT,
    signature_key_id TEXT,
    supersedes_id UUID,
    superseded_by_id UUID
);

CREATE TABLE IF NOT EXISTS legal_hold_records (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID,
    subject_type TEXT NOT NULL DEFAULT 'case'::text,
    subject_id UUID NOT NULL,
    reason TEXT NOT NULL DEFAULT ''::text,
    applied_by TEXT NOT NULL DEFAULT ''::text,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    lifted_at TIMESTAMP WITH TIME ZONE,
    lifted_by TEXT NOT NULL DEFAULT ''::text,
    hold_scope TEXT NOT NULL DEFAULT 'case'::text,
    reason_code TEXT NOT NULL DEFAULT 'operator_hold'::text,
    status TEXT NOT NULL DEFAULT 'ACTIVE'::text,
    approved_by TEXT,
    effective_from TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    evidence_id UUID,
    correlation_id UUID,
    trace_id UUID
);

CREATE TABLE IF NOT EXISTS lineage_records (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    parent_id UUID,
    event_type TEXT NOT NULL,
    payload_hash BYTEA NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    transform_id TEXT,
    transform_version TEXT,
    transform_input_hash TEXT,
    transform_output_hash TEXT,
    reference_data_snapshot JSONB,
    transformed_at TIMESTAMP WITH TIME ZONE,
    transformed_by TEXT,
    canonical_records JSONB,
    lineage_domain_tag TEXT DEFAULT 'zoiko/v1/lineage-record'::text
);

CREATE TABLE IF NOT EXISTS model_calls (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    purpose TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT ''::text,
    prompt_version TEXT NOT NULL DEFAULT 'v1'::text,
    input_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outbox (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    topic TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    shipped_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS outcomes (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    recon_id UUID NOT NULL,
    outcome_type TEXT NOT NULL,
    outcome_hash BYTEA NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS override_records (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID,
    override_type TEXT NOT NULL DEFAULT 'MANUAL'::text,
    original_decision TEXT NOT NULL DEFAULT ''::text,
    override_decision TEXT NOT NULL DEFAULT ''::text,
    reason TEXT NOT NULL DEFAULT ''::text,
    actor TEXT NOT NULL DEFAULT ''::text,
    approved_by TEXT NOT NULL DEFAULT ''::text,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS password_reset_otp (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    otp TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS password_reset_verify (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    verify_hash TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_bundles (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    version TEXT NOT NULL,
    rego_hash BYTEA NOT NULL,
    active BOOLEAN NOT NULL DEFAULT false,
    deployed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_packs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0'::text,
    policy_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'Draft'::text,
    promoted_by TEXT NOT NULL DEFAULT ''::text,
    promoted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS proofs_of_delivery (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    shipment_id UUID,
    signed_by TEXT NOT NULL DEFAULT ''::text,
    signed_at TIMESTAMP WITH TIME ZONE,
    document_url TEXT NOT NULL DEFAULT ''::text,
    content_hash TEXT NOT NULL DEFAULT ''::text,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS purge_jobs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    purge_scope TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    retention_policy_id UUID,
    legal_hold_checked BOOLEAN NOT NULL DEFAULT false,
    legal_hold_blocked BOOLEAN NOT NULL DEFAULT false,
    approval_id TEXT,
    approved_by TEXT,
    approved_at TIMESTAMP WITH TIME ZONE,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    completed_at TIMESTAMP WITH TIME ZONE,
    evidence_id UUID,
    correlation_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quarantine_items (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_record_id UUID,
    reason TEXT NOT NULL DEFAULT ''::text,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    quarantined_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    released_at TIMESTAMP WITH TIME ZONE,
    released_by TEXT NOT NULL DEFAULT ''::text
);

CREATE TABLE IF NOT EXISTS reasoning_traces (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    agent_id TEXT NOT NULL,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    tools_used text[] NOT NULL DEFAULT '{}'::text[],
    evidence_refs text[] NOT NULL DEFAULT '{}'::text[],
    confidence NUMERIC(5,4) NOT NULL,
    action_intent TEXT NOT NULL,
    policy_version TEXT NOT NULL DEFAULT 'v1.0.0'::text,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reconciliations (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    envelope_id UUID NOT NULL,
    delta_amount NUMERIC(18,4) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD'::text,
    recon_hash BYTEA NOT NULL,
    reconciled_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    reconciliation_type TEXT,
    expected_amount NUMERIC(18,4),
    observed_amount NUMERIC(18,4),
    external_response_id UUID
);

CREATE TABLE IF NOT EXISTS recovery_instruments (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    instrument_type TEXT NOT NULL,
    counterparty_type TEXT NOT NULL DEFAULT 'carrier'::text,
    counterparty_id UUID,
    source_record_id UUID,
    external_reference TEXT,
    related_external_invoice_ref TEXT,
    related_case_id UUID,
    instrument_amount NUMERIC(18,4) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'::text,
    instrument_date DATE,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'AVAILABLE'::text,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID
);

CREATE TABLE IF NOT EXISTS recovery_matches (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    expected_recovery_id UUID NOT NULL,
    recovery_instrument_id UUID NOT NULL,
    match_tier SMALLINT NOT NULL,
    match_method TEXT NOT NULL,
    match_confidence NUMERIC(5,4) NOT NULL DEFAULT 1.0,
    matched_amount NUMERIC(18,4) NOT NULL,
    expected_amount NUMERIC(18,4) NOT NULL,
    variance NUMERIC(18,4) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'INR'::text,
    allocation_status TEXT NOT NULL,
    matched_by TEXT NOT NULL,
    matched_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID
);

CREATE TABLE IF NOT EXISTS recovery_proofs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    claimed_amount NUMERIC(18,4) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'::text,
    expected_recovery_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    recovery_instrument_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    recovery_match_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ledger_entry_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_expected NUMERIC(18,4) NOT NULL,
    total_recovered NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_unrecovered NUMERIC(18,4) NOT NULL DEFAULT 0,
    recovery_status TEXT NOT NULL,
    ledger_status TEXT NOT NULL,
    acr_ready BOOLEAN NOT NULL DEFAULT false,
    superseded_by UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID,
    retention_until TIMESTAMP WITH TIME ZONE,
    archive_after TIMESTAMP WITH TIME ZONE,
    purge_after TIMESTAMP WITH TIME ZONE,
    crypto_shred_status TEXT NOT NULL DEFAULT 'ACTIVE'::text,
    archive_eligible BOOLEAN NOT NULL DEFAULT false,
    immutable_after_status TEXT,
    integrity_hash TEXT,
    signature_key_id TEXT,
    supersedes_id UUID,
    superseded_by_id UUID
);

CREATE TABLE IF NOT EXISTS release_gate_scoreboards (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    gate_number INTEGER NOT NULL,
    gate_name TEXT NOT NULL,
    score NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    weight NUMERIC(5,2) NOT NULL DEFAULT 1.0,
    verdict TEXT NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS restore_jobs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    restore_type TEXT NOT NULL,
    restored_scope TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    requested_by TEXT NOT NULL,
    approved_by TEXT,
    approved_at TIMESTAMP WITH TIME ZONE,
    evidence_id UUID,
    correlation_id UUID,
    trace_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS restore_verification_records (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    restore_job_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    source_records_verified BOOLEAN NOT NULL DEFAULT false,
    evidence_chain_verified BOOLEAN NOT NULL DEFAULT false,
    acr_verified BOOLEAN NOT NULL DEFAULT false,
    ledger_continuity_verified BOOLEAN NOT NULL DEFAULT false,
    tenant_isolation_verified BOOLEAN NOT NULL DEFAULT false,
    residency_verified BOOLEAN NOT NULL DEFAULT false,
    permissions_verified BOOLEAN NOT NULL DEFAULT false,
    legal_hold_verified BOOLEAN NOT NULL DEFAULT false,
    indexes_rebuilt BOOLEAN NOT NULL DEFAULT false,
    projection_consistency_verified BOOLEAN NOT NULL DEFAULT false,
    verification_status TEXT NOT NULL DEFAULT 'PENDING'::text,
    verified_at TIMESTAMP WITH TIME ZONE,
    evidence_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS retention_markers (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id UUID NOT NULL,
    retention_class TEXT NOT NULL DEFAULT 'STANDARD'::text,
    retain_until TIMESTAMP WITH TIME ZONE,
    reason TEXT NOT NULL DEFAULT ''::text,
    applied_by TEXT NOT NULL DEFAULT 'system'::text,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS retention_policies (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    policy_name TEXT NOT NULL,
    data_class TEXT NOT NULL,
    retention_class TEXT NOT NULL,
    retention_days INTEGER NOT NULL,
    archive_after_days INTEGER,
    purge_after_days INTEGER,
    status TEXT NOT NULL DEFAULT 'ACTIVE'::text,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rule_traces (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID,
    validator_name TEXT NOT NULL DEFAULT ''::text,
    rule_id TEXT NOT NULL DEFAULT ''::text,
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result TEXT NOT NULL DEFAULT 'PASS'::text,
    executed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shipment_legs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    shipment_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    leg_sequence INTEGER NOT NULL DEFAULT 1,
    carrier_id UUID,
    origin TEXT NOT NULL DEFAULT ''::text,
    destination TEXT NOT NULL DEFAULT ''::text,
    transport_mode TEXT NOT NULL DEFAULT 'TRUCKLOAD'::text,
    departure_at TIMESTAMP WITH TIME ZONE,
    arrival_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shipments (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    shipment_number TEXT NOT NULL DEFAULT ''::text,
    origin_facility_id UUID,
    dest_facility_id UUID,
    carrier_id UUID,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    transport_mode TEXT NOT NULL DEFAULT 'TRUCKLOAD'::text,
    scheduled_pickup TIMESTAMP WITH TIME ZONE,
    actual_pickup TIMESTAMP WITH TIME ZONE,
    scheduled_delivery TIMESTAMP WITH TIME ZONE,
    actual_delivery TIMESTAMP WITH TIME ZONE,
    total_weight_kg NUMERIC(12,4) NOT NULL DEFAULT 0,
    total_volume_m3 NUMERIC(12,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signup_verification (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    org_name TEXT NOT NULL,
    admin_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_record_states (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_record_id UUID NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT,
    detail JSONB,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_records (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_type TEXT NOT NULL,
    canonical_hash BYTEA NOT NULL,
    ciphertext BYTEA NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    schema_version TEXT NOT NULL DEFAULT 'source-record.v1'::text,
    domain_tag TEXT NOT NULL DEFAULT 'zoiko/v1/source-record'::text,
    brand_id UUID,
    jurisdiction_code TEXT,
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    data_classification TEXT NOT NULL DEFAULT 'confidential'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-A'::text,
    channel TEXT NOT NULL DEFAULT 'rest_api_push'::text,
    channel_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_type_version TEXT NOT NULL DEFAULT 'v1'::text,
    external_source_ref TEXT,
    received_at TIMESTAMP WITH TIME ZONE,
    received_by_service TEXT,
    received_by_user UUID,
    raw_payload_iv BYTEA,
    raw_payload_aad TEXT,
    raw_payload_dek_id TEXT,
    raw_payload_size_bytes INTEGER,
    raw_payload_content_type TEXT NOT NULL DEFAULT 'application/json'::text,
    raw_payload_encoding TEXT NOT NULL DEFAULT 'utf-8'::text,
    raw_payload_hash_alg TEXT NOT NULL DEFAULT 'sha-256'::text,
    deduplication_key TEXT,
    deduplication_outcome TEXT NOT NULL DEFAULT 'FIRST_SEEN'::text,
    deduplication_canonical_record_id UUID,
    validation_status TEXT NOT NULL DEFAULT 'PENDING'::text,
    validation_result_id UUID,
    lineage_id UUID,
    correlation_id UUID,
    causation_id UUID,
    record_status TEXT NOT NULL DEFAULT 'RECEIVED'::text,
    signature_block JSONB,
    retention_until TIMESTAMP WITH TIME ZONE,
    archive_after TIMESTAMP WITH TIME ZONE,
    purge_after TIMESTAMP WITH TIME ZONE,
    crypto_shred_status TEXT NOT NULL DEFAULT 'ACTIVE'::text,
    archive_eligible BOOLEAN NOT NULL DEFAULT false,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    trace_id UUID,
    updated_by TEXT,
    immutable_after_status TEXT,
    integrity_hash TEXT,
    signature_key_id TEXT,
    supersedes_id UUID,
    superseded_by_id UUID,
    payload_key_region TEXT,
    payload_encryption_alg TEXT NOT NULL DEFAULT 'AES-256-GCM'::text
);

CREATE TABLE IF NOT EXISTS sso_domains (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    domain TEXT NOT NULL,
    idp_type TEXT NOT NULL DEFAULT 'oidc'::text,
    idp_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS step_up_assertions (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    action TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS submit_jobs (
    job_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'::text,
    case_data JSONB,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    task_type TEXT NOT NULL DEFAULT 'REVIEW'::text,
    assigned_to TEXT NOT NULL DEFAULT ''::text,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    due_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    notes TEXT NOT NULL DEFAULT ''::text,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenant_keys (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    key_purpose TEXT NOT NULL,
    kms_resource TEXT NOT NULL,
    key_ciphertext BYTEA NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    rotated_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS tenant_notification_settings (
    tenant_id UUID NOT NULL,
    case_opened_email BOOLEAN NOT NULL DEFAULT true,
    overcharge_detected_email BOOLEAN NOT NULL DEFAULT true,
    approval_needed_email BOOLEAN NOT NULL DEFAULT true,
    recovery_executed_email BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenants (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'::text,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    residency_assigned_at TIMESTAMP WITH TIME ZONE,
    residency_assigned_by TEXT
);

CREATE TABLE IF NOT EXISTS threshold_profiles (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD'::text,
    auto_approve_below NUMERIC(18,4) NOT NULL DEFAULT 0,
    require_approval_above NUMERIC(18,4) NOT NULL DEFAULT 1000,
    escalate_above NUMERIC(18,4) NOT NULL DEFAULT 10000,
    approval_group_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transparency_log_commits (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    root_hash BYTEA NOT NULL,
    leaf_count INTEGER NOT NULL,
    witness_signature BYTEA NOT NULL,
    witness_kid TEXT NOT NULL,
    committed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transparency_log_entries (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    acr_id UUID NOT NULL,
    log_index BIGINT NOT NULL,
    leaf_hash BYTEA NOT NULL,
    commit_id UUID,
    appended_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT ''::text,
    role TEXT NOT NULL DEFAULT 'analyst'::text,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    title TEXT NOT NULL DEFAULT ''::text
);

CREATE TABLE IF NOT EXISTS validation_results (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_record_id UUID NOT NULL,
    status TEXT NOT NULL,
    rule_violations JSONB NOT NULL DEFAULT '[]'::jsonb,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    validated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    rule_set_id TEXT,
    rule_set_version TEXT,
    validation_service_version TEXT NOT NULL DEFAULT '1.0.0'::text,
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID
);

CREATE TABLE IF NOT EXISTS validation_rule_sets (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    rule_set_id TEXT NOT NULL,
    version TEXT NOT NULL,
    source_type TEXT NOT NULL,
    rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'DRAFT'::text,
    activated_at TIMESTAMP WITH TIME ZONE,
    superseded_at TIMESTAMP WITH TIME ZONE,
    authored_by UUID,
    signature TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS variance_records (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    proposal_id UUID,
    variance_type TEXT NOT NULL,
    expected_value NUMERIC(15,4),
    actual_value NUMERIC(15,4),
    delta NUMERIC(15,4),
    status TEXT NOT NULL DEFAULT 'OPEN'::text,
    resolved_by TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS webhook_signing_configs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_type TEXT NOT NULL,
    signing_secret TEXT NOT NULL,
    ip_allowlist JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    rotated_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS witness_packs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_record_id UUID NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id UUID NOT NULL,
    snapshot_payload JSONB NOT NULL,
    snapshot_hash BYTEA NOT NULL,
    signature BYTEA NOT NULL,
    kid TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workspace_access_requests (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    full_name TEXT NOT NULL,
    work_email TEXT NOT NULL,
    company_name TEXT NOT NULL,
    company_website TEXT,
    country TEXT,
    role TEXT,
    use_case TEXT,
    team_size TEXT,
    heard_from TEXT,
    consent BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'PENDING'::text,
    crm_ref TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS write_offs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL,
    expected_recovery_id UUID NOT NULL,
    amount NUMERIC(18,4) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR'::text,
    reason_code TEXT NOT NULL,
    policy_version_id TEXT NOT NULL DEFAULT 'writeoff-policy-v1'::text,
    authorized_by TEXT,
    authorized_at TIMESTAMP WITH TIME ZONE,
    ledger_entry_id UUID,
    status TEXT NOT NULL DEFAULT 'REQUESTED'::text,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    data_residency_region TEXT NOT NULL DEFAULT 'ap-south-1'::text,
    retention_class TEXT NOT NULL DEFAULT 'tier-B-operational'::text,
    legal_hold_status TEXT NOT NULL DEFAULT 'NONE'::text,
    updated_by TEXT,
    correlation_id UUID,
    trace_id UUID
);


-- ===== CONSTRAINTS =====

ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_pkey PRIMARY KEY (id);
ALTER TABLE action_intents ADD CONSTRAINT action_intents_pkey PRIMARY KEY (id);
ALTER TABLE action_plans ADD CONSTRAINT action_plans_pkey PRIMARY KEY (id);
ALTER TABLE agent_tool_permissions ADD CONSTRAINT agent_tool_permissions_pkey PRIMARY KEY (id);
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_pkey PRIMARY KEY (id);
ALTER TABLE api_keys ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_pkey PRIMARY KEY (id);
ALTER TABLE approval_group_members ADD CONSTRAINT approval_group_members_pkey PRIMARY KEY (id);
ALTER TABLE approval_groups ADD CONSTRAINT approval_groups_pkey PRIMARY KEY (id);
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_pkey PRIMARY KEY (id);
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_pkey PRIMARY KEY (id);
ALTER TABLE approval_thresholds ADD CONSTRAINT approval_thresholds_pkey PRIMARY KEY (id);
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_pkey PRIMARY KEY (id);
ALTER TABLE assertion_results ADD CONSTRAINT assertion_results_pkey PRIMARY KEY (id);
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_pkey PRIMARY KEY (id);
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_pkey PRIMARY KEY (id);
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_pkey PRIMARY KEY (id);
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_pkey PRIMARY KEY (id);
ALTER TABLE batch_records ADD CONSTRAINT batch_records_pkey PRIMARY KEY (id);
ALTER TABLE business_units ADD CONSTRAINT business_units_pkey PRIMARY KEY (id);
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_pkey PRIMARY KEY (id);
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_pkey PRIMARY KEY (id);
ALTER TABLE carriers ADD CONSTRAINT carriers_pkey PRIMARY KEY (id);
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_pkey PRIMARY KEY (id);
ALTER TABLE case_events ADD CONSTRAINT case_events_pkey PRIMARY KEY (id);
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_pkey PRIMARY KEY (id);
ALTER TABLE cases ADD CONSTRAINT cases_pkey PRIMARY KEY (id);
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_pkey PRIMARY KEY (id);
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_pkey PRIMARY KEY (id);
ALTER TABLE connector_responses ADD CONSTRAINT connector_responses_pkey PRIMARY KEY (id);
ALTER TABLE connectors ADD CONSTRAINT connectors_pkey PRIMARY KEY (id);
ALTER TABLE contract_clauses ADD CONSTRAINT contract_clauses_pkey PRIMARY KEY (id);
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_pkey PRIMARY KEY (id);
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_pkey PRIMARY KEY (id);
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_pkey PRIMARY KEY (id);
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_pkey PRIMARY KEY (id);
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_pkey PRIMARY KEY (id);
ALTER TABLE documents ADD CONSTRAINT documents_pkey PRIMARY KEY (id);
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_pkey PRIMARY KEY (id);
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_pkey PRIMARY KEY (id);
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_pkey PRIMARY KEY (id);
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_pkey PRIMARY KEY (id);
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_pkey PRIMARY KEY (id);
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_pkey PRIMARY KEY (id);
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_pkey PRIMARY KEY (id);
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_pkey PRIMARY KEY (id);
ALTER TABLE external_acknowledgments ADD CONSTRAINT external_acknowledgments_pkey PRIMARY KEY (id);
ALTER TABLE external_responses ADD CONSTRAINT external_responses_pkey PRIMARY KEY (id);
ALTER TABLE facilities ADD CONSTRAINT facilities_pkey PRIMARY KEY (id);
ALTER TABLE findings ADD CONSTRAINT findings_pkey PRIMARY KEY (id);
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_pkey PRIMARY KEY (id);
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_pkey PRIMARY KEY (id);
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (id);
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_pkey PRIMARY KEY (id);
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_pkey PRIMARY KEY (id);
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_pkey PRIMARY KEY (id);
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_pkey PRIMARY KEY (id);
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_pkey PRIMARY KEY (id);
ALTER TABLE lineage_records ADD CONSTRAINT lineage_records_pkey PRIMARY KEY (id);
ALTER TABLE model_calls ADD CONSTRAINT model_calls_pkey PRIMARY KEY (id);
ALTER TABLE outbox ADD CONSTRAINT outbox_pkey PRIMARY KEY (id);
ALTER TABLE outcomes ADD CONSTRAINT outcomes_pkey PRIMARY KEY (id);
ALTER TABLE override_records ADD CONSTRAINT override_records_pkey PRIMARY KEY (id);
ALTER TABLE password_reset_otp ADD CONSTRAINT password_reset_otp_pkey PRIMARY KEY (id);
ALTER TABLE password_reset_tokens ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);
ALTER TABLE password_reset_verify ADD CONSTRAINT password_reset_verify_pkey PRIMARY KEY (id);
ALTER TABLE policy_bundles ADD CONSTRAINT policy_bundles_pkey PRIMARY KEY (id);
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_pkey PRIMARY KEY (id);
ALTER TABLE proofs_of_delivery ADD CONSTRAINT proofs_of_delivery_pkey PRIMARY KEY (id);
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_pkey PRIMARY KEY (id);
ALTER TABLE quarantine_items ADD CONSTRAINT quarantine_items_pkey PRIMARY KEY (id);
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_pkey PRIMARY KEY (id);
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_pkey PRIMARY KEY (id);
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_pkey PRIMARY KEY (id);
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_pkey PRIMARY KEY (id);
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_pkey PRIMARY KEY (id);
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_pkey PRIMARY KEY (id);
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_pkey PRIMARY KEY (id);
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_pkey PRIMARY KEY (id);
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_pkey PRIMARY KEY (id);
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_pkey PRIMARY KEY (id);
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_pkey PRIMARY KEY (id);
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_pkey PRIMARY KEY (id);
ALTER TABLE shipments ADD CONSTRAINT shipments_pkey PRIMARY KEY (id);
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_pkey PRIMARY KEY (id);
ALTER TABLE source_record_states ADD CONSTRAINT source_record_states_pkey PRIMARY KEY (id);
ALTER TABLE source_records ADD CONSTRAINT source_records_pkey PRIMARY KEY (id);
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_pkey PRIMARY KEY (id);
ALTER TABLE step_up_assertions ADD CONSTRAINT step_up_assertions_pkey PRIMARY KEY (id);
ALTER TABLE submit_jobs ADD CONSTRAINT submit_jobs_pkey PRIMARY KEY (job_id);
ALTER TABLE tasks ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);
ALTER TABLE tenant_keys ADD CONSTRAINT tenant_keys_pkey PRIMARY KEY (id);
ALTER TABLE tenant_notification_settings ADD CONSTRAINT tenant_notification_settings_pkey PRIMARY KEY (tenant_id);
ALTER TABLE tenants ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_pkey PRIMARY KEY (id);
ALTER TABLE transparency_log_commits ADD CONSTRAINT transparency_log_commits_pkey PRIMARY KEY (id);
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_pkey PRIMARY KEY (id);
ALTER TABLE users ADD CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE validation_results ADD CONSTRAINT validation_results_pkey PRIMARY KEY (id);
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_pkey PRIMARY KEY (id);
ALTER TABLE variance_records ADD CONSTRAINT variance_records_pkey PRIMARY KEY (id);
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_pkey PRIMARY KEY (id);
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_pkey PRIMARY KEY (id);
ALTER TABLE workspace_access_requests ADD CONSTRAINT workspace_access_requests_pkey PRIMARY KEY (id);
ALTER TABLE write_offs ADD CONSTRAINT write_offs_pkey PRIMARY KEY (id);
ALTER TABLE agent_tool_permissions ADD CONSTRAINT agent_tool_permissions_tool_name_key UNIQUE (tool_name);
ALTER TABLE api_keys ADD CONSTRAINT api_keys_key_hash_key UNIQUE (key_hash);
ALTER TABLE approval_group_members ADD CONSTRAINT approval_group_members_approval_group_id_user_id_key UNIQUE (approval_group_id, user_id);
ALTER TABLE approval_groups ADD CONSTRAINT approval_groups_tenant_id_name_key UNIQUE (tenant_id, name);
ALTER TABLE approval_thresholds ADD CONSTRAINT approval_thresholds_tenant_id_currency_key UNIQUE (tenant_id, currency);
ALTER TABLE business_units ADD CONSTRAINT business_units_tenant_id_name_key UNIQUE (tenant_id, name);
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_tenant_id_invoice_number_key UNIQUE (tenant_id, invoice_number);
ALTER TABLE canonical_shipments ADD CONSTRAINT uq_canonical_shipments_invoice_id UNIQUE (invoice_id);
ALTER TABLE carriers ADD CONSTRAINT carriers_tenant_id_name_key UNIQUE (tenant_id, name);
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_tenant_id_grouping_key_key UNIQUE (tenant_id, grouping_key);
ALTER TABLE connectors ADD CONSTRAINT connectors_tenant_id_name_key UNIQUE (tenant_id, name);
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_tenant_id_deduplication_key_key UNIQUE (tenant_id, deduplication_key);
ALTER TABLE facilities ADD CONSTRAINT facilities_tenant_id_name_key UNIQUE (tenant_id, name);
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_tenant_id_key_value_key UNIQUE (tenant_id, key_value);
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_token_hash_key UNIQUE (token_hash);
ALTER TABLE password_reset_tokens ADD CONSTRAINT password_reset_tokens_token_hash_key UNIQUE (token_hash);
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_tenant_id_name_version_key UNIQUE (tenant_id, name, version);
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_restore_job_id_key UNIQUE (restore_job_id);
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_tenant_id_policy_name_key UNIQUE (tenant_id, policy_name);
ALTER TABLE source_records ADD CONSTRAINT source_records_tenant_id_idempotency_key_key UNIQUE (tenant_id, idempotency_key);
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_domain_key UNIQUE (domain);
ALTER TABLE tenants ADD CONSTRAINT tenants_slug_key UNIQUE (slug);
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_tenant_id_name_key UNIQUE (tenant_id, name);
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_tenant_id_acr_id_key UNIQUE (tenant_id, acr_id);
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_tenant_id_log_index_key UNIQUE (tenant_id, log_index);
ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email);
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_rule_set_id_version_key UNIQUE (rule_set_id, version);
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_crypto_shred_status_check CHECK ((crypto_shred_status = ANY (ARRAY['ACTIVE'::text, 'SHREDDED'::text, 'EXEMPT'::text])));
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_resolution_check CHECK ((resolution = ANY (ARRAY['USE_LATEST'::text, 'USE_ORIGINAL'::text, 'REJECT_BOTH'::text, 'MANUAL'::text])));
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_decision_check CHECK ((decision = ANY (ARRAY['APPROVE'::text, 'REJECT'::text, 'ESCALATE'::text])));
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_approval_level_check CHECK ((approval_level = ANY (ARRAY['AUTO'::text, 'SINGLE'::text, 'DUAL'::text])));
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'APPROVED'::text, 'REJECTED'::text, 'ESCALATED'::text, 'TIMEOUT'::text])));
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_approval_level_check CHECK ((approval_level = ANY (ARRAY['AUTO'::text, 'SINGLE'::text, 'DUAL'::text])));
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'APPROVED'::text, 'REJECTED'::text])));
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'IN_PROGRESS'::text, 'COMPLETED'::text, 'FAILED'::text])));
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_decision_check CHECK ((decision = ANY (ARRAY['ALLOW'::text, 'DENY'::text, 'ESCALATE'::text])));
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_processing_status_check CHECK ((processing_status = ANY (ARRAY['RECEIVED'::text, 'STREAMING'::text, 'PROCESSING'::text, 'COMPLETED'::text, 'FAILED_PARTIAL'::text, 'FAILED'::text])));
ALTER TABLE batch_records ADD CONSTRAINT batch_records_outcome_check CHECK ((outcome = ANY (ARRAY['PENDING'::text, 'FIRST_SEEN'::text, 'DUPLICATE_OF'::text, 'AMBIGUOUS'::text, 'REJECTED'::text, 'QUARANTINED'::text, 'PROCESSED'::text])));
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'PROMOTED'::text, 'REJECTED'::text])));
ALTER TABLE cases ADD CONSTRAINT cases_closure_reason_check CHECK (((closure_reason IS NULL) OR (closure_reason = ANY (ARRAY['RECOVERED_FULL'::text, 'RECOVERED_PARTIAL'::text, 'NO_ACTION_REQUIRED'::text, 'FINDING_INVALID'::text, 'DUPLICATE_CASE'::text, 'UNRECOVERABLE'::text, 'WITHDRAWN'::text, 'EXTERNAL_REJECTED'::text, 'POLICY_CLOSED'::text]))));
ALTER TABLE cases ADD CONSTRAINT cases_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE cases ADD CONSTRAINT cases_state_check CHECK ((state = ANY (ARRAY['NEW'::text, 'EVIDENCE_PENDING'::text, 'FINDING_GENERATED'::text, 'APPROVAL_PENDING'::text, 'EXECUTION_READY'::text, 'DISPATCHED'::text, 'OUTCOME_RECORDED'::text, 'CLOSED'::text, 'ABORTED'::text, 'CANDIDATE'::text, 'UNDER_REVIEW'::text, 'ACTION_PLAN_READY'::text, 'READY_FOR_AUTHORIZATION'::text, 'AUTHORIZED'::text, 'EXECUTING'::text, 'AWAITING_EXTERNAL_RESPONSE'::text, 'RECONCILING'::text, 'CLOSED_RECOVERED'::text, 'CLOSED_NO_ACTION'::text, 'CLOSED_REJECTED'::text, 'CLOSED_WITHDRAWN'::text, 'CLOSED_UNRECOVERABLE'::text, 'CLOSED_DUPLICATE'::text, 'ESCALATED'::text, 'QUARANTINED'::text])));
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_run_type_check CHECK ((run_type = ANY (ARRAY['TCP'::text, 'SMOKE'::text, 'REGRESSION'::text, 'RELEASE_GATE'::text])));
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_status_check CHECK ((status = ANY (ARRAY['RUNNING'::text, 'PASSED'::text, 'FAILED'::text, 'ABORTED'::text])));
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'IN_PROGRESS'::text, 'COMPLETED'::text, 'BLOCKED'::text, 'FAILED'::text])));
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_outcome_check CHECK ((outcome = ANY (ARRAY['FIRST_SEEN'::text, 'DUPLICATE_OF'::text, 'AMBIGUOUS'::text])));
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_leaf_type_check CHECK ((leaf_type = ANY (ARRAY['source_record'::text, 'canonical_record'::text, 'validation_result'::text, 'finding'::text, 'action_plan'::text, 'authorization'::text, 'execution'::text, 'external_response'::text, 'reconciliation'::text, 'closure'::text])));
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_completeness_status_check CHECK ((completeness_status = ANY (ARRAY['INCOMPLETE'::text, 'COMPLETE'::text])));
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_crypto_shred_status_check CHECK ((crypto_shred_status = ANY (ARRAY['ACTIVE'::text, 'SHREDDED'::text, 'EXEMPT'::text])));
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_status_check CHECK ((status = ANY (ARRAY['DISPATCHED'::text, 'CONFIRMED'::text, 'FAILED'::text])));
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_expected_recovery_method_check CHECK ((expected_recovery_method = ANY (ARRAY['carrier_credit_memo'::text, 'settlement_offset'::text, 'refund_payment'::text, 'invoice_adjustment'::text, 'future_bill_credit'::text, 'partner_statement_credit'::text, 'internal_adjustment'::text, 'write_off'::text, 'chargeback_reversal'::text, 'manual_recovery_evidence'::text])));
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_status_check CHECK ((status = ANY (ARRAY['EXPECTED'::text, 'AWAITING_INSTRUMENT'::text, 'INSTRUMENT_RECEIVED'::text, 'MATCHING'::text, 'MATCHED_FULL'::text, 'MATCHED_PARTIAL'::text, 'OVER_RECOVERED'::text, 'MISMATCHED'::text, 'UNRECOVERABLE_PENDING_APPROVAL'::text, 'WRITTEN_OFF'::text, 'LEDGER_PENDING'::text, 'LEDGER_CLOSED'::text, 'ACR_READY'::text])));
ALTER TABLE external_responses ADD CONSTRAINT external_responses_status_check CHECK ((status = ANY (ARRAY['RECEIVED'::text, 'LINKED'::text, 'REQUIRES_REVIEW'::text])));
ALTER TABLE findings ADD CONSTRAINT findings_confidence_check CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric)));
ALTER TABLE findings ADD CONSTRAINT findings_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_outcome_check CHECK ((outcome = ANY (ARRAY['EXECUTION_READY'::text, 'ABORTED'::text])));
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_status_check CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'CONSUMED'::text, 'EXPIRED'::text, 'REVOKED'::text])));
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_status_check CHECK ((status = ANY (ARRAY['IN_PROGRESS'::text, 'COMPLETE'::text])));
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_role_check CHECK ((role = ANY (ARRAY['analyst'::text, 'manager'::text, 'admin'::text])));
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_crypto_shred_status_check CHECK ((crypto_shred_status = ANY (ARRAY['ACTIVE'::text, 'SHREDDED'::text, 'EXEMPT'::text])));
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_entry_type_check CHECK ((entry_type = ANY (ARRAY['RECOVERY_RECEIVABLE_CREATED'::text, 'RECOVERY_CREDIT_APPLIED'::text, 'RECOVERY_REFUND_RECEIVED'::text, 'RECOVERY_PARTIAL_APPLIED'::text, 'RECOVERY_WRITE_OFF_POSTED'::text, 'OVER_RECOVERY_PENDING_REVIEW'::text, 'LEDGER_EXEMPT_APPROVED'::text, 'REVERSAL'::text])));
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_status_check CHECK ((status = ANY (ARRAY['POSTED'::text, 'EXPORT_PENDING'::text, 'EXPORTED'::text, 'EXPORT_CONFIRMED'::text, 'EXEMPT'::text])));
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_status_check CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'RELEASED'::text])));
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'APPROVED'::text, 'IN_PROGRESS'::text, 'COMPLETED'::text, 'BLOCKED'::text, 'FAILED'::text])));
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_confidence_check CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric)));
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_reconciliation_type_check CHECK (((reconciliation_type IS NULL) OR (reconciliation_type = ANY (ARRAY['MATCHED'::text, 'PARTIAL_MATCH'::text, 'MISMATCH'::text]))));
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_instrument_type_check CHECK ((instrument_type = ANY (ARRAY['carrier_credit_memo'::text, 'settlement_offset'::text, 'refund_payment'::text, 'invoice_adjustment'::text, 'future_bill_credit'::text, 'partner_statement_credit'::text, 'internal_adjustment'::text, 'write_off'::text, 'chargeback_reversal'::text, 'manual_recovery_evidence'::text])));
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_status_check CHECK ((status = ANY (ARRAY['AVAILABLE'::text, 'CONSUMED'::text, 'REVERSED'::text])));
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_allocation_status_check CHECK ((allocation_status = ANY (ARRAY['FULL'::text, 'PARTIAL'::text, 'OVER'::text, 'MISMATCH'::text, 'REVIEW_REQUIRED'::text, 'REVERSED'::text])));
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_crypto_shred_status_check CHECK ((crypto_shred_status = ANY (ARRAY['ACTIVE'::text, 'SHREDDED'::text, 'EXEMPT'::text])));
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_ledger_status_check CHECK ((ledger_status = ANY (ARRAY['LEDGER_PENDING'::text, 'LEDGER_CLOSED'::text, 'LEDGER_EXEMPT'::text])));
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_recovery_status_check CHECK ((recovery_status = ANY (ARRAY['RECOVERED_FULL'::text, 'RECOVERED_PARTIAL'::text, 'UNRECOVERABLE_APPROVED'::text, 'REJECTED_BY_COUNTERPARTY'::text, 'OVER_RECOVERED'::text, 'MISMATCHED'::text, 'AWAITING_INSTRUMENT'::text, 'LEDGER_PENDING'::text])));
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_score_check CHECK (((score >= (0)::numeric) AND (score <= (100)::numeric)));
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_verdict_check CHECK ((verdict = ANY (ARRAY['PASS'::text, 'FAIL'::text, 'SKIP'::text])));
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_restore_type_check CHECK ((restore_type = ANY (ARRAY['tenant_restore'::text, 'case_restore'::text, 'source_record_restore'::text, 'evidence_restore'::text, 'acr_restore'::text, 'ledger_recovery_restore'::text, 'regional_dr_restore'::text, 'archive_restore'::text, 'projection_rebuild'::text])));
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'IN_PROGRESS'::text, 'DATA_RESTORED'::text, 'VERIFICATION_PENDING'::text, 'VERIFICATION_PASSED'::text, 'VERIFICATION_FAILED'::text, 'APPROVED_FOR_USE'::text, 'FAILED'::text])));
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_verification_status_check CHECK ((verification_status = ANY (ARRAY['PENDING'::text, 'PASSED'::text, 'FAILED'::text])));
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_status_check CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'SUPERSEDED'::text, 'RETIRED'::text])));
ALTER TABLE source_records ADD CONSTRAINT source_records_channel_check CHECK ((channel = ANY (ARRAY['rest_api_push'::text, 'rest_api_pull'::text, 'webhook'::text, 'edi'::text, 'file_upload'::text, 'ui_entry'::text])));
ALTER TABLE source_records ADD CONSTRAINT source_records_crypto_shred_status_check CHECK ((crypto_shred_status = ANY (ARRAY['ACTIVE'::text, 'SHREDDED'::text, 'EXEMPT'::text])));
ALTER TABLE source_records ADD CONSTRAINT source_records_deduplication_outcome_check CHECK ((deduplication_outcome = ANY (ARRAY['FIRST_SEEN'::text, 'DUPLICATE_OF'::text, 'AMBIGUOUS'::text])));
ALTER TABLE source_records ADD CONSTRAINT source_records_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE source_records ADD CONSTRAINT source_records_record_status_check CHECK ((record_status = ANY (ARRAY['RECEIVED'::text, 'PERSISTED'::text, 'DEDUPED'::text, 'ENCRYPTED'::text, 'SIGNED'::text, 'PENDING_VALIDATION'::text, 'VALIDATING'::text, 'VALIDATED'::text, 'CANONICALIZING'::text, 'PROCESSED'::text, 'QUARANTINED'::text, 'REJECTED'::text])));
ALTER TABLE source_records ADD CONSTRAINT source_records_validation_status_check CHECK ((validation_status = ANY (ARRAY['PENDING'::text, 'VALIDATING'::text, 'VALIDATED'::text, 'QUARANTINED'::text, 'REJECTED'::text])));
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_idp_type_check CHECK ((idp_type = ANY (ARRAY['entra'::text, 'okta'::text, 'ping'::text, 'google'::text, 'saml'::text, 'oidc'::text])));
ALTER TABLE tenants ADD CONSTRAINT tenants_status_check CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'SUSPENDED'::text, 'OFFBOARDED'::text])));
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK ((role = ANY (ARRAY['analyst'::text, 'manager'::text, 'admin'::text])));
ALTER TABLE validation_results ADD CONSTRAINT validation_results_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE validation_results ADD CONSTRAINT validation_results_status_check CHECK ((status = ANY (ARRAY['PASS'::text, 'FAIL'::text, 'WARN'::text])));
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_status_check CHECK ((status = ANY (ARRAY['DRAFT'::text, 'ACTIVE'::text, 'SUPERSEDED'::text, 'RETIRED'::text])));
ALTER TABLE variance_records ADD CONSTRAINT variance_records_status_check CHECK ((status = ANY (ARRAY['OPEN'::text, 'RESOLVED'::text, 'WAIVED'::text])));
ALTER TABLE variance_records ADD CONSTRAINT variance_records_variance_type_check CHECK ((variance_type = ANY (ARRAY['AMOUNT_MISMATCH'::text, 'CARRIER_MISMATCH'::text, 'CURRENCY_MISMATCH'::text, 'OVERCHARGE_DELTA'::text, 'OTHER'::text])));
ALTER TABLE workspace_access_requests ADD CONSTRAINT workspace_access_requests_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'CONTACTED'::text, 'QUALIFIED'::text, 'REJECTED'::text])));
ALTER TABLE write_offs ADD CONSTRAINT write_offs_legal_hold_status_check CHECK ((legal_hold_status = ANY (ARRAY['NONE'::text, 'HELD'::text])));
ALTER TABLE write_offs ADD CONSTRAINT write_offs_reason_code_check CHECK ((reason_code = ANY (ARRAY['counterparty_rejection'::text, 'below_pursuit_threshold'::text, 'window_expired'::text, 'insufficient_documentation'::text, 'uneconomic_pursuit'::text, 'commercial_decision'::text, 'residual_immateriality'::text])));
ALTER TABLE write_offs ADD CONSTRAINT write_offs_status_check CHECK ((status = ANY (ARRAY['REQUESTED'::text, 'AUTHORIZED'::text, 'POSTED'::text, 'REJECTED'::text])));
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_superseded_by_acr_id_fkey FOREIGN KEY (superseded_by_acr_id) REFERENCES action_certification_records(id);
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_supersedes_acr_id_fkey FOREIGN KEY (supersedes_acr_id) REFERENCES action_certification_records(id);
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE action_intents ADD CONSTRAINT action_intents_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE action_intents ADD CONSTRAINT action_intents_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE action_plans ADD CONSTRAINT action_plans_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE action_plans ADD CONSTRAINT action_plans_evidence_bundle_id_fkey FOREIGN KEY (evidence_bundle_id) REFERENCES evidence_bundles(id);
ALTER TABLE action_plans ADD CONSTRAINT action_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_original_record_id_fkey FOREIGN KEY (original_record_id) REFERENCES source_records(id);
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE api_keys ADD CONSTRAINT api_keys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_approval_request_id_fkey FOREIGN KEY (approval_request_id) REFERENCES approval_requests(id);
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE approval_group_members ADD CONSTRAINT approval_group_members_approval_group_id_fkey FOREIGN KEY (approval_group_id) REFERENCES approval_groups(id) ON DELETE CASCADE;
ALTER TABLE approval_group_members ADD CONSTRAINT approval_group_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE approval_groups ADD CONSTRAINT approval_groups_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_proposal_id_fkey FOREIGN KEY (proposal_id) REFERENCES decision_proposals(id);
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_proposal_id_fkey FOREIGN KEY (proposal_id) REFERENCES decision_proposals(id);
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE approval_thresholds ADD CONSTRAINT approval_thresholds_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_retention_policy_id_fkey FOREIGN KEY (retention_policy_id) REFERENCES retention_policies(id);
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE assertion_results ADD CONSTRAINT assertion_results_run_id_fkey FOREIGN KEY (run_id) REFERENCES certification_runs(id);
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_acr_id_fkey FOREIGN KEY (acr_id) REFERENCES action_certification_records(id);
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_action_plan_id_fkey FOREIGN KEY (action_plan_id) REFERENCES action_plans(id);
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES evidence_items(id);
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE batch_records ADD CONSTRAINT batch_records_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES batch_artifacts(id);
ALTER TABLE batch_records ADD CONSTRAINT batch_records_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE batch_records ADD CONSTRAINT batch_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE business_units ADD CONSTRAINT business_units_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES business_units(id);
ALTER TABLE business_units ADD CONSTRAINT business_units_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES canonical_invoices(id);
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE carriers ADD CONSTRAINT carriers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_promoted_case_id_fkey FOREIGN KEY (promoted_case_id) REFERENCES cases(id);
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE case_events ADD CONSTRAINT case_events_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE case_events ADD CONSTRAINT case_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE cases ADD CONSTRAINT cases_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES canonical_invoices(id);
ALTER TABLE cases ADD CONSTRAINT cases_primary_case_id_fkey FOREIGN KEY (primary_case_id) REFERENCES cases(id);
ALTER TABLE cases ADD CONSTRAINT cases_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE connector_responses ADD CONSTRAINT connector_responses_envelope_id_fkey FOREIGN KEY (envelope_id) REFERENCES execution_envelopes(id);
ALTER TABLE connector_responses ADD CONSTRAINT connector_responses_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE connectors ADD CONSTRAINT connectors_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE contract_clauses ADD CONSTRAINT contract_clauses_contract_rate_id_fkey FOREIGN KEY (contract_rate_id) REFERENCES contract_rates(id) ON DELETE CASCADE;
ALTER TABLE contract_clauses ADD CONSTRAINT contract_clauses_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_supersedes_id_fkey FOREIGN KEY (supersedes_id) REFERENCES contract_rates(id);
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_action_intent_id_fkey FOREIGN KEY (action_intent_id) REFERENCES action_intents(id);
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_finding_id_fkey FOREIGN KEY (finding_id) REFERENCES findings(id);
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_reasoning_trace_id_fkey FOREIGN KEY (reasoning_trace_id) REFERENCES reasoning_traces(id);
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_original_record_id_fkey FOREIGN KEY (original_record_id) REFERENCES source_records(id);
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_connector_id_fkey FOREIGN KEY (connector_id) REFERENCES connectors(id);
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_execution_envelope_id_fkey FOREIGN KEY (execution_envelope_id) REFERENCES execution_envelopes(id);
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE documents ADD CONSTRAINT documents_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE documents ADD CONSTRAINT documents_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_evaluation_run_id_fkey FOREIGN KEY (evaluation_run_id) REFERENCES evaluation_runs(id);
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_bundle_id_fkey FOREIGN KEY (bundle_id) REFERENCES evidence_bundles(id);
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_bundle_id_fkey FOREIGN KEY (bundle_id) REFERENCES evidence_bundles(id);
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_action_plan_id_fkey FOREIGN KEY (action_plan_id) REFERENCES action_plans(id);
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_token_id_fkey FOREIGN KEY (token_id) REFERENCES governance_tokens(id);
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_counterparty_id_fkey FOREIGN KEY (counterparty_id) REFERENCES carriers(id);
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_expected_invoice_id_fkey FOREIGN KEY (expected_invoice_id) REFERENCES canonical_invoices(id);
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_superseded_by_fkey FOREIGN KEY (superseded_by) REFERENCES expected_recoveries(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE external_acknowledgments ADD CONSTRAINT external_acknowledgments_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE external_acknowledgments ADD CONSTRAINT external_acknowledgments_dispatch_ticket_id_fkey FOREIGN KEY (dispatch_ticket_id) REFERENCES dispatch_tickets(id);
ALTER TABLE external_acknowledgments ADD CONSTRAINT external_acknowledgments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE external_responses ADD CONSTRAINT external_responses_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE external_responses ADD CONSTRAINT external_responses_execution_attempt_id_fkey FOREIGN KEY (execution_attempt_id) REFERENCES execution_envelopes(id);
ALTER TABLE external_responses ADD CONSTRAINT external_responses_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE external_responses ADD CONSTRAINT external_responses_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE facilities ADD CONSTRAINT facilities_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE findings ADD CONSTRAINT findings_bundle_id_fkey FOREIGN KEY (bundle_id) REFERENCES evidence_bundles(id);
ALTER TABLE findings ADD CONSTRAINT findings_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE findings ADD CONSTRAINT findings_superseded_by_fkey FOREIGN KEY (superseded_by) REFERENCES findings(id);
ALTER TABLE findings ADD CONSTRAINT findings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_policy_bundle_id_fkey FOREIGN KEY (policy_bundle_id) REFERENCES policy_bundles(id);
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_proposal_id_fkey FOREIGN KEY (proposal_id) REFERENCES decision_proposals(id);
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_decision_id_fkey FOREIGN KEY (decision_id) REFERENCES governance_decisions(id);
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_connector_id_fkey FOREIGN KEY (connector_id) REFERENCES connectors(id);
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_canonical_invoice_id_fkey FOREIGN KEY (canonical_invoice_id) REFERENCES canonical_invoices(id) ON DELETE CASCADE;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_reversal_of_entry_id_fkey FOREIGN KEY (reversal_of_entry_id) REFERENCES ledger_entries(id);
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_source_recovery_match_id_fkey FOREIGN KEY (source_recovery_match_id) REFERENCES recovery_matches(id);
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE lineage_records ADD CONSTRAINT lineage_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE model_calls ADD CONSTRAINT model_calls_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE outbox ADD CONSTRAINT outbox_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE outcomes ADD CONSTRAINT outcomes_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE outcomes ADD CONSTRAINT outcomes_recon_id_fkey FOREIGN KEY (recon_id) REFERENCES reconciliations(id);
ALTER TABLE outcomes ADD CONSTRAINT outcomes_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE override_records ADD CONSTRAINT override_records_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE override_records ADD CONSTRAINT override_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE password_reset_tokens ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE policy_bundles ADD CONSTRAINT policy_bundles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE proofs_of_delivery ADD CONSTRAINT proofs_of_delivery_shipment_id_fkey FOREIGN KEY (shipment_id) REFERENCES shipments(id);
ALTER TABLE proofs_of_delivery ADD CONSTRAINT proofs_of_delivery_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_retention_policy_id_fkey FOREIGN KEY (retention_policy_id) REFERENCES retention_policies(id);
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE quarantine_items ADD CONSTRAINT quarantine_items_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE quarantine_items ADD CONSTRAINT quarantine_items_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_envelope_id_fkey FOREIGN KEY (envelope_id) REFERENCES execution_envelopes(id);
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_external_response_id_fkey FOREIGN KEY (external_response_id) REFERENCES external_responses(id);
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_counterparty_id_fkey FOREIGN KEY (counterparty_id) REFERENCES carriers(id);
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_related_case_id_fkey FOREIGN KEY (related_case_id) REFERENCES cases(id);
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_expected_recovery_id_fkey FOREIGN KEY (expected_recovery_id) REFERENCES expected_recoveries(id);
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_recovery_instrument_id_fkey FOREIGN KEY (recovery_instrument_id) REFERENCES recovery_instruments(id);
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_superseded_by_fkey FOREIGN KEY (superseded_by) REFERENCES recovery_proofs(id);
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_run_id_fkey FOREIGN KEY (run_id) REFERENCES certification_runs(id);
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_restore_job_id_fkey FOREIGN KEY (restore_job_id) REFERENCES restore_jobs(id);
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_carrier_id_fkey FOREIGN KEY (carrier_id) REFERENCES carriers(id);
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_shipment_id_fkey FOREIGN KEY (shipment_id) REFERENCES shipments(id) ON DELETE CASCADE;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE shipments ADD CONSTRAINT shipments_carrier_id_fkey FOREIGN KEY (carrier_id) REFERENCES carriers(id);
ALTER TABLE shipments ADD CONSTRAINT shipments_dest_facility_id_fkey FOREIGN KEY (dest_facility_id) REFERENCES facilities(id);
ALTER TABLE shipments ADD CONSTRAINT shipments_origin_facility_id_fkey FOREIGN KEY (origin_facility_id) REFERENCES facilities(id);
ALTER TABLE shipments ADD CONSTRAINT shipments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE source_record_states ADD CONSTRAINT source_record_states_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE source_record_states ADD CONSTRAINT source_record_states_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE source_records ADD CONSTRAINT source_records_deduplication_canonical_record_id_fkey FOREIGN KEY (deduplication_canonical_record_id) REFERENCES source_records(id);
ALTER TABLE source_records ADD CONSTRAINT source_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE step_up_assertions ADD CONSTRAINT step_up_assertions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE step_up_assertions ADD CONSTRAINT step_up_assertions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE tasks ADD CONSTRAINT tasks_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;
ALTER TABLE tasks ADD CONSTRAINT tasks_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE tenant_keys ADD CONSTRAINT tenant_keys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE tenant_notification_settings ADD CONSTRAINT tenant_notification_settings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_approval_group_id_fkey FOREIGN KEY (approval_group_id) REFERENCES approval_groups(id);
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE transparency_log_commits ADD CONSTRAINT transparency_log_commits_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_acr_id_fkey FOREIGN KEY (acr_id) REFERENCES action_certification_records(id);
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_commit_id_fkey FOREIGN KEY (commit_id) REFERENCES transparency_log_commits(id);
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE users ADD CONSTRAINT users_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE validation_results ADD CONSTRAINT validation_results_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE variance_records ADD CONSTRAINT variance_records_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id);
ALTER TABLE variance_records ADD CONSTRAINT variance_records_proposal_id_fkey FOREIGN KEY (proposal_id) REFERENCES decision_proposals(id);
ALTER TABLE variance_records ADD CONSTRAINT variance_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES source_records(id);
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE write_offs ADD CONSTRAINT write_offs_case_id_fkey FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_expected_recovery_id_fkey FOREIGN KEY (expected_recovery_id) REFERENCES expected_recoveries(id);
ALTER TABLE write_offs ADD CONSTRAINT write_offs_ledger_entry_id_fkey FOREIGN KEY (ledger_entry_id) REFERENCES ledger_entries(id);
ALTER TABLE write_offs ADD CONSTRAINT write_offs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_acr_version_not_null NOT NULL acr_version;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_archive_eligible_not_null NOT NULL archive_eligible;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_artifact_hashes_not_null NOT NULL artifact_hashes;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_case_id_not_null NOT NULL case_id;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_certified_at_not_null NOT NULL certified_at;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_crypto_shred_status_not_null NOT NULL crypto_shred_status;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_currency_not_null NOT NULL currency;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_id_not_null NOT NULL id;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_kid_not_null NOT NULL kid;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_merkle_root_not_null NOT NULL merkle_root;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_retention_class_not_null NOT NULL retention_class;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_signature_not_null NOT NULL signature;
ALTER TABLE action_certification_records ADD CONSTRAINT action_certification_records_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE action_intents ADD CONSTRAINT action_intents_action_type_not_null NOT NULL action_type;
ALTER TABLE action_intents ADD CONSTRAINT action_intents_agent_id_not_null NOT NULL agent_id;
ALTER TABLE action_intents ADD CONSTRAINT action_intents_case_id_not_null NOT NULL case_id;
ALTER TABLE action_intents ADD CONSTRAINT action_intents_declared_at_not_null NOT NULL declared_at;
ALTER TABLE action_intents ADD CONSTRAINT action_intents_id_not_null NOT NULL id;
ALTER TABLE action_intents ADD CONSTRAINT action_intents_policy_version_not_null NOT NULL policy_version;
ALTER TABLE action_intents ADD CONSTRAINT action_intents_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_authorization_required_not_null NOT NULL authorization_required;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_case_id_not_null NOT NULL case_id;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_created_at_not_null NOT NULL created_at;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_created_by_not_null NOT NULL created_by;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_currency_not_null NOT NULL currency;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_expected_outcome_not_null NOT NULL expected_outcome;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_id_not_null NOT NULL id;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_recommended_action_not_null NOT NULL recommended_action;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_risk_level_not_null NOT NULL risk_level;
ALTER TABLE action_plans ADD CONSTRAINT action_plans_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE agent_tool_permissions ADD CONSTRAINT agent_tool_permissions_allowed_not_null NOT NULL allowed;
ALTER TABLE agent_tool_permissions ADD CONSTRAINT agent_tool_permissions_created_at_not_null NOT NULL created_at;
ALTER TABLE agent_tool_permissions ADD CONSTRAINT agent_tool_permissions_description_not_null NOT NULL description;
ALTER TABLE agent_tool_permissions ADD CONSTRAINT agent_tool_permissions_id_not_null NOT NULL id;
ALTER TABLE agent_tool_permissions ADD CONSTRAINT agent_tool_permissions_requires_approval_not_null NOT NULL requires_approval;
ALTER TABLE agent_tool_permissions ADD CONSTRAINT agent_tool_permissions_tool_name_not_null NOT NULL tool_name;
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_created_at_not_null NOT NULL created_at;
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_external_source_ref_not_null NOT NULL external_source_ref;
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_id_not_null NOT NULL id;
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_original_record_id_not_null NOT NULL original_record_id;
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_reason_not_null NOT NULL reason;
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_source_record_id_not_null NOT NULL source_record_id;
ALTER TABLE ambiguity_queue ADD CONSTRAINT ambiguity_queue_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE api_keys ADD CONSTRAINT api_keys_created_at_not_null NOT NULL created_at;
ALTER TABLE api_keys ADD CONSTRAINT api_keys_created_by_not_null NOT NULL created_by;
ALTER TABLE api_keys ADD CONSTRAINT api_keys_id_not_null NOT NULL id;
ALTER TABLE api_keys ADD CONSTRAINT api_keys_key_hash_not_null NOT NULL key_hash;
ALTER TABLE api_keys ADD CONSTRAINT api_keys_key_prefix_not_null NOT NULL key_prefix;
ALTER TABLE api_keys ADD CONSTRAINT api_keys_name_not_null NOT NULL name;
ALTER TABLE api_keys ADD CONSTRAINT api_keys_scopes_not_null NOT NULL scopes;
ALTER TABLE api_keys ADD CONSTRAINT api_keys_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_actor_sub_not_null NOT NULL actor_sub;
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_approval_request_id_not_null NOT NULL approval_request_id;
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_decided_at_not_null NOT NULL decided_at;
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_decision_not_null NOT NULL decision;
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_id_not_null NOT NULL id;
ALTER TABLE approval_decisions ADD CONSTRAINT approval_decisions_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE approval_group_members ADD CONSTRAINT approval_group_members_added_at_not_null NOT NULL added_at;
ALTER TABLE approval_group_members ADD CONSTRAINT approval_group_members_approval_group_id_not_null NOT NULL approval_group_id;
ALTER TABLE approval_group_members ADD CONSTRAINT approval_group_members_id_not_null NOT NULL id;
ALTER TABLE approval_group_members ADD CONSTRAINT approval_group_members_user_id_not_null NOT NULL user_id;
ALTER TABLE approval_groups ADD CONSTRAINT approval_groups_created_at_not_null NOT NULL created_at;
ALTER TABLE approval_groups ADD CONSTRAINT approval_groups_description_not_null NOT NULL description;
ALTER TABLE approval_groups ADD CONSTRAINT approval_groups_id_not_null NOT NULL id;
ALTER TABLE approval_groups ADD CONSTRAINT approval_groups_min_approvers_not_null NOT NULL min_approvers;
ALTER TABLE approval_groups ADD CONSTRAINT approval_groups_name_not_null NOT NULL name;
ALTER TABLE approval_groups ADD CONSTRAINT approval_groups_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_approval_level_not_null NOT NULL approval_level;
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_deadline_at_not_null NOT NULL deadline_at;
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_id_not_null NOT NULL id;
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_proposal_id_not_null NOT NULL proposal_id;
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_requested_at_not_null NOT NULL requested_at;
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_status_not_null NOT NULL status;
ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_created_at_not_null NOT NULL created_at;
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_id_not_null NOT NULL id;
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_proposal_id_not_null NOT NULL proposal_id;
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_proposer_sub_not_null NOT NULL proposer_sub;
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_status_not_null NOT NULL status;
ALTER TABLE approval_tasks ADD CONSTRAINT approval_tasks_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE approval_thresholds ADD CONSTRAINT approval_thresholds_created_at_not_null NOT NULL created_at;
ALTER TABLE approval_thresholds ADD CONSTRAINT approval_thresholds_currency_not_null NOT NULL currency;
ALTER TABLE approval_thresholds ADD CONSTRAINT approval_thresholds_escalate_after_hours_not_null NOT NULL escalate_after_hours;
ALTER TABLE approval_thresholds ADD CONSTRAINT approval_thresholds_id_not_null NOT NULL id;
ALTER TABLE approval_thresholds ADD CONSTRAINT approval_thresholds_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_archive_scope_not_null NOT NULL archive_scope;
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_created_at_not_null NOT NULL created_at;
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_id_not_null NOT NULL id;
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_integrity_metadata_not_null NOT NULL integrity_metadata;
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_legal_hold_checked_not_null NOT NULL legal_hold_checked;
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_record_ids_not_null NOT NULL record_ids;
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_requested_by_not_null NOT NULL requested_by;
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_status_not_null NOT NULL status;
ALTER TABLE archive_jobs ADD CONSTRAINT archive_jobs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE assertion_results ADD CONSTRAINT assertion_results_asserted_at_not_null NOT NULL asserted_at;
ALTER TABLE assertion_results ADD CONSTRAINT assertion_results_assertion_name_not_null NOT NULL assertion_name;
ALTER TABLE assertion_results ADD CONSTRAINT assertion_results_id_not_null NOT NULL id;
ALTER TABLE assertion_results ADD CONSTRAINT assertion_results_passed_not_null NOT NULL passed;
ALTER TABLE assertion_results ADD CONSTRAINT assertion_results_run_id_not_null NOT NULL run_id;
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_case_id_not_null NOT NULL case_id;
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_chain_root_hash_not_null NOT NULL chain_root_hash;
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_event_count_not_null NOT NULL event_count;
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_events_snapshot_not_null NOT NULL events_snapshot;
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_id_not_null NOT NULL id;
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_sealed_at_not_null NOT NULL sealed_at;
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_sealed_by_not_null NOT NULL sealed_by;
ALTER TABLE audit_chains ADD CONSTRAINT audit_chains_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_acr_id_not_null NOT NULL acr_id;
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_id_not_null NOT NULL id;
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_indexed_at_not_null NOT NULL indexed_at;
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_object_hash_not_null NOT NULL object_hash;
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_object_name_not_null NOT NULL object_name;
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE audit_worm_index ADD CONSTRAINT audit_worm_index_worm_bucket_not_null NOT NULL worm_bucket;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_action_plan_id_not_null NOT NULL action_plan_id;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_action_type_not_null NOT NULL action_type;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_case_id_not_null NOT NULL case_id;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_decided_at_not_null NOT NULL decided_at;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_decided_by_not_null NOT NULL decided_by;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_decision_not_null NOT NULL decision;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_expires_at_not_null NOT NULL expires_at;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_id_not_null NOT NULL id;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_policy_version_id_not_null NOT NULL policy_version_id;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_required_approvals_not_null NOT NULL required_approvals;
ALTER TABLE authorization_decisions ADD CONSTRAINT authorization_decisions_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_ambiguous_count_not_null NOT NULL ambiguous_count;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_channel_not_null NOT NULL channel;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_created_at_not_null NOT NULL created_at;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_declared_record_count_not_null NOT NULL declared_record_count;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_declared_schema_not_null NOT NULL declared_schema;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_duplicate_count_not_null NOT NULL duplicate_count;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_first_seen_count_not_null NOT NULL first_seen_count;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_id_not_null NOT NULL id;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_processed_count_not_null NOT NULL processed_count;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_processing_status_not_null NOT NULL processing_status;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_quarantined_count_not_null NOT NULL quarantined_count;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_received_at_not_null NOT NULL received_at;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_rejected_count_not_null NOT NULL rejected_count;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE batch_artifacts ADD CONSTRAINT batch_artifacts_total_records_not_null NOT NULL total_records;
ALTER TABLE batch_records ADD CONSTRAINT batch_records_batch_id_not_null NOT NULL batch_id;
ALTER TABLE batch_records ADD CONSTRAINT batch_records_created_at_not_null NOT NULL created_at;
ALTER TABLE batch_records ADD CONSTRAINT batch_records_id_not_null NOT NULL id;
ALTER TABLE batch_records ADD CONSTRAINT batch_records_outcome_not_null NOT NULL outcome;
ALTER TABLE batch_records ADD CONSTRAINT batch_records_record_index_not_null NOT NULL record_index;
ALTER TABLE batch_records ADD CONSTRAINT batch_records_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE business_units ADD CONSTRAINT business_units_code_not_null NOT NULL code;
ALTER TABLE business_units ADD CONSTRAINT business_units_created_at_not_null NOT NULL created_at;
ALTER TABLE business_units ADD CONSTRAINT business_units_id_not_null NOT NULL id;
ALTER TABLE business_units ADD CONSTRAINT business_units_name_not_null NOT NULL name;
ALTER TABLE business_units ADD CONSTRAINT business_units_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_canonical_hash_not_null NOT NULL canonical_hash;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_carrier_id_not_null NOT NULL carrier_id;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_charge_lines_not_null NOT NULL charge_lines;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_created_at_not_null NOT NULL created_at;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_currency_not_null NOT NULL currency;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_id_not_null NOT NULL id;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_invoice_date_not_null NOT NULL invoice_date;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_invoice_number_not_null NOT NULL invoice_number;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_kid_not_null NOT NULL kid;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_signature_not_null NOT NULL signature;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_source_record_id_not_null NOT NULL source_record_id;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_total_amount_not_null NOT NULL total_amount;
ALTER TABLE canonical_invoices ADD CONSTRAINT canonical_invoices_transport_mode_not_null NOT NULL transport_mode;
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_created_at_not_null NOT NULL created_at;
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_dest_city_not_null NOT NULL dest_city;
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_equipment_type_not_null NOT NULL equipment_type;
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_id_not_null NOT NULL id;
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_invoice_id_not_null NOT NULL invoice_id;
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_mode_not_null NOT NULL mode;
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_origin_city_not_null NOT NULL origin_city;
ALTER TABLE canonical_shipments ADD CONSTRAINT canonical_shipments_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE carriers ADD CONSTRAINT carriers_address_not_null NOT NULL address;
ALTER TABLE carriers ADD CONSTRAINT carriers_cc_emails_not_null NOT NULL cc_emails;
ALTER TABLE carriers ADD CONSTRAINT carriers_contact_person_not_null NOT NULL contact_person;
ALTER TABLE carriers ADD CONSTRAINT carriers_contact_phone_not_null NOT NULL contact_phone;
ALTER TABLE carriers ADD CONSTRAINT carriers_created_at_not_null NOT NULL created_at;
ALTER TABLE carriers ADD CONSTRAINT carriers_email_not_null NOT NULL email;
ALTER TABLE carriers ADD CONSTRAINT carriers_id_not_null NOT NULL id;
ALTER TABLE carriers ADD CONSTRAINT carriers_name_not_null NOT NULL name;
ALTER TABLE carriers ADD CONSTRAINT carriers_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_candidate_type_not_null NOT NULL candidate_type;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_created_at_not_null NOT NULL created_at;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_currency_not_null NOT NULL currency;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_finding_ids_not_null NOT NULL finding_ids;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_grouping_key_not_null NOT NULL grouping_key;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_id_not_null NOT NULL id;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_recommended_case_type_not_null NOT NULL recommended_case_type;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_recommended_priority_not_null NOT NULL recommended_priority;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_status_not_null NOT NULL status;
ALTER TABLE case_candidates ADD CONSTRAINT case_candidates_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE case_events ADD CONSTRAINT case_events_actor_sub_not_null NOT NULL actor_sub;
ALTER TABLE case_events ADD CONSTRAINT case_events_case_id_not_null NOT NULL case_id;
ALTER TABLE case_events ADD CONSTRAINT case_events_event_type_not_null NOT NULL event_type;
ALTER TABLE case_events ADD CONSTRAINT case_events_id_not_null NOT NULL id;
ALTER TABLE case_events ADD CONSTRAINT case_events_occurred_at_not_null NOT NULL occurred_at;
ALTER TABLE case_events ADD CONSTRAINT case_events_payload_not_null NOT NULL payload;
ALTER TABLE case_events ADD CONSTRAINT case_events_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_actor_not_null NOT NULL actor;
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_case_id_not_null NOT NULL case_id;
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_event_type_not_null NOT NULL event_type;
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_id_not_null NOT NULL id;
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_occurred_at_not_null NOT NULL occurred_at;
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_payload_not_null NOT NULL payload;
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_summary_not_null NOT NULL summary;
ALTER TABLE case_timeline_entries ADD CONSTRAINT case_timeline_entries_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE cases ADD CONSTRAINT cases_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE cases ADD CONSTRAINT cases_id_not_null NOT NULL id;
ALTER TABLE cases ADD CONSTRAINT cases_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE cases ADD CONSTRAINT cases_opened_at_not_null NOT NULL opened_at;
ALTER TABLE cases ADD CONSTRAINT cases_retention_class_not_null NOT NULL retention_class;
ALTER TABLE cases ADD CONSTRAINT cases_state_not_null NOT NULL state;
ALTER TABLE cases ADD CONSTRAINT cases_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE cases ADD CONSTRAINT cases_version_not_null NOT NULL version;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_failed_not_null NOT NULL failed;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_id_not_null NOT NULL id;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_passed_not_null NOT NULL passed;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_policy_version_not_null NOT NULL policy_version;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_run_type_not_null NOT NULL run_type;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_skipped_not_null NOT NULL skipped;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_started_at_not_null NOT NULL started_at;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_status_not_null NOT NULL status;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_target_service_not_null NOT NULL target_service;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_total_assertions_not_null NOT NULL total_assertions;
ALTER TABLE certification_runs ADD CONSTRAINT certification_runs_triggered_by_not_null NOT NULL triggered_by;
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_assessed_at_not_null NOT NULL assessed_at;
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_calibration_version_not_null NOT NULL calibration_version;
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_id_not_null NOT NULL id;
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_model_id_not_null NOT NULL model_id;
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_score_not_null NOT NULL score;
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_subject_id_not_null NOT NULL subject_id;
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_subject_type_not_null NOT NULL subject_type;
ALTER TABLE confidence_assessments ADD CONSTRAINT confidence_assessments_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE connector_responses ADD CONSTRAINT connector_responses_connector_id_not_null NOT NULL connector_id;
ALTER TABLE connector_responses ADD CONSTRAINT connector_responses_envelope_id_not_null NOT NULL envelope_id;
ALTER TABLE connector_responses ADD CONSTRAINT connector_responses_id_not_null NOT NULL id;
ALTER TABLE connector_responses ADD CONSTRAINT connector_responses_received_at_not_null NOT NULL received_at;
ALTER TABLE connector_responses ADD CONSTRAINT connector_responses_status_code_not_null NOT NULL status_code;
ALTER TABLE connector_responses ADD CONSTRAINT connector_responses_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE connectors ADD CONSTRAINT connectors_auth_method_not_null NOT NULL auth_method;
ALTER TABLE connectors ADD CONSTRAINT connectors_certification_state_not_null NOT NULL certification_state;
ALTER TABLE connectors ADD CONSTRAINT connectors_connector_type_not_null NOT NULL connector_type;
ALTER TABLE connectors ADD CONSTRAINT connectors_created_at_not_null NOT NULL created_at;
ALTER TABLE connectors ADD CONSTRAINT connectors_credentials_ref_not_null NOT NULL credentials_ref;
ALTER TABLE connectors ADD CONSTRAINT connectors_endpoint_url_not_null NOT NULL endpoint_url;
ALTER TABLE connectors ADD CONSTRAINT connectors_id_not_null NOT NULL id;
ALTER TABLE connectors ADD CONSTRAINT connectors_name_not_null NOT NULL name;
ALTER TABLE connectors ADD CONSTRAINT connectors_operational_state_not_null NOT NULL operational_state;
ALTER TABLE connectors ADD CONSTRAINT connectors_rate_limit_rps_not_null NOT NULL rate_limit_rps;
ALTER TABLE connectors ADD CONSTRAINT connectors_source_type_not_null NOT NULL source_type;
ALTER TABLE connectors ADD CONSTRAINT connectors_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE connectors ADD CONSTRAINT connectors_trust_tier_not_null NOT NULL trust_tier;
ALTER TABLE connectors ADD CONSTRAINT connectors_updated_at_not_null NOT NULL updated_at;
ALTER TABLE contract_clauses ADD CONSTRAINT contract_clauses_clause_type_not_null NOT NULL clause_type;
ALTER TABLE contract_clauses ADD CONSTRAINT contract_clauses_created_at_not_null NOT NULL created_at;
ALTER TABLE contract_clauses ADD CONSTRAINT contract_clauses_description_not_null NOT NULL description;
ALTER TABLE contract_clauses ADD CONSTRAINT contract_clauses_id_not_null NOT NULL id;
ALTER TABLE contract_clauses ADD CONSTRAINT contract_clauses_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE contract_clauses ADD CONSTRAINT contract_clauses_value_expression_not_null NOT NULL value_expression;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_carrier_id_not_null NOT NULL carrier_id;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_created_at_not_null NOT NULL created_at;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_currency_not_null NOT NULL currency;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_effective_on_not_null NOT NULL effective_on;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_id_not_null NOT NULL id;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_rate_type_not_null NOT NULL rate_type;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_rate_value_not_null NOT NULL rate_value;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE contract_rates ADD CONSTRAINT contract_rates_version_not_null NOT NULL version;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_affected_key_ids_not_null NOT NULL affected_key_ids;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_affected_record_ids_not_null NOT NULL affected_record_ids;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_created_at_not_null NOT NULL created_at;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_id_not_null NOT NULL id;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_legal_hold_blocked_not_null NOT NULL legal_hold_blocked;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_legal_hold_checked_not_null NOT NULL legal_hold_checked;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_requested_by_not_null NOT NULL requested_by;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_status_not_null NOT NULL status;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_subject_ref_not_null NOT NULL subject_ref;
ALTER TABLE crypto_shred_requests ADD CONSTRAINT crypto_shred_requests_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_case_id_not_null NOT NULL case_id;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_created_at_not_null NOT NULL created_at;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_finding_id_not_null NOT NULL finding_id;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_id_not_null NOT NULL id;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_kid_not_null NOT NULL kid;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_proposal_hash_not_null NOT NULL proposal_hash;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_proposed_action_not_null NOT NULL proposed_action;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_proposer_sub_not_null NOT NULL proposer_sub;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_signature_not_null NOT NULL signature;
ALTER TABLE decision_proposals ADD CONSTRAINT decision_proposals_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_decided_at_not_null NOT NULL decided_at;
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_deduplication_key_not_null NOT NULL deduplication_key;
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_id_not_null NOT NULL id;
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_outcome_not_null NOT NULL outcome;
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_payload_hash_not_null NOT NULL payload_hash;
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_source_record_id_not_null NOT NULL source_record_id;
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_source_type_not_null NOT NULL source_type;
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_source_type_version_not_null NOT NULL source_type_version;
ALTER TABLE dedup_index ADD CONSTRAINT dedup_index_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_created_at_not_null NOT NULL created_at;
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_id_not_null NOT NULL id;
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_idempotency_key_not_null NOT NULL idempotency_key;
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_last_error_not_null NOT NULL last_error;
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_retry_count_not_null NOT NULL retry_count;
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_status_not_null NOT NULL status;
ALTER TABLE dispatch_tickets ADD CONSTRAINT dispatch_tickets_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE documents ADD CONSTRAINT documents_content_hash_not_null NOT NULL content_hash;
ALTER TABLE documents ADD CONSTRAINT documents_created_at_not_null NOT NULL created_at;
ALTER TABLE documents ADD CONSTRAINT documents_document_type_not_null NOT NULL document_type;
ALTER TABLE documents ADD CONSTRAINT documents_file_name_not_null NOT NULL file_name;
ALTER TABLE documents ADD CONSTRAINT documents_id_not_null NOT NULL id;
ALTER TABLE documents ADD CONSTRAINT documents_mime_type_not_null NOT NULL mime_type;
ALTER TABLE documents ADD CONSTRAINT documents_retention_class_not_null NOT NULL retention_class;
ALTER TABLE documents ADD CONSTRAINT documents_size_bytes_not_null NOT NULL size_bytes;
ALTER TABLE documents ADD CONSTRAINT documents_storage_uri_not_null NOT NULL storage_uri;
ALTER TABLE documents ADD CONSTRAINT documents_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_description_not_null NOT NULL description;
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_detected_at_not_null NOT NULL detected_at;
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_id_not_null NOT NULL id;
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_metric_name_not_null NOT NULL metric_name;
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_reviewed_by_not_null NOT NULL reviewed_by;
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_severity_not_null NOT NULL severity;
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_signal_type_not_null NOT NULL signal_type;
ALTER TABLE drift_signals ADD CONSTRAINT drift_signals_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_cases_evaluated_not_null NOT NULL cases_evaluated;
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_id_not_null NOT NULL id;
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_model_version_not_null NOT NULL model_version;
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_result_payload_not_null NOT NULL result_payload;
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_run_type_not_null NOT NULL run_type;
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_started_at_not_null NOT NULL started_at;
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_status_not_null NOT NULL status;
ALTER TABLE evaluation_runs ADD CONSTRAINT evaluation_runs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_added_at_not_null NOT NULL added_at;
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_bundle_id_not_null NOT NULL bundle_id;
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_bundle_version_not_null NOT NULL bundle_version;
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_entity_id_not_null NOT NULL entity_id;
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_id_not_null NOT NULL id;
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_leaf_hash_not_null NOT NULL leaf_hash;
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_leaf_type_not_null NOT NULL leaf_type;
ALTER TABLE evidence_bundle_leaves ADD CONSTRAINT evidence_bundle_leaves_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_archive_eligible_not_null NOT NULL archive_eligible;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_bundle_hash_not_null NOT NULL bundle_hash;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_bundle_version_not_null NOT NULL bundle_version;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_case_id_not_null NOT NULL case_id;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_completeness_status_not_null NOT NULL completeness_status;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_created_at_not_null NOT NULL created_at;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_crypto_shred_status_not_null NOT NULL crypto_shred_status;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_id_not_null NOT NULL id;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_kid_not_null NOT NULL kid;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_payload_encryption_alg_not_null NOT NULL payload_encryption_alg;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_payload_hash_alg_not_null NOT NULL payload_hash_alg;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_retention_class_not_null NOT NULL retention_class;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_signature_not_null NOT NULL signature;
ALTER TABLE evidence_bundles ADD CONSTRAINT evidence_bundles_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_added_at_not_null NOT NULL added_at;
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_bundle_id_not_null NOT NULL bundle_id;
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_entity_id_not_null NOT NULL entity_id;
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_id_not_null NOT NULL id;
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_item_hash_not_null NOT NULL item_hash;
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_item_type_not_null NOT NULL item_type;
ALTER TABLE evidence_items ADD CONSTRAINT evidence_items_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_dispatched_at_not_null NOT NULL dispatched_at;
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_env_hash_not_null NOT NULL env_hash;
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_gate_results_not_null NOT NULL gate_results;
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_id_not_null NOT NULL id;
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_kid_not_null NOT NULL kid;
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_signature_not_null NOT NULL signature;
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_status_not_null NOT NULL status;
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE execution_envelopes ADD CONSTRAINT execution_envelopes_token_id_not_null NOT NULL token_id;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_case_id_not_null NOT NULL case_id;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_counterparty_type_not_null NOT NULL counterparty_type;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_created_at_not_null NOT NULL created_at;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_currency_not_null NOT NULL currency;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_expected_amount_not_null NOT NULL expected_amount;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_expected_recovery_method_not_null NOT NULL expected_recovery_method;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_id_not_null NOT NULL id;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_retention_class_not_null NOT NULL retention_class;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_status_not_null NOT NULL status;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_tolerance_policy_id_not_null NOT NULL tolerance_policy_id;
ALTER TABLE expected_recoveries ADD CONSTRAINT expected_recoveries_updated_at_not_null NOT NULL updated_at;
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_created_at_not_null NOT NULL created_at;
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_explanation_not_null NOT NULL explanation;
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_format_not_null NOT NULL format;
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_generated_by_not_null NOT NULL generated_by;
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_id_not_null NOT NULL id;
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_subject_type_not_null NOT NULL subject_type;
ALTER TABLE explanation_artifacts ADD CONSTRAINT explanation_artifacts_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE external_acknowledgments ADD CONSTRAINT external_acknowledgments_ack_payload_not_null NOT NULL ack_payload;
ALTER TABLE external_acknowledgments ADD CONSTRAINT external_acknowledgments_ack_reference_not_null NOT NULL ack_reference;
ALTER TABLE external_acknowledgments ADD CONSTRAINT external_acknowledgments_id_not_null NOT NULL id;
ALTER TABLE external_acknowledgments ADD CONSTRAINT external_acknowledgments_received_at_not_null NOT NULL received_at;
ALTER TABLE external_acknowledgments ADD CONSTRAINT external_acknowledgments_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE external_responses ADD CONSTRAINT external_responses_case_id_not_null NOT NULL case_id;
ALTER TABLE external_responses ADD CONSTRAINT external_responses_id_not_null NOT NULL id;
ALTER TABLE external_responses ADD CONSTRAINT external_responses_payload_hash_not_null NOT NULL payload_hash;
ALTER TABLE external_responses ADD CONSTRAINT external_responses_received_at_not_null NOT NULL received_at;
ALTER TABLE external_responses ADD CONSTRAINT external_responses_response_type_not_null NOT NULL response_type;
ALTER TABLE external_responses ADD CONSTRAINT external_responses_status_not_null NOT NULL status;
ALTER TABLE external_responses ADD CONSTRAINT external_responses_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE facilities ADD CONSTRAINT facilities_address_not_null NOT NULL address;
ALTER TABLE facilities ADD CONSTRAINT facilities_country_not_null NOT NULL country;
ALTER TABLE facilities ADD CONSTRAINT facilities_created_at_not_null NOT NULL created_at;
ALTER TABLE facilities ADD CONSTRAINT facilities_facility_type_not_null NOT NULL facility_type;
ALTER TABLE facilities ADD CONSTRAINT facilities_id_not_null NOT NULL id;
ALTER TABLE facilities ADD CONSTRAINT facilities_name_not_null NOT NULL name;
ALTER TABLE facilities ADD CONSTRAINT facilities_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE findings ADD CONSTRAINT findings_bundle_id_not_null NOT NULL bundle_id;
ALTER TABLE findings ADD CONSTRAINT findings_canonical_record_ids_not_null NOT NULL canonical_record_ids;
ALTER TABLE findings ADD CONSTRAINT findings_case_id_not_null NOT NULL case_id;
ALTER TABLE findings ADD CONSTRAINT findings_confidence_not_null NOT NULL confidence;
ALTER TABLE findings ADD CONSTRAINT findings_created_at_not_null NOT NULL created_at;
ALTER TABLE findings ADD CONSTRAINT findings_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE findings ADD CONSTRAINT findings_id_not_null NOT NULL id;
ALTER TABLE findings ADD CONSTRAINT findings_kid_not_null NOT NULL kid;
ALTER TABLE findings ADD CONSTRAINT findings_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE findings ADD CONSTRAINT findings_retention_class_not_null NOT NULL retention_class;
ALTER TABLE findings ADD CONSTRAINT findings_rule_trace_not_null NOT NULL rule_trace;
ALTER TABLE findings ADD CONSTRAINT findings_signature_not_null NOT NULL signature;
ALTER TABLE findings ADD CONSTRAINT findings_source_record_ids_not_null NOT NULL source_record_ids;
ALTER TABLE findings ADD CONSTRAINT findings_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_decided_at_not_null NOT NULL decided_at;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_decision_hash_not_null NOT NULL decision_hash;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_id_not_null NOT NULL id;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_kid_not_null NOT NULL kid;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_outcome_not_null NOT NULL outcome;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_policy_bundle_id_not_null NOT NULL policy_bundle_id;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_policy_version_not_null NOT NULL policy_version;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_proposal_id_not_null NOT NULL proposal_id;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_signature_not_null NOT NULL signature;
ALTER TABLE governance_decisions ADD CONSTRAINT governance_decisions_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_decision_id_not_null NOT NULL decision_id;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_expires_at_not_null NOT NULL expires_at;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_id_not_null NOT NULL id;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_issued_at_not_null NOT NULL issued_at;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_kid_not_null NOT NULL kid;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_policy_version_not_null NOT NULL policy_version;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_retention_class_not_null NOT NULL retention_class;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_scope_not_null NOT NULL scope;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_signature_not_null NOT NULL signature;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_status_not_null NOT NULL status;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_tenant_binding_not_null NOT NULL tenant_binding;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE governance_tokens ADD CONSTRAINT governance_tokens_token_hash_not_null NOT NULL token_hash;
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_created_at_not_null NOT NULL created_at;
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_id_not_null NOT NULL id;
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_key_value_not_null NOT NULL key_value;
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_status_not_null NOT NULL status;
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_connector_id_not_null NOT NULL connector_id;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_error_detail_not_null NOT NULL error_detail;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_id_not_null NOT NULL id;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_records_accepted_not_null NOT NULL records_accepted;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_records_received_not_null NOT NULL records_received;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_records_rejected_not_null NOT NULL records_rejected;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_started_at_not_null NOT NULL started_at;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_status_not_null NOT NULL status;
ALTER TABLE ingestion_runs ADD CONSTRAINT ingestion_runs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_created_at_not_null NOT NULL created_at;
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_email_not_null NOT NULL email;
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_expires_at_not_null NOT NULL expires_at;
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_id_not_null NOT NULL id;
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_invited_by_not_null NOT NULL invited_by;
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_role_not_null NOT NULL role;
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE invitation_tokens ADD CONSTRAINT invitation_tokens_token_hash_not_null NOT NULL token_hash;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_charge_code_not_null NOT NULL charge_code;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_created_at_not_null NOT NULL created_at;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_currency_not_null NOT NULL currency;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_description_not_null NOT NULL description;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_id_not_null NOT NULL id;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_is_disputed_not_null NOT NULL is_disputed;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_line_number_not_null NOT NULL line_number;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_quantity_not_null NOT NULL quantity;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_total_amount_not_null NOT NULL total_amount;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_unit_price_not_null NOT NULL unit_price;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_amount_not_null NOT NULL amount;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_archive_eligible_not_null NOT NULL archive_eligible;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_case_id_not_null NOT NULL case_id;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_created_at_not_null NOT NULL created_at;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_credit_account_not_null NOT NULL credit_account;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_crypto_shred_status_not_null NOT NULL crypto_shred_status;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_currency_not_null NOT NULL currency;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_debit_account_not_null NOT NULL debit_account;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_entry_type_not_null NOT NULL entry_type;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_id_not_null NOT NULL id;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_posted_at_not_null NOT NULL posted_at;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_retention_class_not_null NOT NULL retention_class;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_status_not_null NOT NULL status;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_applied_at_not_null NOT NULL applied_at;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_applied_by_not_null NOT NULL applied_by;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_effective_from_not_null NOT NULL effective_from;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_hold_scope_not_null NOT NULL hold_scope;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_id_not_null NOT NULL id;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_lifted_by_not_null NOT NULL lifted_by;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_reason_code_not_null NOT NULL reason_code;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_reason_not_null NOT NULL reason;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_status_not_null NOT NULL status;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_subject_id_not_null NOT NULL subject_id;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_subject_type_not_null NOT NULL subject_type;
ALTER TABLE legal_hold_records ADD CONSTRAINT legal_hold_records_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE lineage_records ADD CONSTRAINT lineage_records_entity_id_not_null NOT NULL entity_id;
ALTER TABLE lineage_records ADD CONSTRAINT lineage_records_entity_type_not_null NOT NULL entity_type;
ALTER TABLE lineage_records ADD CONSTRAINT lineage_records_event_type_not_null NOT NULL event_type;
ALTER TABLE lineage_records ADD CONSTRAINT lineage_records_id_not_null NOT NULL id;
ALTER TABLE lineage_records ADD CONSTRAINT lineage_records_payload_hash_not_null NOT NULL payload_hash;
ALTER TABLE lineage_records ADD CONSTRAINT lineage_records_recorded_at_not_null NOT NULL recorded_at;
ALTER TABLE lineage_records ADD CONSTRAINT lineage_records_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_created_at_not_null NOT NULL created_at;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_id_not_null NOT NULL id;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_input_hash_not_null NOT NULL input_hash;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_latency_ms_not_null NOT NULL latency_ms;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_model_id_not_null NOT NULL model_id;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_model_version_not_null NOT NULL model_version;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_output_hash_not_null NOT NULL output_hash;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_prompt_version_not_null NOT NULL prompt_version;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_purpose_not_null NOT NULL purpose;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE outbox ADD CONSTRAINT outbox_created_at_not_null NOT NULL created_at;
ALTER TABLE outbox ADD CONSTRAINT outbox_id_not_null NOT NULL id;
ALTER TABLE outbox ADD CONSTRAINT outbox_partition_key_not_null NOT NULL partition_key;
ALTER TABLE outbox ADD CONSTRAINT outbox_payload_not_null NOT NULL payload;
ALTER TABLE outbox ADD CONSTRAINT outbox_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE outbox ADD CONSTRAINT outbox_topic_not_null NOT NULL topic;
ALTER TABLE outcomes ADD CONSTRAINT outcomes_case_id_not_null NOT NULL case_id;
ALTER TABLE outcomes ADD CONSTRAINT outcomes_id_not_null NOT NULL id;
ALTER TABLE outcomes ADD CONSTRAINT outcomes_kid_not_null NOT NULL kid;
ALTER TABLE outcomes ADD CONSTRAINT outcomes_outcome_hash_not_null NOT NULL outcome_hash;
ALTER TABLE outcomes ADD CONSTRAINT outcomes_outcome_type_not_null NOT NULL outcome_type;
ALTER TABLE outcomes ADD CONSTRAINT outcomes_recon_id_not_null NOT NULL recon_id;
ALTER TABLE outcomes ADD CONSTRAINT outcomes_recorded_at_not_null NOT NULL recorded_at;
ALTER TABLE outcomes ADD CONSTRAINT outcomes_signature_not_null NOT NULL signature;
ALTER TABLE outcomes ADD CONSTRAINT outcomes_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE override_records ADD CONSTRAINT override_records_actor_not_null NOT NULL actor;
ALTER TABLE override_records ADD CONSTRAINT override_records_approved_by_not_null NOT NULL approved_by;
ALTER TABLE override_records ADD CONSTRAINT override_records_id_not_null NOT NULL id;
ALTER TABLE override_records ADD CONSTRAINT override_records_occurred_at_not_null NOT NULL occurred_at;
ALTER TABLE override_records ADD CONSTRAINT override_records_original_decision_not_null NOT NULL original_decision;
ALTER TABLE override_records ADD CONSTRAINT override_records_override_decision_not_null NOT NULL override_decision;
ALTER TABLE override_records ADD CONSTRAINT override_records_override_type_not_null NOT NULL override_type;
ALTER TABLE override_records ADD CONSTRAINT override_records_reason_not_null NOT NULL reason;
ALTER TABLE override_records ADD CONSTRAINT override_records_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE password_reset_otp ADD CONSTRAINT password_reset_otp_created_at_not_null NOT NULL created_at;
ALTER TABLE password_reset_otp ADD CONSTRAINT password_reset_otp_email_not_null NOT NULL email;
ALTER TABLE password_reset_otp ADD CONSTRAINT password_reset_otp_expires_at_not_null NOT NULL expires_at;
ALTER TABLE password_reset_otp ADD CONSTRAINT password_reset_otp_failed_attempts_not_null NOT NULL failed_attempts;
ALTER TABLE password_reset_otp ADD CONSTRAINT password_reset_otp_id_not_null NOT NULL id;
ALTER TABLE password_reset_otp ADD CONSTRAINT password_reset_otp_otp_not_null NOT NULL otp;
ALTER TABLE password_reset_tokens ADD CONSTRAINT password_reset_tokens_created_at_not_null NOT NULL created_at;
ALTER TABLE password_reset_tokens ADD CONSTRAINT password_reset_tokens_expires_at_not_null NOT NULL expires_at;
ALTER TABLE password_reset_tokens ADD CONSTRAINT password_reset_tokens_id_not_null NOT NULL id;
ALTER TABLE password_reset_tokens ADD CONSTRAINT password_reset_tokens_token_hash_not_null NOT NULL token_hash;
ALTER TABLE password_reset_tokens ADD CONSTRAINT password_reset_tokens_user_id_not_null NOT NULL user_id;
ALTER TABLE password_reset_verify ADD CONSTRAINT password_reset_verify_created_at_not_null NOT NULL created_at;
ALTER TABLE password_reset_verify ADD CONSTRAINT password_reset_verify_email_not_null NOT NULL email;
ALTER TABLE password_reset_verify ADD CONSTRAINT password_reset_verify_expires_at_not_null NOT NULL expires_at;
ALTER TABLE password_reset_verify ADD CONSTRAINT password_reset_verify_id_not_null NOT NULL id;
ALTER TABLE password_reset_verify ADD CONSTRAINT password_reset_verify_verify_hash_not_null NOT NULL verify_hash;
ALTER TABLE policy_bundles ADD CONSTRAINT policy_bundles_active_not_null NOT NULL active;
ALTER TABLE policy_bundles ADD CONSTRAINT policy_bundles_deployed_at_not_null NOT NULL deployed_at;
ALTER TABLE policy_bundles ADD CONSTRAINT policy_bundles_id_not_null NOT NULL id;
ALTER TABLE policy_bundles ADD CONSTRAINT policy_bundles_rego_hash_not_null NOT NULL rego_hash;
ALTER TABLE policy_bundles ADD CONSTRAINT policy_bundles_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE policy_bundles ADD CONSTRAINT policy_bundles_version_not_null NOT NULL version;
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_created_at_not_null NOT NULL created_at;
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_id_not_null NOT NULL id;
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_name_not_null NOT NULL name;
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_policy_data_not_null NOT NULL policy_data;
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_promoted_by_not_null NOT NULL promoted_by;
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_status_not_null NOT NULL status;
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE policy_packs ADD CONSTRAINT policy_packs_version_not_null NOT NULL version;
ALTER TABLE proofs_of_delivery ADD CONSTRAINT proofs_of_delivery_content_hash_not_null NOT NULL content_hash;
ALTER TABLE proofs_of_delivery ADD CONSTRAINT proofs_of_delivery_created_at_not_null NOT NULL created_at;
ALTER TABLE proofs_of_delivery ADD CONSTRAINT proofs_of_delivery_document_url_not_null NOT NULL document_url;
ALTER TABLE proofs_of_delivery ADD CONSTRAINT proofs_of_delivery_id_not_null NOT NULL id;
ALTER TABLE proofs_of_delivery ADD CONSTRAINT proofs_of_delivery_signed_by_not_null NOT NULL signed_by;
ALTER TABLE proofs_of_delivery ADD CONSTRAINT proofs_of_delivery_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_created_at_not_null NOT NULL created_at;
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_id_not_null NOT NULL id;
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_legal_hold_blocked_not_null NOT NULL legal_hold_blocked;
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_legal_hold_checked_not_null NOT NULL legal_hold_checked;
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_purge_scope_not_null NOT NULL purge_scope;
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_record_count_not_null NOT NULL record_count;
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_status_not_null NOT NULL status;
ALTER TABLE purge_jobs ADD CONSTRAINT purge_jobs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE quarantine_items ADD CONSTRAINT quarantine_items_id_not_null NOT NULL id;
ALTER TABLE quarantine_items ADD CONSTRAINT quarantine_items_quarantined_at_not_null NOT NULL quarantined_at;
ALTER TABLE quarantine_items ADD CONSTRAINT quarantine_items_raw_payload_not_null NOT NULL raw_payload;
ALTER TABLE quarantine_items ADD CONSTRAINT quarantine_items_reason_not_null NOT NULL reason;
ALTER TABLE quarantine_items ADD CONSTRAINT quarantine_items_released_by_not_null NOT NULL released_by;
ALTER TABLE quarantine_items ADD CONSTRAINT quarantine_items_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_action_intent_not_null NOT NULL action_intent;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_agent_id_not_null NOT NULL agent_id;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_case_id_not_null NOT NULL case_id;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_confidence_not_null NOT NULL confidence;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_created_at_not_null NOT NULL created_at;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_evidence_refs_not_null NOT NULL evidence_refs;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_id_not_null NOT NULL id;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_policy_version_not_null NOT NULL policy_version;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_steps_not_null NOT NULL steps;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE reasoning_traces ADD CONSTRAINT reasoning_traces_tools_used_not_null NOT NULL tools_used;
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_case_id_not_null NOT NULL case_id;
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_currency_not_null NOT NULL currency;
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_delta_amount_not_null NOT NULL delta_amount;
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_envelope_id_not_null NOT NULL envelope_id;
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_id_not_null NOT NULL id;
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_recon_hash_not_null NOT NULL recon_hash;
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_reconciled_at_not_null NOT NULL reconciled_at;
ALTER TABLE reconciliations ADD CONSTRAINT reconciliations_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_counterparty_type_not_null NOT NULL counterparty_type;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_created_at_not_null NOT NULL created_at;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_created_by_not_null NOT NULL created_by;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_currency_not_null NOT NULL currency;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_id_not_null NOT NULL id;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_instrument_amount_not_null NOT NULL instrument_amount;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_instrument_type_not_null NOT NULL instrument_type;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_received_at_not_null NOT NULL received_at;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_retention_class_not_null NOT NULL retention_class;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_status_not_null NOT NULL status;
ALTER TABLE recovery_instruments ADD CONSTRAINT recovery_instruments_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_allocation_status_not_null NOT NULL allocation_status;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_created_at_not_null NOT NULL created_at;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_currency_not_null NOT NULL currency;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_expected_amount_not_null NOT NULL expected_amount;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_expected_recovery_id_not_null NOT NULL expected_recovery_id;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_id_not_null NOT NULL id;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_match_confidence_not_null NOT NULL match_confidence;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_match_method_not_null NOT NULL match_method;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_match_tier_not_null NOT NULL match_tier;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_matched_amount_not_null NOT NULL matched_amount;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_matched_at_not_null NOT NULL matched_at;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_matched_by_not_null NOT NULL matched_by;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_recovery_instrument_id_not_null NOT NULL recovery_instrument_id;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_retention_class_not_null NOT NULL retention_class;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE recovery_matches ADD CONSTRAINT recovery_matches_variance_not_null NOT NULL variance;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_acr_ready_not_null NOT NULL acr_ready;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_archive_eligible_not_null NOT NULL archive_eligible;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_case_id_not_null NOT NULL case_id;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_claimed_amount_not_null NOT NULL claimed_amount;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_created_at_not_null NOT NULL created_at;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_crypto_shred_status_not_null NOT NULL crypto_shred_status;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_currency_not_null NOT NULL currency;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_expected_recovery_ids_not_null NOT NULL expected_recovery_ids;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_id_not_null NOT NULL id;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_ledger_entry_ids_not_null NOT NULL ledger_entry_ids;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_ledger_status_not_null NOT NULL ledger_status;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_recovery_instrument_ids_not_null NOT NULL recovery_instrument_ids;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_recovery_match_ids_not_null NOT NULL recovery_match_ids;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_recovery_status_not_null NOT NULL recovery_status;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_retention_class_not_null NOT NULL retention_class;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_total_expected_not_null NOT NULL total_expected;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_total_recovered_not_null NOT NULL total_recovered;
ALTER TABLE recovery_proofs ADD CONSTRAINT recovery_proofs_total_unrecovered_not_null NOT NULL total_unrecovered;
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_gate_name_not_null NOT NULL gate_name;
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_gate_number_not_null NOT NULL gate_number;
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_id_not_null NOT NULL id;
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_recorded_at_not_null NOT NULL recorded_at;
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_run_id_not_null NOT NULL run_id;
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_score_not_null NOT NULL score;
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_verdict_not_null NOT NULL verdict;
ALTER TABLE release_gate_scoreboards ADD CONSTRAINT release_gate_scoreboards_weight_not_null NOT NULL weight;
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_created_at_not_null NOT NULL created_at;
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_id_not_null NOT NULL id;
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_requested_by_not_null NOT NULL requested_by;
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_restore_type_not_null NOT NULL restore_type;
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_restored_scope_not_null NOT NULL restored_scope;
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_status_not_null NOT NULL status;
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE restore_jobs ADD CONSTRAINT restore_jobs_updated_at_not_null NOT NULL updated_at;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_record_ledger_continuity_verified_not_null NOT NULL ledger_continuity_verified;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_record_projection_consistency_ver_not_null NOT NULL projection_consistency_verified;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_acr_verified_not_null NOT NULL acr_verified;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_created_at_not_null NOT NULL created_at;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_evidence_chain_verified_not_null NOT NULL evidence_chain_verified;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_id_not_null NOT NULL id;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_indexes_rebuilt_not_null NOT NULL indexes_rebuilt;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_legal_hold_verified_not_null NOT NULL legal_hold_verified;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_permissions_verified_not_null NOT NULL permissions_verified;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_residency_verified_not_null NOT NULL residency_verified;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_restore_job_id_not_null NOT NULL restore_job_id;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_source_records_verified_not_null NOT NULL source_records_verified;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_tenant_isolation_verified_not_null NOT NULL tenant_isolation_verified;
ALTER TABLE restore_verification_records ADD CONSTRAINT restore_verification_records_verification_status_not_null NOT NULL verification_status;
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_applied_at_not_null NOT NULL applied_at;
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_applied_by_not_null NOT NULL applied_by;
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_id_not_null NOT NULL id;
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_reason_not_null NOT NULL reason;
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_retention_class_not_null NOT NULL retention_class;
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_subject_id_not_null NOT NULL subject_id;
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_subject_type_not_null NOT NULL subject_type;
ALTER TABLE retention_markers ADD CONSTRAINT retention_markers_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_created_at_not_null NOT NULL created_at;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_created_by_not_null NOT NULL created_by;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_data_class_not_null NOT NULL data_class;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_id_not_null NOT NULL id;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_policy_name_not_null NOT NULL policy_name;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_retention_class_not_null NOT NULL retention_class;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_retention_days_not_null NOT NULL retention_days;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_status_not_null NOT NULL status;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE retention_policies ADD CONSTRAINT retention_policies_updated_at_not_null NOT NULL updated_at;
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_executed_at_not_null NOT NULL executed_at;
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_id_not_null NOT NULL id;
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_input_payload_not_null NOT NULL input_payload;
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_output_payload_not_null NOT NULL output_payload;
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_result_not_null NOT NULL result;
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_rule_id_not_null NOT NULL rule_id;
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE rule_traces ADD CONSTRAINT rule_traces_validator_name_not_null NOT NULL validator_name;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_created_at_not_null NOT NULL created_at;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_destination_not_null NOT NULL destination;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_id_not_null NOT NULL id;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_leg_sequence_not_null NOT NULL leg_sequence;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_origin_not_null NOT NULL origin;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_shipment_id_not_null NOT NULL shipment_id;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE shipment_legs ADD CONSTRAINT shipment_legs_transport_mode_not_null NOT NULL transport_mode;
ALTER TABLE shipments ADD CONSTRAINT shipments_created_at_not_null NOT NULL created_at;
ALTER TABLE shipments ADD CONSTRAINT shipments_id_not_null NOT NULL id;
ALTER TABLE shipments ADD CONSTRAINT shipments_shipment_number_not_null NOT NULL shipment_number;
ALTER TABLE shipments ADD CONSTRAINT shipments_status_not_null NOT NULL status;
ALTER TABLE shipments ADD CONSTRAINT shipments_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE shipments ADD CONSTRAINT shipments_total_volume_m3_not_null NOT NULL total_volume_m3;
ALTER TABLE shipments ADD CONSTRAINT shipments_total_weight_kg_not_null NOT NULL total_weight_kg;
ALTER TABLE shipments ADD CONSTRAINT shipments_transport_mode_not_null NOT NULL transport_mode;
ALTER TABLE shipments ADD CONSTRAINT shipments_updated_at_not_null NOT NULL updated_at;
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_admin_name_not_null NOT NULL admin_name;
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_created_at_not_null NOT NULL created_at;
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_email_not_null NOT NULL email;
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_expires_at_not_null NOT NULL expires_at;
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_failed_attempts_not_null NOT NULL failed_attempts;
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_id_not_null NOT NULL id;
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_org_name_not_null NOT NULL org_name;
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_otp_hash_not_null NOT NULL otp_hash;
ALTER TABLE signup_verification ADD CONSTRAINT signup_verification_password_hash_not_null NOT NULL password_hash;
ALTER TABLE source_record_states ADD CONSTRAINT source_record_states_id_not_null NOT NULL id;
ALTER TABLE source_record_states ADD CONSTRAINT source_record_states_occurred_at_not_null NOT NULL occurred_at;
ALTER TABLE source_record_states ADD CONSTRAINT source_record_states_source_record_id_not_null NOT NULL source_record_id;
ALTER TABLE source_record_states ADD CONSTRAINT source_record_states_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE source_record_states ADD CONSTRAINT source_record_states_to_status_not_null NOT NULL to_status;
ALTER TABLE source_records ADD CONSTRAINT source_records_archive_eligible_not_null NOT NULL archive_eligible;
ALTER TABLE source_records ADD CONSTRAINT source_records_canonical_hash_not_null NOT NULL canonical_hash;
ALTER TABLE source_records ADD CONSTRAINT source_records_channel_metadata_not_null NOT NULL channel_metadata;
ALTER TABLE source_records ADD CONSTRAINT source_records_channel_not_null NOT NULL channel;
ALTER TABLE source_records ADD CONSTRAINT source_records_ciphertext_not_null NOT NULL ciphertext;
ALTER TABLE source_records ADD CONSTRAINT source_records_created_at_not_null NOT NULL created_at;
ALTER TABLE source_records ADD CONSTRAINT source_records_crypto_shred_status_not_null NOT NULL crypto_shred_status;
ALTER TABLE source_records ADD CONSTRAINT source_records_data_classification_not_null NOT NULL data_classification;
ALTER TABLE source_records ADD CONSTRAINT source_records_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE source_records ADD CONSTRAINT source_records_deduplication_outcome_not_null NOT NULL deduplication_outcome;
ALTER TABLE source_records ADD CONSTRAINT source_records_domain_tag_not_null NOT NULL domain_tag;
ALTER TABLE source_records ADD CONSTRAINT source_records_id_not_null NOT NULL id;
ALTER TABLE source_records ADD CONSTRAINT source_records_idempotency_key_not_null NOT NULL idempotency_key;
ALTER TABLE source_records ADD CONSTRAINT source_records_kid_not_null NOT NULL kid;
ALTER TABLE source_records ADD CONSTRAINT source_records_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE source_records ADD CONSTRAINT source_records_payload_encryption_alg_not_null NOT NULL payload_encryption_alg;
ALTER TABLE source_records ADD CONSTRAINT source_records_raw_payload_content_type_not_null NOT NULL raw_payload_content_type;
ALTER TABLE source_records ADD CONSTRAINT source_records_raw_payload_encoding_not_null NOT NULL raw_payload_encoding;
ALTER TABLE source_records ADD CONSTRAINT source_records_raw_payload_hash_alg_not_null NOT NULL raw_payload_hash_alg;
ALTER TABLE source_records ADD CONSTRAINT source_records_record_status_not_null NOT NULL record_status;
ALTER TABLE source_records ADD CONSTRAINT source_records_retention_class_not_null NOT NULL retention_class;
ALTER TABLE source_records ADD CONSTRAINT source_records_schema_version_not_null NOT NULL schema_version;
ALTER TABLE source_records ADD CONSTRAINT source_records_signature_not_null NOT NULL signature;
ALTER TABLE source_records ADD CONSTRAINT source_records_source_type_not_null NOT NULL source_type;
ALTER TABLE source_records ADD CONSTRAINT source_records_source_type_version_not_null NOT NULL source_type_version;
ALTER TABLE source_records ADD CONSTRAINT source_records_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE source_records ADD CONSTRAINT source_records_validation_status_not_null NOT NULL validation_status;
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_created_at_not_null NOT NULL created_at;
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_domain_not_null NOT NULL domain;
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_id_not_null NOT NULL id;
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_idp_config_not_null NOT NULL idp_config;
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_idp_type_not_null NOT NULL idp_type;
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_is_active_not_null NOT NULL is_active;
ALTER TABLE sso_domains ADD CONSTRAINT sso_domains_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE step_up_assertions ADD CONSTRAINT step_up_assertions_action_not_null NOT NULL action;
ALTER TABLE step_up_assertions ADD CONSTRAINT step_up_assertions_created_at_not_null NOT NULL created_at;
ALTER TABLE step_up_assertions ADD CONSTRAINT step_up_assertions_expires_at_not_null NOT NULL expires_at;
ALTER TABLE step_up_assertions ADD CONSTRAINT step_up_assertions_id_not_null NOT NULL id;
ALTER TABLE step_up_assertions ADD CONSTRAINT step_up_assertions_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE step_up_assertions ADD CONSTRAINT step_up_assertions_user_id_not_null NOT NULL user_id;
ALTER TABLE submit_jobs ADD CONSTRAINT submit_jobs_job_id_not_null NOT NULL job_id;
ALTER TABLE submit_jobs ADD CONSTRAINT submit_jobs_status_not_null NOT NULL status;
ALTER TABLE tasks ADD CONSTRAINT tasks_assigned_to_not_null NOT NULL assigned_to;
ALTER TABLE tasks ADD CONSTRAINT tasks_case_id_not_null NOT NULL case_id;
ALTER TABLE tasks ADD CONSTRAINT tasks_created_at_not_null NOT NULL created_at;
ALTER TABLE tasks ADD CONSTRAINT tasks_id_not_null NOT NULL id;
ALTER TABLE tasks ADD CONSTRAINT tasks_notes_not_null NOT NULL notes;
ALTER TABLE tasks ADD CONSTRAINT tasks_status_not_null NOT NULL status;
ALTER TABLE tasks ADD CONSTRAINT tasks_task_type_not_null NOT NULL task_type;
ALTER TABLE tasks ADD CONSTRAINT tasks_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE tasks ADD CONSTRAINT tasks_updated_at_not_null NOT NULL updated_at;
ALTER TABLE tenant_keys ADD CONSTRAINT tenant_keys_created_at_not_null NOT NULL created_at;
ALTER TABLE tenant_keys ADD CONSTRAINT tenant_keys_id_not_null NOT NULL id;
ALTER TABLE tenant_keys ADD CONSTRAINT tenant_keys_key_ciphertext_not_null NOT NULL key_ciphertext;
ALTER TABLE tenant_keys ADD CONSTRAINT tenant_keys_key_purpose_not_null NOT NULL key_purpose;
ALTER TABLE tenant_keys ADD CONSTRAINT tenant_keys_kms_resource_not_null NOT NULL kms_resource;
ALTER TABLE tenant_keys ADD CONSTRAINT tenant_keys_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE tenant_notification_settings ADD CONSTRAINT tenant_notification_settings_approval_needed_email_not_null NOT NULL approval_needed_email;
ALTER TABLE tenant_notification_settings ADD CONSTRAINT tenant_notification_settings_case_opened_email_not_null NOT NULL case_opened_email;
ALTER TABLE tenant_notification_settings ADD CONSTRAINT tenant_notification_settings_overcharge_detected_email_not_null NOT NULL overcharge_detected_email;
ALTER TABLE tenant_notification_settings ADD CONSTRAINT tenant_notification_settings_recovery_executed_email_not_null NOT NULL recovery_executed_email;
ALTER TABLE tenant_notification_settings ADD CONSTRAINT tenant_notification_settings_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE tenant_notification_settings ADD CONSTRAINT tenant_notification_settings_updated_at_not_null NOT NULL updated_at;
ALTER TABLE tenants ADD CONSTRAINT tenants_created_at_not_null NOT NULL created_at;
ALTER TABLE tenants ADD CONSTRAINT tenants_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE tenants ADD CONSTRAINT tenants_display_name_not_null NOT NULL display_name;
ALTER TABLE tenants ADD CONSTRAINT tenants_id_not_null NOT NULL id;
ALTER TABLE tenants ADD CONSTRAINT tenants_slug_not_null NOT NULL slug;
ALTER TABLE tenants ADD CONSTRAINT tenants_status_not_null NOT NULL status;
ALTER TABLE tenants ADD CONSTRAINT tenants_updated_at_not_null NOT NULL updated_at;
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_auto_approve_below_not_null NOT NULL auto_approve_below;
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_created_at_not_null NOT NULL created_at;
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_currency_not_null NOT NULL currency;
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_escalate_above_not_null NOT NULL escalate_above;
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_id_not_null NOT NULL id;
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_name_not_null NOT NULL name;
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_require_approval_above_not_null NOT NULL require_approval_above;
ALTER TABLE threshold_profiles ADD CONSTRAINT threshold_profiles_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE transparency_log_commits ADD CONSTRAINT transparency_log_commits_committed_at_not_null NOT NULL committed_at;
ALTER TABLE transparency_log_commits ADD CONSTRAINT transparency_log_commits_id_not_null NOT NULL id;
ALTER TABLE transparency_log_commits ADD CONSTRAINT transparency_log_commits_leaf_count_not_null NOT NULL leaf_count;
ALTER TABLE transparency_log_commits ADD CONSTRAINT transparency_log_commits_root_hash_not_null NOT NULL root_hash;
ALTER TABLE transparency_log_commits ADD CONSTRAINT transparency_log_commits_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE transparency_log_commits ADD CONSTRAINT transparency_log_commits_witness_kid_not_null NOT NULL witness_kid;
ALTER TABLE transparency_log_commits ADD CONSTRAINT transparency_log_commits_witness_signature_not_null NOT NULL witness_signature;
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_acr_id_not_null NOT NULL acr_id;
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_appended_at_not_null NOT NULL appended_at;
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_id_not_null NOT NULL id;
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_leaf_hash_not_null NOT NULL leaf_hash;
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_log_index_not_null NOT NULL log_index;
ALTER TABLE transparency_log_entries ADD CONSTRAINT transparency_log_entries_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE users ADD CONSTRAINT users_created_at_not_null NOT NULL created_at;
ALTER TABLE users ADD CONSTRAINT users_email_not_null NOT NULL email;
ALTER TABLE users ADD CONSTRAINT users_full_name_not_null NOT NULL full_name;
ALTER TABLE users ADD CONSTRAINT users_id_not_null NOT NULL id;
ALTER TABLE users ADD CONSTRAINT users_is_active_not_null NOT NULL is_active;
ALTER TABLE users ADD CONSTRAINT users_password_hash_not_null NOT NULL password_hash;
ALTER TABLE users ADD CONSTRAINT users_role_not_null NOT NULL role;
ALTER TABLE users ADD CONSTRAINT users_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE users ADD CONSTRAINT users_title_not_null NOT NULL title;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_id_not_null NOT NULL id;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_kid_not_null NOT NULL kid;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_retention_class_not_null NOT NULL retention_class;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_rule_violations_not_null NOT NULL rule_violations;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_signature_not_null NOT NULL signature;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_source_record_id_not_null NOT NULL source_record_id;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_status_not_null NOT NULL status;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_validated_at_not_null NOT NULL validated_at;
ALTER TABLE validation_results ADD CONSTRAINT validation_results_validation_service_version_not_null NOT NULL validation_service_version;
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_created_at_not_null NOT NULL created_at;
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_id_not_null NOT NULL id;
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_rule_set_id_not_null NOT NULL rule_set_id;
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_rules_not_null NOT NULL rules;
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_source_type_not_null NOT NULL source_type;
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_status_not_null NOT NULL status;
ALTER TABLE validation_rule_sets ADD CONSTRAINT validation_rule_sets_version_not_null NOT NULL version;
ALTER TABLE variance_records ADD CONSTRAINT variance_records_case_id_not_null NOT NULL case_id;
ALTER TABLE variance_records ADD CONSTRAINT variance_records_created_at_not_null NOT NULL created_at;
ALTER TABLE variance_records ADD CONSTRAINT variance_records_id_not_null NOT NULL id;
ALTER TABLE variance_records ADD CONSTRAINT variance_records_status_not_null NOT NULL status;
ALTER TABLE variance_records ADD CONSTRAINT variance_records_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE variance_records ADD CONSTRAINT variance_records_variance_type_not_null NOT NULL variance_type;
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_config_not_null NOT NULL config;
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_created_at_not_null NOT NULL created_at;
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_id_not_null NOT NULL id;
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_ip_allowlist_not_null NOT NULL ip_allowlist;
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_is_active_not_null NOT NULL is_active;
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_signing_secret_not_null NOT NULL signing_secret;
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_source_type_not_null NOT NULL source_type;
ALTER TABLE webhook_signing_configs ADD CONSTRAINT webhook_signing_configs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_created_at_not_null NOT NULL created_at;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_id_not_null NOT NULL id;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_kid_not_null NOT NULL kid;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_signature_not_null NOT NULL signature;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_snapshot_hash_not_null NOT NULL snapshot_hash;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_snapshot_payload_not_null NOT NULL snapshot_payload;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_source_record_id_not_null NOT NULL source_record_id;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_subject_id_not_null NOT NULL subject_id;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_subject_type_not_null NOT NULL subject_type;
ALTER TABLE witness_packs ADD CONSTRAINT witness_packs_tenant_id_not_null NOT NULL tenant_id;
ALTER TABLE workspace_access_requests ADD CONSTRAINT workspace_access_requests_company_name_not_null NOT NULL company_name;
ALTER TABLE workspace_access_requests ADD CONSTRAINT workspace_access_requests_consent_not_null NOT NULL consent;
ALTER TABLE workspace_access_requests ADD CONSTRAINT workspace_access_requests_created_at_not_null NOT NULL created_at;
ALTER TABLE workspace_access_requests ADD CONSTRAINT workspace_access_requests_full_name_not_null NOT NULL full_name;
ALTER TABLE workspace_access_requests ADD CONSTRAINT workspace_access_requests_id_not_null NOT NULL id;
ALTER TABLE workspace_access_requests ADD CONSTRAINT workspace_access_requests_status_not_null NOT NULL status;
ALTER TABLE workspace_access_requests ADD CONSTRAINT workspace_access_requests_work_email_not_null NOT NULL work_email;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_amount_not_null NOT NULL amount;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_case_id_not_null NOT NULL case_id;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_created_at_not_null NOT NULL created_at;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_currency_not_null NOT NULL currency;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_data_residency_region_not_null NOT NULL data_residency_region;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_expected_recovery_id_not_null NOT NULL expected_recovery_id;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_id_not_null NOT NULL id;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_legal_hold_status_not_null NOT NULL legal_hold_status;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_policy_version_id_not_null NOT NULL policy_version_id;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_reason_code_not_null NOT NULL reason_code;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_retention_class_not_null NOT NULL retention_class;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_status_not_null NOT NULL status;
ALTER TABLE write_offs ADD CONSTRAINT write_offs_tenant_id_not_null NOT NULL tenant_id;

-- ===== INDEXES =====

CREATE INDEX idx_acr_integrity ON public.action_certification_records USING btree (tenant_id, integrity_hash) WHERE (integrity_hash IS NOT NULL);
CREATE INDEX idx_action_certification_records_live ON public.action_certification_records USING btree (tenant_id, superseded_by_id) WHERE (superseded_by_id IS NULL);
CREATE INDEX idx_action_plans_case ON public.action_plans USING btree (case_id);
CREATE INDEX idx_ambiguity_queue_tenant ON public.ambiguity_queue USING btree (tenant_id, resolved_at) WHERE (resolved_at IS NULL);
CREATE INDEX idx_api_keys_tenant ON public.api_keys USING btree (tenant_id) WHERE (revoked_at IS NULL);
CREATE INDEX idx_archive_jobs_tenant ON public.archive_jobs USING btree (tenant_id, status);
CREATE INDEX idx_authz_decisions_action_plan ON public.authorization_decisions USING btree (action_plan_id);
CREATE INDEX idx_batch_artifacts_tenant ON public.batch_artifacts USING btree (tenant_id, received_at DESC);
CREATE INDEX idx_batch_records_batch ON public.batch_records USING btree (batch_id, record_index);
CREATE INDEX idx_batch_records_outcome ON public.batch_records USING btree (batch_id, outcome);
CREATE INDEX idx_case_candidates_tenant_status ON public.case_candidates USING btree (tenant_id, status);
CREATE UNIQUE INDEX uq_cases_tenant_invoice ON public.cases USING btree (tenant_id, invoice_id) WHERE (invoice_id IS NOT NULL);
CREATE UNIQUE INDEX uq_connectors_tenant_source_type ON public.connectors USING btree (tenant_id, source_type);
CREATE INDEX idx_contract_rates_active ON public.contract_rates USING btree (tenant_id, carrier_id, rate_type) WHERE (superseded_at IS NULL);
CREATE INDEX idx_contract_rates_carrier ON public.contract_rates USING btree (tenant_id, carrier_id, effective_on);
CREATE INDEX idx_contract_rates_lane ON public.contract_rates USING btree (tenant_id, lane_hash, effective_from) WHERE (lane_hash IS NOT NULL);
CREATE INDEX idx_crypto_shred_tenant ON public.crypto_shred_requests USING btree (tenant_id, status);
CREATE INDEX idx_dedup_index_tenant ON public.dedup_index USING btree (tenant_id, external_source_ref);
CREATE INDEX idx_evidence_bundle_leaves_bundle ON public.evidence_bundle_leaves USING btree (bundle_id, bundle_version);
CREATE INDEX idx_evidence_bundles_integrity ON public.evidence_bundles USING btree (tenant_id, integrity_hash) WHERE (integrity_hash IS NOT NULL);
CREATE INDEX idx_evidence_bundles_live ON public.evidence_bundles USING btree (tenant_id, superseded_by_id) WHERE (superseded_by_id IS NULL);
CREATE UNIQUE INDEX uq_execution_envelopes_idem ON public.execution_envelopes USING btree (tenant_id, idempotency_key) WHERE (idempotency_key IS NOT NULL);
CREATE INDEX ix_expected_recoveries_tenant_case ON public.expected_recoveries USING btree (tenant_id, case_id);
CREATE UNIQUE INDEX uq_expected_recoveries_tenant_case_authdec ON public.expected_recoveries USING btree (tenant_id, case_id, authorization_decision_id) WHERE ((authorization_decision_id IS NOT NULL) AND (superseded_by IS NULL));
CREATE INDEX idx_external_responses_case ON public.external_responses USING btree (case_id);
CREATE INDEX idx_ledger_entries_live ON public.ledger_entries USING btree (tenant_id, superseded_by_id) WHERE (superseded_by_id IS NULL);
CREATE INDEX ix_ledger_entries_tenant_case ON public.ledger_entries USING btree (tenant_id, case_id);
CREATE INDEX idx_legal_hold_scope ON public.legal_hold_records USING btree (tenant_id, subject_id, status) WHERE (status = 'ACTIVE'::text);
CREATE INDEX idx_model_calls_tenant_purpose ON public.model_calls USING btree (tenant_id, purpose, created_at);
CREATE INDEX idx_outbox_unshipped ON public.outbox USING btree (created_at) WHERE (shipped_at IS NULL);
CREATE INDEX idx_prt_token_hash ON public.password_reset_tokens USING btree (token_hash) WHERE (used_at IS NULL);
CREATE INDEX idx_purge_jobs_tenant ON public.purge_jobs USING btree (tenant_id, status);
CREATE INDEX ix_recovery_instruments_tenant_case ON public.recovery_instruments USING btree (tenant_id, related_case_id);
CREATE UNIQUE INDEX uq_recovery_instruments_tenant_extref ON public.recovery_instruments USING btree (tenant_id, external_reference) WHERE (external_reference IS NOT NULL);
CREATE INDEX ix_recovery_matches_tenant_expected ON public.recovery_matches USING btree (tenant_id, expected_recovery_id);
CREATE INDEX idx_recovery_proofs_live ON public.recovery_proofs USING btree (tenant_id, superseded_by_id) WHERE (superseded_by_id IS NULL);
CREATE INDEX ix_recovery_proofs_tenant_case ON public.recovery_proofs USING btree (tenant_id, case_id);
CREATE INDEX idx_restore_jobs_tenant ON public.restore_jobs USING btree (tenant_id, status);
CREATE INDEX idx_retention_policies_tenant ON public.retention_policies USING btree (tenant_id, status);
CREATE INDEX idx_src_states_record ON public.source_record_states USING btree (source_record_id, occurred_at);
CREATE INDEX idx_source_records_correlation ON public.source_records USING btree (correlation_id) WHERE (correlation_id IS NOT NULL);
CREATE INDEX idx_source_records_dedup_key ON public.source_records USING btree (tenant_id, deduplication_key) WHERE (deduplication_key IS NOT NULL);
CREATE INDEX idx_source_records_ext_ref ON public.source_records USING btree (tenant_id, external_source_ref) WHERE (external_source_ref IS NOT NULL);
CREATE INDEX idx_source_records_integrity ON public.source_records USING btree (tenant_id, integrity_hash) WHERE (integrity_hash IS NOT NULL);
CREATE INDEX idx_source_records_legal_hold ON public.source_records USING btree (tenant_id, legal_hold_status) WHERE (legal_hold_status = 'HELD'::text);
CREATE INDEX idx_source_records_live ON public.source_records USING btree (tenant_id, superseded_by_id) WHERE (superseded_by_id IS NULL);
CREATE INDEX idx_source_records_record_status ON public.source_records USING btree (tenant_id, record_status);
CREATE INDEX idx_source_records_validation_status ON public.source_records USING btree (tenant_id, validation_status);
CREATE INDEX idx_tle_pending ON public.transparency_log_entries USING btree (tenant_id) WHERE (commit_id IS NULL);
CREATE INDEX idx_users_tenant ON public.users USING btree (tenant_id, role) WHERE (is_active = true);
CREATE INDEX idx_rule_sets_active ON public.validation_rule_sets USING btree (source_type, status) WHERE (status = 'ACTIVE'::text);
CREATE INDEX idx_webhook_signing_tenant_type ON public.webhook_signing_configs USING btree (tenant_id, source_type, is_active);
CREATE INDEX idx_witness_packs_source_record ON public.witness_packs USING btree (tenant_id, source_record_id);
CREATE INDEX ix_write_offs_tenant_case ON public.write_offs USING btree (tenant_id, case_id);

-- ===== ROW LEVEL SECURITY =====

ALTER TABLE action_certification_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_certification_records FORCE ROW LEVEL SECURITY;
ALTER TABLE action_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_intents FORCE ROW LEVEL SECURITY;
ALTER TABLE approval_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_decisions FORCE ROW LEVEL SECURITY;
ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_requests FORCE ROW LEVEL SECURITY;
ALTER TABLE approval_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_tasks FORCE ROW LEVEL SECURITY;
ALTER TABLE approval_thresholds ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_thresholds FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_chains ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_chains FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_worm_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_worm_index FORCE ROW LEVEL SECURITY;
ALTER TABLE canonical_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_invoices FORCE ROW LEVEL SECURITY;
ALTER TABLE canonical_shipments ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_shipments FORCE ROW LEVEL SECURITY;
ALTER TABLE case_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_events FORCE ROW LEVEL SECURITY;
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE cases FORCE ROW LEVEL SECURITY;
ALTER TABLE connector_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE connector_responses FORCE ROW LEVEL SECURITY;
ALTER TABLE contract_rates ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_rates FORCE ROW LEVEL SECURITY;
ALTER TABLE decision_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_proposals FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_bundles FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_items FORCE ROW LEVEL SECURITY;
ALTER TABLE execution_envelopes ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_envelopes FORCE ROW LEVEL SECURITY;
ALTER TABLE findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE findings FORCE ROW LEVEL SECURITY;
ALTER TABLE governance_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance_decisions FORCE ROW LEVEL SECURITY;
ALTER TABLE governance_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE lineage_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE lineage_records FORCE ROW LEVEL SECURITY;
ALTER TABLE model_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_calls FORCE ROW LEVEL SECURITY;
ALTER TABLE outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcomes FORCE ROW LEVEL SECURITY;
ALTER TABLE policy_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_bundles FORCE ROW LEVEL SECURITY;
ALTER TABLE reasoning_traces ENABLE ROW LEVEL SECURITY;
ALTER TABLE reasoning_traces FORCE ROW LEVEL SECURITY;
ALTER TABLE reconciliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE reconciliations FORCE ROW LEVEL SECURITY;
ALTER TABLE source_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_records FORCE ROW LEVEL SECURITY;
ALTER TABLE tenant_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE transparency_log_commits ENABLE ROW LEVEL SECURITY;
ALTER TABLE transparency_log_commits FORCE ROW LEVEL SECURITY;
ALTER TABLE transparency_log_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE transparency_log_entries FORCE ROW LEVEL SECURITY;
ALTER TABLE validation_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_results FORCE ROW LEVEL SECURITY;
ALTER TABLE variance_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE variance_records FORCE ROW LEVEL SECURITY;
ALTER TABLE witness_packs ENABLE ROW LEVEL SECURITY;
ALTER TABLE witness_packs FORCE ROW LEVEL SECURITY;
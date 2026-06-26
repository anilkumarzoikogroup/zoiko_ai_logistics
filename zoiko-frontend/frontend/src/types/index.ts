// Types matching the Zoiko backend DB schema (Phases 0-4)

// Case FSM states (spec §7.5 — aligned with implementation plan)
export type CaseState =
  | "NEW"               // Case opened after invoice validation
  | "EVIDENCE_PENDING"  // Evidence bundle being collected
  | "FINDING_GENERATED" // AI reasoned; ready for analyst proposal
  | "APPROVAL_PENDING"  // Analyst proposed; awaiting manager approval
  | "EXECUTION_READY"   // Manager approved; governance token issued (15-min TTL)
  | "DISPATCHED"        // 8-gate execution gateway passed; credit memo sent
  | "OUTCOME_RECORDED"  // Reconciliation complete; GL journal recorded
  | "CLOSED"            // ACR locked in WORM; case archived
  | "ABORTED";          // Rejected at any stage

export type ValidationOutcome = "PASS" | "FAIL";

export type TokenStatus = "ACTIVE" | "CONSUMED" | "EXPIRED" | "REVOKED";

export type VarianceStatus = "OPEN" | "RESOLVED" | "WAIVED";

export type VarianceType =
  | "AMOUNT_MISMATCH"
  | "CARRIER_MISMATCH"
  | "CURRENCY_MISMATCH"
  | "OVERCHARGE_DELTA"
  | "OTHER";

export interface Tenant {
  id: string;
  slug: string;
  name: string;
  created_at: string;
}

export interface SourceRecord {
  id: string;
  tenant_id: string;
  canonical_hash: string;
  signature: string;
  key_id: string;
  received_at: string;
  payload_preview?: Record<string, unknown>;
}

export interface ValidationResult {
  id: string;
  case_id: string;
  outcome: ValidationOutcome;
  diff: number;
  currency: string;
  reason: string;
  invoice_amount: number;
  contract_amount: number;
  validated_at: string;
}

export interface CanonicalInvoice {
  id: string;
  tenant_id: string;
  shipment_ref: string;
  carrier: string;
  amount: number;
  currency: string;
  canonical_hash: string;
  signature: string;
  signed_at: string;
}

export interface Case {
  id: string;
  tenant_id: string;
  state: CaseState;
  carrier: string;
  shipment_ref: string;
  amount: number;
  currency: string;
  diff: number;
  confidence?: number;
  opened_at: string;
  updated_at: string;
  duplicate?: boolean;
  deduplication_outcome?: string;
}

// SC-002 — carrier claim case states (parallel to CaseState, no FK overlap with invoices)
export type ClaimState =
  | "NEW"
  | "EVIDENCE_PENDING"
  | "FINDING_GENERATED"
  | "APPROVAL_PENDING"
  | "EXECUTION_READY"
  | "DISPATCHED"
  | "OUTCOME_RECORDED"
  | "CLOSED"
  | "ABORTED";

export interface Claim {
  id: string;
  tenant_id: string;
  state: ClaimState;
  case_type: "CARRIER_CLAIM";
  carrier: string;
  shipment_ref: string;   // claim_reference
  claim_type: string;
  amount: number;
  currency: string;
  diff: number;
  confidence?: number;
  opened_at: string;
  updated_at: string;
  duplicate?: boolean;
  deduplication_outcome?: string;
  negotiation_status?: string;   // OPEN | SUBMITTED | UNDER_CARRIER_REVIEW | COUNTERED | PARTIALLY_ACCEPTED | ACCEPTED | REJECTED | WITHDRAWN | CLOSED
  approved_amount?: number | null;
}

export interface NegotiationRound {
  round: number;
  action: string;         // COUNTER | ACCEPT | PARTIALLY_ACCEPT | REJECT
  from_status: string;
  to_status: string;
  approved_amount: number | null;
  note: string;
  occurred_at: string;
  actor_sub?: string;
}


export interface CaseEvent {
  id: string;
  case_id: string;
  from_state: CaseState | null;
  to_state: CaseState;
  actor: string;
  reason: string;
  created_at: string;
  payload?: Record<string, unknown> | string | null;
}

export interface EvidenceItem {
  id: string;
  bundle_id: string;
  item_type: "BOL" | "RATE_SHEET" | "INVOICE" | "EMAIL" | "OTHER";
  leaf_hash: string;
  added_at: string;
}

export interface EvidenceBundle {
  id: string;
  case_id: string;
  merkle_root: string;
  item_count: number;
  created_at: string;
  completeness_status: "INCOMPLETE" | "COMPLETE";
  items?: EvidenceItem[];
}

export interface Finding {
  id: string;
  case_id: string;
  confidence: number;
  trace: Record<string, { confidence: number; weight: number }>;
  finding_hash: string;
  created_at: string;
  risk_level?:    "HIGH" | "MEDIUM" | "LOW";
  ai_confidence?: number;
  ai_reasoning?:  string;
}

export interface DecisionProposal {
  id: string;
  case_id: string;
  action: "EXECUTE_CREDIT_MEMO" | "DISMISS" | "ESCALATE";
  amount: number;
  currency: string;
  proposed_by: string;
  proposed_at: string;
}

export interface ApprovalTask {
  id: string;
  case_id: string;
  proposer_sub: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  created_at: string;
}

export interface GovernanceDecision {
  id: string;
  case_id: string;
  proposer_sub: string;
  actor_sub: string;
  decision: "EXECUTION_READY" | "ABORTED";
  decision_hash: string;
  decided_at: string;
}

export interface GovernanceToken {
  id: string;
  case_id: string;
  tenant_id: string;
  action: string;
  amount: number;
  currency: string;
  tenant_binding: string;
  exp: string;
  status: TokenStatus;
  signature: string;
  key_id: string;
  issued_at: string;
}

export interface VarianceRecord {
  id: string;
  case_id: string;
  variance_type: VarianceType;
  expected_value: number;
  actual_value: number;
  delta: number;
  status: VarianceStatus;
  resolved_by?: string;
  resolved_at?: string;
  created_at: string;
}

export interface ACRBundle {
  id: string;
  case_id: string;
  tenant_id: string;
  merkle_root: string;
  acr_hash: string;
  signature: string;
  kid: string;
  issued_at: string;
  is_locked: boolean;
  artifact_count?: number;
}

export interface RecoveryProof {
  proof_id: string;
  tenant_id: string;
  case_id: string;
  claimed_amount: number;
  currency: string;
  expected_recovery_ids: string[];
  recovery_instrument_ids: string[];
  recovery_match_ids: string[];
  ledger_entry_ids: string[];
  total_expected: number;
  total_recovered: number;
  total_unrecovered: number;
  recovery_status: string;
  ledger_status: string;
  acr_ready: boolean;
  superseded_by?: string | null;
  created_at: string;
}

export interface ExpectedRecovery {
  expected_recovery_id: string;
  case_id: string;
  tenant_id: string;
  expected_amount: number;
  currency: string;
  expected_recovery_method: string;
  status: string;
  created_at: string;
}

export interface RecoveryInstrument {
  recovery_instrument_id: string;
  tenant_id: string;
  instrument_type: string;
  instrument_amount: number;
  currency: string;
  status: string;
  related_case_id?: string | null;
  created_by: string;
  created_at: string;
  payment_confirmed?: boolean;
  payment_confirmed_at?: string | null;
  payment_confirmed_ref?: string | null;
}

export interface RecoveryMatch {
  match_id: string;
  expected_recovery_id: string;
  recovery_instrument_id: string;
  tenant_id: string;
  match_tier?: number | null;
  match_method?: string | null;
  match_confidence?: number | null;
  matched_amount: number;
  expected_amount: number;
  variance: number;
  currency: string;
  allocation_status: string;
  matched_by: string;
  matched_at: string;
}

export interface RecoveryException {
  exception_type: string;
  tenant_id: string;
  case_id: string;
  expected_recovery_id: string;
  recovery_match_id?: string | null;
  status: string;
  amount: number;
  currency: string;
  age_days: number;
  detail: string;
  detected_at: string;
}

export interface ReconcileResult {
  reconciliation_id: string;
  envelope_id: string;
  status: string;
  delta: number;
  reconciled_at: string;
}

export interface ExecutionResult {
  envelope_id: string;
  case_id: string;
  token_id: string;
  gates_passed: number;
  status: string;
  dispatched_at: string;
}

export interface KafkaEvent {
  topic: string;
  key: string;
  payload: Record<string, unknown>;
  published_at: string;
}

export interface DashboardStats {
  total_cases: number;
  pending_approval: number;
  approved: number;
  total_recovered: number;
  avg_confidence: number;
}

// ── C07 — Data Governance types ───────────────────────────────────────────────

export type LegalHoldStatus = "ACTIVE" | "RELEASED";
export type CryptoShredStatus = "PENDING" | "COMPLETED" | "BLOCKED" | "VERIFIED";
export type RestoreJobStatus =
  | "PENDING"
  | "VERIFICATION_PENDING"
  | "VERIFICATION_PASSED"
  | "VERIFICATION_FAILED"
  | "APPROVED_FOR_USE"
  | "REJECTED";
export type ArchiveJobStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED";
export type PurgeJobStatus = "PENDING" | "APPROVED" | "EXECUTING" | "COMPLETED" | "BLOCKED" | "FAILED";

export interface LegalHold {
  id: string;
  tenant_id: string;
  hold_scope: string;
  scope_id: string;
  reason_code: string;
  status: LegalHoldStatus;
  requested_by: string;
  approved_by?: string;
  effective_from?: string;
  released_by?: string;
  released_at?: string;
  created_at: string;
}

export interface RetentionPolicy {
  id: string;
  tenant_id: string;
  policy_name: string;
  data_class: string;
  retention_class: string;
  retention_days: number;
  archive_after_days?: number;
  purge_after_days?: number;
  created_by: string;
  created_at: string;
}

export interface RetentionAssignment {
  record_id: string;
  record_type: string;
  policy_id: string;
  retention_until?: string;
  archive_after?: string;
  purge_after?: string;
  assigned_at: string;
}

export interface CryptoShredRequest {
  id: string;
  tenant_id: string;
  subject_ref: string;
  affected_key_ids: string[];
  affected_record_ids: string[];
  status: CryptoShredStatus;
  legal_hold_blocked: boolean;
  requested_by: string;
  completed_at?: string;
  created_at: string;
}

export interface CryptoShredVerification {
  crypto_shred_id: string;
  verified: boolean;
  shredded_count: number;
  unshredded_ids: string[];
}

export interface RestoreJob {
  id: string;
  tenant_id: string;
  restore_type: string;
  restored_scope: string;
  status: RestoreJobStatus;
  requested_by: string;
  approved_by?: string;
  approved_at?: string;
  created_at: string;
}

export interface RestoreVerification {
  id: string;
  restore_job_id: string;
  tenant_id: string;
  verification_status: "PENDING" | "PASSED" | "FAILED";
  source_records_verified: boolean;
  evidence_chain_verified: boolean;
  acr_verified: boolean;
  ledger_continuity_verified: boolean;
  tenant_isolation_verified: boolean;
  residency_verified: boolean;
  permissions_verified: boolean;
  legal_hold_verified: boolean;
  indexes_rebuilt: boolean;
  projection_consistency_verified: boolean;
  created_at: string;
}

export interface ArchiveJob {
  id: string;
  tenant_id: string;
  archive_scope: string;
  record_ids: string[];
  retention_policy_id?: string;
  status: ArchiveJobStatus;
  integrity_metadata?: Record<string, unknown>;
  requested_by: string;
  created_at: string;
}

export interface PurgeJob {
  id: string;
  tenant_id: string;
  purge_scope: string;
  record_count: number;
  retention_policy_id?: string;
  status: PurgeJobStatus;
  legal_hold_blocked: boolean;
  approved_by?: string;
  approved_at?: string;
  requested_by: string;
  created_at: string;
}

export interface ObservabilityMetrics {
  tenant_id: string;
  computed_at: string;
  records_by_retention_class: Record<string, number>;
  records_approaching_expiry: number;
  records_blocked_by_legal_hold: number;
  archive_jobs: Record<string, number>;
  archive_restore_latency_avg_seconds: number;
  restore_verification_failures: number;
  evidence_chain_verification_failures: number;
  acr_verification_failures_after_restore: number;
  purge_jobs: Record<string, number>;
  crypto_shred_requests: Record<string, number>;
  cross_region_access_attempts: number;
  residency_violations_detected: number;
  backup_restore_test_results: Record<string, unknown>;
  payload_access_events: number;
  legal_hold_active_by_scope: Record<string, number>;
}

export interface ObservabilityAlert {
  alert: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  count: number;
  detail: string;
}

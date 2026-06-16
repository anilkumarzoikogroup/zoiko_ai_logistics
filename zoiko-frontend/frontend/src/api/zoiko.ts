import { api, api3, api4, USE_MOCK } from "./client";
import * as mocks from "@/mocks/fixtures";
import type {
  Case, CanonicalInvoice, ValidationResult, EvidenceBundle, Finding,
  DecisionProposal, GovernanceToken, GovernanceDecision, CaseEvent,
  KafkaEvent, DashboardStats, SourceRecord, VarianceRecord, ACRBundle,
  ExecutionResult, RecoveryProof,
  ExpectedRecovery, RecoveryInstrument, RecoveryMatch, RecoveryException, ReconcileResult,
  LegalHold, RetentionPolicy, RetentionAssignment,
  CryptoShredRequest, CryptoShredVerification,
  RestoreJob, RestoreVerification,
  ArchiveJob, PurgeJob,
  ObservabilityMetrics, ObservabilityAlert,
} from "@/types";

// Simulates network latency for mock mode so loading states are visible
const delay = (ms = 250) => new Promise(r => setTimeout(r, ms));

// ── Auth types ────────────────────────────────────────────────────────────────
export interface LoginResponse {
  token:      string;
  tenant_id:  string;
  role:       string;
  full_name:  string;
  email:      string;
  expires_in: number;
}

export interface RegisterRequest {
  email:     string;
  password?: string;
  full_name: string;
  role:      "analyst" | "manager" | "admin";
}

export interface UserItem {
  user_id:    string;
  email:      string;
  full_name:  string;
  role:       string;
  is_active:  boolean;
  created_at: string;
}

export interface ApiKeyItem {
  id:           string;
  name:         string;
  key_prefix:   string;
  scopes:       string;
  created_at:   string;
  last_used_at: string | null;
  revoked:      boolean;
}

export interface CreateApiKeyResponse {
  id:         string;
  name:       string;
  key:        string;
  key_prefix: string;
  scopes:     string;
  created_at: string;
}

export interface NotificationSettings {
  case_opened_email:         boolean;
  overcharge_detected_email: boolean;
  approval_needed_email:     boolean;
  recovery_executed_email:   boolean;
}

export interface UsageSummary {
  plan:             string;
  member_since:     string;
  total_cases:      number;
  cases_this_month: number;
  total_recovered:  number;
  active_users:     number;
}

export const zoikoApi = {
  // ---------- Auth ----------
  async login(email: string, password: string): Promise<LoginResponse> {
    const { data } = await api.post<LoginResponse>("/auth/login", { email, password });
    return data;
  },

  async registerUser(req: RegisterRequest): Promise<UserItem> {
    const { data } = await api.post<UserItem>("/auth/register", req);
    return data;
  },

  async listUsers(): Promise<UserItem[]> {
    const { data } = await api.get<{ users: UserItem[] }>("/auth/users");
    return data.users;
  },

  // ---------- API Keys ----------
  async listApiKeys(): Promise<ApiKeyItem[]> {
    const { data } = await api.get<{ api_keys: ApiKeyItem[] }>("/api-keys");
    return data.api_keys;
  },

  async createApiKey(name: string, scopes = "read:*"): Promise<CreateApiKeyResponse> {
    const { data } = await api.post<CreateApiKeyResponse>("/api-keys", { name, scopes });
    return data;
  },

  async revokeApiKey(id: string): Promise<void> {
    await api.delete(`/api-keys/${id}`);
  },

  // ---------- Notification Settings ----------
  async getNotificationSettings(): Promise<NotificationSettings> {
    const { data } = await api.get<NotificationSettings>("/settings/notifications");
    return data;
  },

  async updateNotificationSettings(settings: NotificationSettings): Promise<NotificationSettings> {
    const { data } = await api.put<NotificationSettings>("/settings/notifications", settings);
    return data;
  },

  // ---------- Billing / Usage ----------
  async getUsageSummary(): Promise<UsageSummary> {
    const { data } = await api.get<UsageSummary>("/billing/usage");
    return data;
  },

  // ---------- Dashboard ----------
  async getStats(): Promise<DashboardStats> {
    if (USE_MOCK) { await delay(); return mocks.mockStats; }
    const { data } = await api.get<DashboardStats>("/dashboard/stats");
    return data;
  },

  // ---------- Cases ----------
  async listCases(filters?: { state?: string; page?: number; page_size?: number }): Promise<Case[]> {
    if (USE_MOCK) {
      await delay();
      return filters?.state
        ? mocks.mockCases.filter(c => c.state === filters.state)
        : mocks.mockCases;
    }
    const { data } = await api.get<{ cases: Case[]; total: number; page: number; pages: number } | Case[]>(
      "/cases", { params: filters }
    );
    // Handle both paginated response and legacy array response
    return Array.isArray(data) ? data : data.cases;
  },

  async listCasesPaged(filters?: { state?: string; page?: number; page_size?: number }): Promise<{ cases: Case[]; total: number; page: number; pages: number }> {
    if (USE_MOCK) {
      await delay();
      const cases = filters?.state ? mocks.mockCases.filter(c => c.state === filters.state) : mocks.mockCases;
      return { cases, total: cases.length, page: 1, pages: 1 };
    }
    const { data } = await api.get<{ cases: Case[]; total: number; page: number; pages: number }>("/cases", { params: filters });
    return data;
  },

  async getCase(id: string): Promise<Case> {
    if (USE_MOCK) {
      await delay();
      const c = mocks.mockCases.find(x => x.id === id);
      if (!c) throw new Error("Case not found");
      return c;
    }
    const { data } = await api.get<Case>(`/cases/${id}`);
    return data;
  },

  async getCaseEvents(caseId: string): Promise<CaseEvent[]> {
    if (USE_MOCK) {
      await delay();
      return mocks.mockEvents.filter(e => e.case_id === caseId);
    }
    const { data } = await api.get<CaseEvent[]>(`/cases/${caseId}/events`);
    return data;
  },

  async createCase(payload: { invoice_number?: string; invoice_date?: string; transport_mode?: string; equipment_type?: string; shipper_reference?: string; charge_lines?: {description:string;amount:number;type:string}[]; carrier: string; route: string; amount: number; currency: string }): Promise<Case> {
    if (USE_MOCK) {
      await delay(500);
      const CONTRACT_BASE: Record<string, number> = {
        "BlueDart": 8000, "Delhivery": 7500, "FedEx India": 9200,
        "DTDC": 6500, "Ekart": 7000, "UPS India": 10500, "V Express": 50000, "Other": 7000,
      };
      const contractAmt = CONTRACT_BASE[payload.carrier] ?? Math.round(payload.amount * 0.72);
      const diff = Math.max(200, payload.amount - contractAmt);
      const confidence = parseFloat((0.72 + Math.random() * 0.25).toFixed(2));
      const now = new Date().toISOString();
      const newCase: Case = {
        id: `case_${Date.now().toString().slice(-6)}`,
        tenant_id: "amazon-india",
        carrier: payload.carrier,
        shipment_ref: payload.route,
        amount: payload.amount,
        currency: payload.currency,
        diff,
        confidence,
        state: "FINDING_GENERATED",
        opened_at: now,
        updated_at: now,
      };
      mocks.mockCases.unshift(newCase);
      return newCase;
    }
    // Step 1: POST /cases/submit-async → returns job_id immediately (<1s).
    // This replaces the old 25s blocking call that NAT/firewalls would drop.
    const { data: job } = await api.post<{ job_id: string }>(
      "/cases/submit-async", payload, { timeout: 10000 }
    );
    // Step 2: Poll every 2s until the pipeline finishes (max 90s).
    for (let i = 0; i < 45; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const { data: s } = await api.get<{ status: string; case: Case | null; error: string | null }>(
        `/cases/submit-status/${job.job_id}`, { timeout: 8000 }
      );
      if (s.status === "done" && s.case) return s.case;
      if (s.status === "error") throw new Error(s.error || "Pipeline failed");
    }
    throw new Error("Timed out waiting for case (90s)");
  },

  // ---------- Phase 2 artifacts ----------
  async getSourceRecords(): Promise<SourceRecord[]> {
    if (USE_MOCK) { await delay(); return mocks.mockSourceRecords; }
    const { data } = await api.get<SourceRecord[]>("/ingestion/source-records");
    return data;
  },

  async getValidationForCase(caseId: string): Promise<ValidationResult> {
    if (USE_MOCK) { await delay(); return mocks.mockValidation; }
    const { data } = await api.get<ValidationResult>(`/cases/${caseId}/validation`);
    return data;
  },

  async getCanonicalInvoice(caseId: string): Promise<CanonicalInvoice> {
    if (USE_MOCK) { await delay(); return mocks.mockCanonicalInvoice; }
    const { data } = await api.get<CanonicalInvoice>(`/cases/${caseId}/canonical-invoice`);
    return data;
  },

  // ---------- Phase 3 artifacts ----------
  async getEvidence(caseId: string): Promise<EvidenceBundle> {
    if (USE_MOCK) { await delay(); return mocks.mockEvidenceBundle; }
    const { data } = await api.get<EvidenceBundle>(`/cases/${caseId}/evidence`);
    return data;
  },

  async sealBundle(caseId: string): Promise<{ bundle_id: string; completeness_status: string }> {
    if (USE_MOCK) { await delay(400); return { bundle_id: "bnd_mock", completeness_status: "COMPLETE" }; }
    const { data } = await api3.post(`/evidence/${caseId}/bundle/seal`);
    return data;
  },

  async getFinding(caseId: string): Promise<Finding> {
    if (USE_MOCK) { await delay(); return mocks.mockFinding; }
    const { data } = await api.get<Finding>(`/cases/${caseId}/finding`);
    return data;
  },

  async getProposal(caseId: string): Promise<DecisionProposal> {
    if (USE_MOCK) { await delay(); return mocks.mockProposal; }
    const { data } = await api.get<DecisionProposal>(`/cases/${caseId}/proposal`);
    return data;
  },

  async proposeRecovery(caseId: string, payload: { action: string; amount: number; currency: string }): Promise<DecisionProposal> {
    if (USE_MOCK) {
      await delay(500);
      const c = mocks.mockCases.find(x => x.id === caseId);
      if (c) { c.state = "APPROVAL_PENDING"; c.updated_at = new Date().toISOString(); }
      return { ...mocks.mockProposal, case_id: caseId, ...payload } as DecisionProposal;
    }
    const { data } = await api.post<DecisionProposal>(`/cases/${caseId}/proposal`, payload);
    return data;
  },

  async approveDecision(caseId: string, payload: { decision: "EXECUTION_READY" | "ABORTED"; note?: string }): Promise<GovernanceDecision> {
    if (USE_MOCK) {
      await delay(700);
      const c = mocks.mockCases.find(x => x.id === caseId);
      if (c) {
        c.state = payload.decision === "EXECUTION_READY" ? "EXECUTION_READY" : "ABORTED";
        c.updated_at = new Date().toISOString();
      }
      if (payload.decision === "EXECUTION_READY") {
        const existing = mocks.mockTokens.find(t => t.case_id === caseId);
        if (!existing) {
          mocks.mockTokens.push({
            id: `tok_${Date.now()}`, case_id: caseId, tenant_id: "amazon-india",
            action: "EXECUTE_CREDIT_MEMO", amount: c?.diff ?? 4500, currency: c?.currency ?? "INR",
            tenant_binding: mocks.rndHash(), exp: new Date(Date.now() + 15 * 60_000).toISOString(),
            status: "ACTIVE", signature: mocks.rndHash(128), key_id: "amazon-india-signing-2025-01",
            issued_at: new Date().toISOString(),
          });
        }
      }
      return {
        id: `dec_${Date.now()}`, case_id: caseId, proposer_sub: "user_analyst_01",
        actor_sub: "user_manager_01", decision: payload.decision,
        decision_hash: mocks.rndHash(), decided_at: new Date().toISOString(),
      };
    }
    const { data } = await api.post<GovernanceDecision>(`/cases/${caseId}/decide`, payload);
    return data;
  },

  async listTokens(filters?: { status?: string }): Promise<GovernanceToken[]> {
    if (USE_MOCK) {
      await delay();
      return filters?.status ? mocks.mockTokens.filter(t => t.status === filters.status) : mocks.mockTokens;
    }
    const { data } = await api.get<GovernanceToken[]>("/tokens", { params: filters });
    return data;
  },

  async getTokenForCase(caseId: string): Promise<GovernanceToken | null> {
    if (USE_MOCK) { await delay(); return mocks.mockTokens.find(t => t.case_id === caseId) ?? null; }
    const { data } = await api.get<GovernanceToken | null>(`/cases/${caseId}/token`);
    return data;
  },

  // ---------- Phase 4 — Execution ----------
  async executeRecovery(tokenId: string, caseId: string, amount: number, currency: string): Promise<ExecutionResult> {
    if (USE_MOCK) {
      await delay(1200);
      const c = mocks.mockCases.find(x => x.id === caseId);
      if (c) { c.state = "DISPATCHED"; c.updated_at = new Date().toISOString(); }
      return { envelope_id: `env_${Date.now()}`, case_id: caseId, token_id: tokenId, gates_passed: 8, status: "DISPATCHED", dispatched_at: new Date().toISOString() };
    }
    // Uses Phase 2 gateway (port 8000) — no separate Phase 4 service needed
    const { data } = await api.post<ExecutionResult>("/execute", { token_id: tokenId, case_id: caseId, amount, currency });
    return data;
  },

  // ---------- Phase 4 — Variances ----------
  async listVariances(caseId: string): Promise<VarianceRecord[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api.get<VarianceRecord[]>(`/cases/${caseId}/variances`);
    return data;
  },

  async resolveVariance(caseId: string, varianceId: string, action: "RESOLVE" | "WAIVE"): Promise<VarianceRecord> {
    if (USE_MOCK) { await delay(300); return {} as VarianceRecord; }
    const { data } = await api.patch<VarianceRecord>(`/cases/${caseId}/variances/${varianceId}/resolve`, { action });
    return data;
  },

  // ---------- Phase 4 — ACR ----------
  async getAcr(caseId: string): Promise<ACRBundle | null> {
    if (USE_MOCK) { await delay(); return null; }
    try {
      const { data } = await api.get<ACRBundle>(`/cases/${caseId}/acr`);
      return data;
    } catch {
      return null;
    }
  },

  async downloadAcr(caseId: string): Promise<Blob> {
    if (USE_MOCK) { await delay(800); return new Blob(["mock acr zip"], { type: "application/zip" }); }
    const response = await api.get(`/cases/${caseId}/acr/download`, { responseType: "blob" });
    return response.data as Blob;
  },

  // ---------- Phase 6 — Recovery ----------
  async getLatestRecoveryProof(caseId: string): Promise<RecoveryProof | null> {
    if (USE_MOCK) { await delay(); return null; }
    try {
      const { data } = await api4.get<RecoveryProof>(`/recovery/proofs:latest`, { params: { case_id: caseId } });
      return data;
    } catch {
      return null;
    }
  },

  async listRecoveryProofsByCase(caseId: string): Promise<RecoveryProof[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<RecoveryProof[]>(`/recovery/proofs:by-case`, { params: { case_id: caseId } });
    return data;
  },

  async generateRecoveryProof(caseId: string): Promise<RecoveryProof> {
    if (USE_MOCK) { await delay(800); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<RecoveryProof>("/recovery/proofs", { case_id: caseId });
    return data;
  },

  async listExpectedRecoveriesByCase(caseId: string): Promise<ExpectedRecovery[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<ExpectedRecovery[]>("/recovery/expected:by-case", { params: { case_id: caseId } });
    return data;
  },

  async createExpectedRecovery(payload: {
    case_id: string;
    expected_amount: number;
    currency?: string;
    expected_recovery_method?: string;
    counterparty_type?: string;
    counterparty_id?: string;
    expected_external_invoice_ref?: string;
    authorization_decision_id?: string;
  }): Promise<ExpectedRecovery> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<ExpectedRecovery>("/recovery/expected", payload);
    return data;
  },

  async listRecoveryInstrumentsByCase(caseId: string): Promise<RecoveryInstrument[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<RecoveryInstrument[]>("/recovery/instruments:by-case", { params: { case_id: caseId } });
    return data;
  },

  async createRecoveryInstrument(payload: {
    instrument_type: string;
    instrument_amount: number;
    currency?: string;
    counterparty_type?: string;
    counterparty_id?: string;
    related_case_id?: string;
    external_reference?: string;
    related_external_invoice_ref?: string;
    instrument_date?: string;
  }): Promise<RecoveryInstrument> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<RecoveryInstrument>("/recovery/instruments", payload);
    return data;
  },

  async listRecoveryMatchesByCase(caseId: string): Promise<RecoveryMatch[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<RecoveryMatch[]>("/recovery/matches:by-case", { params: { case_id: caseId } });
    return data;
  },

  async createRecoveryMatch(expectedRecoveryId: string): Promise<RecoveryMatch> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<RecoveryMatch>("/recovery/match", { expected_recovery_id: expectedRecoveryId });
    return data;
  },

  async reverseRecoveryMatch(matchId: string, reason = ""): Promise<RecoveryMatch> {
    if (USE_MOCK) { await delay(500); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<RecoveryMatch>(`/recovery/matches/${matchId}/reverse`, { reason });
    return data;
  },

  async listRecoveryExceptions(caseId?: string, stuckAfterDays = 7): Promise<RecoveryException[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api4.get<RecoveryException[]>("/recovery/exceptions", {
      params: { case_id: caseId, stuck_after_days: stuckAfterDays },
    });
    return data;
  },

  // ---------- Phase 4 — Reconciliation ----------
  async reconcileEnvelope(envelopeId: string, actorSub: string): Promise<ReconcileResult> {
    if (USE_MOCK) { await delay(800); throw new Error("Not available in mock mode"); }
    const { data } = await api4.post<ReconcileResult>("/reconcile", { envelope_id: envelopeId, actor_sub: actorSub });
    return data;
  },

  // ---------- Contract rates ----------
  async listContractRates(): Promise<{ id: string; carrier: string; rate_type: string; rate_value: number; currency: string; effective_on: string; expires_on: string | null }[]> {
    if (USE_MOCK) {
      await delay();
      return [
        { id: "cr1", carrier: "BlueDart",   rate_type: "FUEL_CHARGE", rate_value: 8000,  currency: "INR", effective_on: "2025-01-01", expires_on: null },
        { id: "cr2", carrier: "Delhivery",  rate_type: "FUEL_CHARGE", rate_value: 7500,  currency: "INR", effective_on: "2025-01-01", expires_on: null },
        { id: "cr3", carrier: "FedEx",      rate_type: "FUEL_CHARGE", rate_value: 9200,  currency: "INR", effective_on: "2025-01-01", expires_on: null },
        { id: "cr4", carrier: "DTDC",       rate_type: "FUEL_CHARGE", rate_value: 6500,  currency: "INR", effective_on: "2025-01-01", expires_on: "2025-12-31" },
        { id: "cr5", carrier: "Ekart",      rate_type: "FUEL_CHARGE", rate_value: 7000,  currency: "INR", effective_on: "2025-01-01", expires_on: null },
      ];
    }
    const { data } = await api.get("/contract-rates");
    return data;
  },

  async createContractRate(payload: {
    carrier_id:   string;
    rate_type:    string;
    rate_value:   number;
    currency:     string;
    effective_on: string;
    expires_on?:  string;
  }): Promise<{ id: string }> {
    if (USE_MOCK) { await delay(400); return { id: `cr_${Date.now()}` }; }
    const { data } = await api.post("/contract-rates", payload);
    return data;
  },

  async deleteContractRate(id: string): Promise<void> {
    if (USE_MOCK) { await delay(300); return; }
    await api.delete(`/contract-rates/${id}`);
  },

  // ---------- Phase 1 — security substrate ----------
  async listKafkaEvents(): Promise<KafkaEvent[]> {
    if (USE_MOCK) { await delay(); return mocks.mockKafkaEvents; }
    const { data } = await api.get<KafkaEvent[]>("/kafka/events");
    return data;
  },

  // ---------- Admin ----------
  async getDbStats(): Promise<{ table: string; rows: number }[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api.get<{ table: string; rows: number }[]>("/admin/db-stats");
    return data;
  },

  // ---------- Profile ----------
  async getProfile(): Promise<{ full_name: string; email: string; role: string; title: string; is_active: boolean; created_at: string }> {
    const { data } = await api.get("/auth/me");
    return data;
  },
  async updateProfile(payload: { title?: string; full_name?: string }): Promise<void> {
    await api.put("/auth/me", payload);
  },

  // ---------- Tenant info ----------
  async getTenant(): Promise<{ display_name: string; slug: string; address: string; city: string; state: string; pincode: string; phone: string; email: string; status: string }> {
    const { data } = await api.get("/auth/tenant");
    return data;
  },
  async updateTenant(payload: { address?: string; city?: string; state?: string; pincode?: string; phone?: string; email?: string }): Promise<void> {
    await api.put("/auth/tenant", payload);
  },

  // ---------- Carriers ----------
  async listCarriers(): Promise<CarrierItem[]> {
    const { data } = await api.get<CarrierItem[]>("/carriers");
    return data;
  },
  async createCarrier(payload: { name: string; email?: string; address?: string; contact_person?: string; contact_phone?: string; cc_emails?: string }): Promise<{ id: string; name: string }> {
    const { data } = await api.post("/carriers", payload);
    return data;
  },
  async updateCarrier(id: string, payload: { name?: string; email?: string; address?: string; contact_person?: string; contact_phone?: string; cc_emails?: string }): Promise<void> {
    await api.put(`/carriers/${id}`, payload);
  },
  async deleteCarrier(id: string): Promise<void> {
    await api.delete(`/carriers/${id}`);
  },

  // ---------- Tenant management ----------
  async listTenants(): Promise<TenantItem[]> {
    if (USE_MOCK) { await delay(); return []; }
    const { data } = await api.get<{ tenants: TenantItem[]; total: number }>("/admin/tenants");
    return data.tenants;
  },

  async createTenant(req: TenantCreateRequest): Promise<TenantCreateResponse> {
    if (USE_MOCK) {
      await delay(600);
      return { tenant_id: `t_${Date.now()}`, display_name: req.display_name, slug: req.slug,
               status: "ACTIVE", admin_user_id: `u_${Date.now()}`, admin_email: req.admin_email,
               created_at: new Date().toISOString() };
    }
    const { data } = await api.post<TenantCreateResponse>("/admin/tenants", req);
    return data;
  },

  // ── C07 — Observability ──────────────────────────────────────────────────────
  async getObservabilityMetrics(): Promise<ObservabilityMetrics> {
    const { data } = await api.get<ObservabilityMetrics>("/data/observability/metrics");
    return data;
  },

  async getObservabilityAlerts(): Promise<ObservabilityAlert[]> {
    const { data } = await api.get<ObservabilityAlert[]>("/data/observability/alerts");
    return data;
  },

  // ── C07 — Legal Holds ────────────────────────────────────────────────────────
  async createLegalHold(payload: { hold_scope: string; scope_id: string; reason_code: string; approved_by?: string }): Promise<LegalHold> {
    const { data } = await api.post<LegalHold>("/legal-holds", payload);
    return data;
  },

  async getLegalHold(id: string): Promise<LegalHold> {
    const { data } = await api.get<LegalHold>(`/legal-holds/${id}`);
    return data;
  },

  async releaseLegalHold(id: string, released_by: string): Promise<LegalHold> {
    const { data } = await api.post<LegalHold>(`/legal-holds/${id}/release`, { released_by });
    return data;
  },

  async legalHoldsByScope(scope_id: string): Promise<LegalHold[]> {
    const { data } = await api.get<LegalHold[]>("/legal-holds:by-scope", { params: { scope_id } });
    return data;
  },

  // ── C07 — Retention ─────────────────────────────────────────────────────────
  async createRetentionPolicy(payload: { policy_name: string; data_class: string; retention_class: string; retention_days: number; archive_after_days?: number; purge_after_days?: number }): Promise<RetentionPolicy> {
    const { data } = await api.post<RetentionPolicy>("/data/retention/policies", payload);
    return data;
  },

  async getRetentionPolicy(id: string): Promise<RetentionPolicy> {
    const { data } = await api.get<RetentionPolicy>(`/data/retention/policies/${id}`);
    return data;
  },

  async assignRetention(payload: { record_type: string; record_id: string; policy_id: string }): Promise<RetentionAssignment> {
    const { data } = await api.post<RetentionAssignment>("/data/retention/assign", payload);
    return data;
  },

  async retentionByRecord(record_id: string): Promise<RetentionAssignment | null> {
    try {
      const { data } = await api.get<RetentionAssignment>("/data/retention:by-record", { params: { record_id } });
      return data;
    } catch { return null; }
  },

  // ── C07 — Archive Jobs ───────────────────────────────────────────────────────
  async createArchiveJob(payload: { archive_scope: string; record_ids: string[]; retention_policy_id?: string }): Promise<ArchiveJob> {
    const { data } = await api.post<ArchiveJob>("/data/archive/jobs", payload);
    return data;
  },

  async getArchiveJob(id: string): Promise<ArchiveJob> {
    const { data } = await api.get<ArchiveJob>(`/data/archive/jobs/${id}`);
    return data;
  },

  async restoreFromArchive(archive_id: string): Promise<RestoreJob> {
    const { data } = await api.post<RestoreJob>(`/data/archive/${archive_id}/restore`);
    return data;
  },

  // ── C07 — Crypto-Shred ───────────────────────────────────────────────────────
  async requestCryptoShred(payload: { subject_ref: string; affected_key_ids: string[]; affected_record_ids: string[] }): Promise<CryptoShredRequest> {
    const { data } = await api.post<CryptoShredRequest>("/privacy/crypto-shred", payload);
    return data;
  },

  async getCryptoShred(id: string): Promise<CryptoShredRequest> {
    const { data } = await api.get<CryptoShredRequest>(`/privacy/crypto-shred/${id}`);
    return data;
  },

  async verifyCryptoShred(id: string): Promise<CryptoShredVerification> {
    const { data } = await api.get<CryptoShredVerification>(`/privacy/crypto-shred/${id}/verify`);
    return data;
  },

  // ── C07 — Restore Jobs ───────────────────────────────────────────────────────
  async createRestoreJob(payload: { restore_type: string; restored_scope: string }): Promise<RestoreJob> {
    const { data } = await api.post<RestoreJob>("/data/restore/jobs", payload);
    return data;
  },

  async getRestoreJob(id: string): Promise<RestoreJob> {
    const { data } = await api.get<RestoreJob>(`/data/restore/jobs/${id}`);
    return data;
  },

  async getRestoreVerification(restore_job_id: string): Promise<RestoreVerification> {
    const { data } = await api.get<RestoreVerification>(`/data/restore/jobs/${restore_job_id}/verification`);
    return data;
  },

  async submitRestoreVerification(restore_job_id: string, checks: Record<string, boolean>): Promise<RestoreVerification> {
    const { data } = await api.post<RestoreVerification>(`/data/restore/jobs/${restore_job_id}/verify`, checks);
    return data;
  },

  async approveRestoreUse(restore_job_id: string): Promise<RestoreJob> {
    const { data } = await api.post<RestoreJob>(`/data/restore/jobs/${restore_job_id}/approve-use`);
    return data;
  },

  // ── C07 — Purge Jobs ─────────────────────────────────────────────────────────
  async createPurgeJob(payload: { purge_scope: string; record_count: number; retention_policy_id?: string; scope_ids?: string[] }): Promise<PurgeJob> {
    const { data } = await api.post<PurgeJob>("/data/purge/jobs", payload);
    return data;
  },

  async getPurgeJob(id: string): Promise<PurgeJob> {
    const { data } = await api.get<PurgeJob>(`/data/purge/jobs/${id}`);
    return data;
  },

  async approvePurge(id: string, approval_id: string): Promise<PurgeJob> {
    const { data } = await api.post<PurgeJob>(`/data/purge/jobs/${id}/approve`, { approval_id });
    return data;
  },
};

// ── Carrier types ─────────────────────────────────────────────────────────────
export interface CarrierItem {
  id:             string;
  name:           string;
  email:          string;
  address:        string;
  contact_person: string;
  contact_phone:  string;
  cc_emails:      string;
  created_at:     string;
}

// ── Tenant types ──────────────────────────────────────────────────────────────
export interface TenantItem {
  tenant_id:    string;
  display_name: string;
  slug:         string;
  status:       string;
  user_count:   number;
  created_at:   string;
}

export interface TenantCreateRequest {
  display_name:   string;
  slug:           string;
  admin_email:    string;
  admin_name:     string;
  admin_password: string;
}

export interface TenantCreateResponse {
  tenant_id:     string;
  display_name:  string;
  slug:          string;
  status:        string;
  admin_user_id: string;
  admin_email:   string;
  created_at:    string;
}

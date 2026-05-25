import { api, USE_MOCK } from "./client";
import * as mocks from "@/mocks/fixtures";
import type {
  Case, CanonicalInvoice, ValidationResult, EvidenceBundle, Finding,
  DecisionProposal, GovernanceToken, GovernanceDecision, CaseEvent,
  KafkaEvent, DashboardStats, SourceRecord
} from "@/types";

// Simulates network latency for mock mode so loading states are visible
const delay = (ms = 250) => new Promise(r => setTimeout(r, ms));

export const zoikoApi = {
  // ---------- Dashboard ----------
  async getStats(): Promise<DashboardStats> {
    if (USE_MOCK) { await delay(); return mocks.mockStats; }
    const { data } = await api.get<DashboardStats>("/dashboard/stats");
    return data;
  },

  // ---------- Cases ----------
  async listCases(filters?: { state?: string }): Promise<Case[]> {
    if (USE_MOCK) {
      await delay();
      return filters?.state
        ? mocks.mockCases.filter(c => c.state === filters.state)
        : mocks.mockCases;
    }
    const { data } = await api.get<Case[]>("/cases", { params: filters });
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

  async createCase(payload: { carrier: string; route: string; amount: number; currency: string }): Promise<Case> {
    if (USE_MOCK) {
      await delay(500);
      // Calculate realistic diff based on carrier contract rates
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
    const { data } = await api.post<Case>("/cases/submit", payload);
    return data;
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
      // Move case to PENDING_APPROVAL so it appears in manager queue
      const c = mocks.mockCases.find(x => x.id === caseId);
      if (c) {
        c.state = "APPROVAL_PENDING";
        c.updated_at = new Date().toISOString();
      }
      return { ...mocks.mockProposal, case_id: caseId, ...payload } as DecisionProposal;
    }
    const { data } = await api.post<DecisionProposal>(`/cases/${caseId}/proposal`, payload);
    return data;
  },

  async approveDecision(caseId: string, payload: { decision: "EXECUTION_READY" | "ABORTED"; note?: string }): Promise<GovernanceDecision> {
    if (USE_MOCK) {
      await delay(700);
      // Move case to APPROVED or REJECTED so it leaves the manager queue
      const c = mocks.mockCases.find(x => x.id === caseId);
      if (c) {
        c.state = payload.decision === "EXECUTION_READY" ? "EXECUTION_READY" : "ABORTED";
        c.updated_at = new Date().toISOString();
      }
      // Issue a governance token for approved cases so Stage 7 shows in CaseDetail
      if (payload.decision === "EXECUTION_READY") {
        const existing = mocks.mockTokens.find(t => t.case_id === caseId);
        if (!existing) {
          mocks.mockTokens.push({
            id: `tok_${Date.now()}`,
            case_id: caseId,
            tenant_id: "amazon-india",
            action: "EXECUTE_CREDIT_MEMO",
            amount: c?.diff ?? 4500,
            currency: c?.currency ?? "INR",
            tenant_binding: mocks.rndHash(),
            exp: new Date(Date.now() + 15 * 60_000).toISOString(),
            status: "ACTIVE",
            signature: mocks.rndHash(128),
            key_id: "amazon-india-signing-2025-01",
            issued_at: new Date().toISOString(),
          });
        }
      }
      return {
        id: `dec_${Date.now()}`,
        case_id: caseId,
        proposer_sub: "user_analyst_01",
        actor_sub: "user_manager_01",
        decision: payload.decision,
        decision_hash: mocks.rndHash(),
        decided_at: new Date().toISOString(),
      };
    }
    const { data } = await api.post<GovernanceDecision>(`/cases/${caseId}/decide`, payload);
    return data;
  },

  async listTokens(filters?: { status?: string }): Promise<GovernanceToken[]> {
    if (USE_MOCK) {
      await delay();
      return filters?.status
        ? mocks.mockTokens.filter(t => t.status === filters.status)
        : mocks.mockTokens;
    }
    const { data } = await api.get<GovernanceToken[]>("/tokens", { params: filters });
    return data;
  },

  async getTokenForCase(caseId: string): Promise<GovernanceToken | null> {
    if (USE_MOCK) {
      await delay();
      return mocks.mockTokens.find(t => t.case_id === caseId) ?? null;
    }
    const { data } = await api.get<GovernanceToken | null>(`/cases/${caseId}/token`);
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

  async createContractRate(payload: { carrier_id: string; rate_value: number; currency: string; effective_on: string }): Promise<{ id: string }> {
    if (USE_MOCK) {
      await delay(400);
      return { id: `cr_${Date.now()}` };
    }
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
};

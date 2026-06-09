import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Brain, ArrowLeft, CheckCircle2, AlertTriangle, MinusCircle, TrendingUp } from "lucide-react";

interface ReasoningData {
  case_id: string;
  findings: { id: string; finding_type: string; severity: string; confidence: number | null; summary: string; created_at: string }[];
  rule_traces: { id: string; validator: string; rule_id: string; result: string; executed_at: string }[];
  confidence_assessments: { subject_id: string; score: number; model_id: string; assessed_at: string }[];
}

interface ProposalsData {
  case_id: string;
  proposals: { id: string; action_type: string; evidence_bundle_id: string | null; confidence_score: number | null; recommended_amount: number | null; status: string; created_at: string }[];
}

const SEVERITY_STYLE: Record<string, string> = {
  HIGH:     "bg-red-50 text-red-700 border-red-200",
  MEDIUM:   "bg-yellow-50 text-yellow-700 border-yellow-200",
  LOW:      "bg-green-50 text-green-700 border-green-200",
  CRITICAL: "bg-red-100 text-red-800 border-red-300",
};

const RESULT_ICON = (r: string) =>
  r === "PASS" ? <CheckCircle2 className="h-4 w-4 text-green-500" /> :
  r === "FAIL" ? <AlertTriangle className="h-4 w-4 text-red-500" /> :
                 <MinusCircle className="h-4 w-4 text-slate-400" />;

export default function DecisionProposals() {
  const { id: caseId } = useParams<{ id: string }>();

  const { data: reasoning, isLoading: rLoad } = useQuery<ReasoningData>({
    queryKey: ["case-reasoning", caseId],
    queryFn: async () => { const { data } = await api.get(`/v1/cases/${caseId}/reasoning`); return data; },
    enabled: !!caseId,
  });

  const { data: proposals, isLoading: pLoad } = useQuery<ProposalsData>({
    queryKey: ["case-proposals", caseId],
    queryFn: async () => { const { data } = await api.get(`/v1/cases/${caseId}/decision-proposals`); return data; },
    enabled: !!caseId,
  });

  const isLoading = rLoad || pLoad;

  const fmtINR = (n: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to={`/cases/${caseId}`} className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <Brain className="h-6 w-6 text-slate-600" />
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Decision & Reasoning</h1>
          <p className="text-xs text-slate-400 font-mono">Case {caseId}</p>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />)}</div>
      )}

      {/* Proposals */}
      {proposals && (
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3 flex items-center gap-2">
            <TrendingUp className="h-4 w-4" /> Decision Proposals
          </h2>
          {proposals.proposals.length === 0 ? (
            <p className="text-sm text-slate-400 bg-slate-50 border border-slate-200 rounded-xl p-6 text-center">No proposals generated yet.</p>
          ) : (
            <div className="space-y-3">
              {proposals.proposals.map(p => (
                <div key={p.id} className="bg-white border border-slate-200 rounded-xl p-4">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-slate-800">{p.action_type}</span>
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${p.status === "ACTIVE" ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-600"}`}>{p.status}</span>
                  </div>
                  <div className="flex items-center gap-6 mt-2 text-sm text-slate-500">
                    {p.confidence_score != null && (
                      <span className="flex items-center gap-1">
                        <span className="text-xs text-slate-400">Confidence</span>
                        <span className="font-semibold text-slate-700">{(p.confidence_score * 100).toFixed(1)}%</span>
                      </span>
                    )}
                    {p.recommended_amount != null && (
                      <span className="flex items-center gap-1">
                        <span className="text-xs text-slate-400">Recommended</span>
                        <span className="font-semibold text-green-600">{fmtINR(p.recommended_amount)}</span>
                      </span>
                    )}
                    <span className="text-xs text-slate-400 ml-auto">{new Date(p.created_at).toLocaleString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Findings */}
      {reasoning && (
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Findings ({reasoning.findings.length})</h2>
          {reasoning.findings.length === 0 ? (
            <p className="text-sm text-slate-400 py-4 text-center">No findings.</p>
          ) : (
            <div className="space-y-2">
              {reasoning.findings.map(f => (
                <div key={f.id} className={`border rounded-xl p-4 ${SEVERITY_STYLE[f.severity] ?? "bg-slate-50 border-slate-200 text-slate-700"}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{f.finding_type}</span>
                    <span className="text-xs font-semibold uppercase">{f.severity}</span>
                  </div>
                  {f.summary && <p className="text-sm mt-1 opacity-80">{f.summary}</p>}
                  {f.confidence != null && (
                    <p className="text-xs mt-1 opacity-60">Confidence: {(f.confidence * 100).toFixed(1)}%</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Rule traces */}
      {reasoning && reasoning.rule_traces.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Rule Traces ({reasoning.rule_traces.length})</h2>
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            {reasoning.rule_traces.map(t => (
              <div key={t.id} className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 last:border-0">
                {RESULT_ICON(t.result)}
                <span className="text-sm font-medium text-slate-700">{t.validator}</span>
                <span className="text-xs text-slate-400 font-mono">{t.rule_id}</span>
                <span className="text-xs text-slate-400 ml-auto">{new Date(t.executed_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

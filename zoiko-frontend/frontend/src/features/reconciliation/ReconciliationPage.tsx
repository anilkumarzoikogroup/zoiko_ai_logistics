import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { cn, formatCurrency } from "@/utils/cn";
import { useAppSelector } from "@/store";
import { Scale, CheckCircle2, XCircle, AlertCircle } from "lucide-react";

const STATUS_STYLE: Record<string, { cls: string; icon: typeof CheckCircle2 }> = {
  MATCHED:    { cls: "bg-emerald-100 text-emerald-700 border-emerald-200", icon: CheckCircle2 },
  VARIANCE:   { cls: "bg-amber-100 text-amber-700 border-amber-200",       icon: AlertCircle  },
  FAILED:     { cls: "bg-red-100 text-red-700 border-red-200",             icon: XCircle      },
};

const VARIANCE_STATUS_BADGE: Record<string, string> = {
  OPEN:     "bg-amber-100 text-amber-700 border-amber-200",
  RESOLVED: "bg-emerald-100 text-emerald-700 border-emerald-200",
  WAIVED:   "bg-slate-100 text-slate-500 border-slate-200",
};

export default function ReconciliationPage() {
  const sub = useAppSelector(s => s.auth.sub) ?? "system";
  const qc = useQueryClient();

  const [envelopeId, setEnvelopeId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [activeCaseId, setActiveCaseId] = useState("");

  const reconcileMut = useMutation({
    mutationFn: () => zoikoApi.reconcileEnvelope(envelopeId.trim(), sub),
  });

  const variancesQ = useQuery({
    queryKey: ["variances", activeCaseId],
    queryFn: () => zoikoApi.listVariances(activeCaseId),
    enabled: !!activeCaseId,
  });

  const resolveMut = useMutation({
    mutationFn: ({ varianceId, action }: { varianceId: string; action: "RESOLVE" | "WAIVE" }) =>
      zoikoApi.resolveVariance(activeCaseId, varianceId, action),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["variances", activeCaseId] }),
  });

  const result = reconcileMut.data;
  const resultStyle = result ? (STATUS_STYLE[result.status] ?? STATUS_STYLE.VARIANCE) : null;
  const ResultIcon = resultStyle?.icon ?? AlertCircle;

  const variances = variancesQ.data ?? [];
  const openCount = variances.filter(v => v.status === "OPEN").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Reconciliation</h1>
        <p className="text-sm text-slate-500 mt-0.5">Phase 4 — Match dispatched execution envelopes against connector settlements</p>
      </div>

      {/* Reconcile an envelope */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Scale className="h-4 w-4 text-blue-500" />
            <h2 className="font-semibold text-slate-700 text-sm">Reconcile Execution Envelope</h2>
          </div>
          <div className="flex gap-2">
            <input
              value={envelopeId}
              onChange={e => setEnvelopeId(e.target.value)}
              placeholder="Envelope ID (UUID)"
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
            />
            <button
              onClick={() => reconcileMut.mutate()}
              disabled={!envelopeId.trim() || reconcileMut.isPending}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              {reconcileMut.isPending ? "Reconciling…" : "Reconcile"}
            </button>
          </div>

          {reconcileMut.error && (
            <p className="text-xs text-red-600 mt-3">{String((reconcileMut.error as any)?.response?.data?.detail ?? reconcileMut.error)}</p>
          )}

          {result && resultStyle && (
            <div className={cn("mt-4 p-4 rounded-lg border flex items-start gap-3", resultStyle.cls)}>
              <ResultIcon className="h-5 w-5 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-bold">{result.status}</p>
                <p className="text-xs mt-1 opacity-80">
                  Reconciliation ID: <span className="font-mono">{result.reconciliation_id}</span>
                </p>
                <p className="text-xs mt-0.5 opacity-80">
                  Delta: <span className="font-semibold">{formatCurrency(result.delta, "INR")}</span> · {new Date(result.reconciled_at).toLocaleString()}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Variance lookup */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-amber-500" />
              <h2 className="font-semibold text-slate-700 text-sm">Case Variances</h2>
              {openCount > 0 && (
                <span className="text-[10px] font-bold bg-amber-100 text-amber-600 px-2 py-0.5 rounded-full">
                  {openCount} OPEN
                </span>
              )}
            </div>
          </div>
          <div className="flex gap-2 mb-4">
            <input
              value={caseId}
              onChange={e => setCaseId(e.target.value)}
              placeholder="Case ID (UUID)"
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
            />
            <button
              onClick={() => setActiveCaseId(caseId.trim())}
              disabled={!caseId.trim()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Load
            </button>
          </div>

          {!activeCaseId ? (
            <p className="text-sm text-slate-400 text-center py-6">Enter a case ID to view its variance records.</p>
          ) : variancesQ.isLoading ? (
            <p className="text-sm text-slate-400 text-center py-6">Loading…</p>
          ) : variances.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-6">No variance records for this case. ACR can be issued once execution and reconciliation are complete.</p>
          ) : (
            <div className="divide-y divide-slate-50">
              {variances.map(v => (
                <div key={v.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-slate-700">{v.variance_type}</span>
                      <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border", VARIANCE_STATUS_BADGE[v.status] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
                        {v.status}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      expected {v.expected_value ?? "—"} · actual {v.actual_value ?? "—"} · delta {v.delta ?? "—"}
                    </p>
                    {v.resolved_by && (
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        resolved by {v.resolved_by} · {v.resolved_at ? new Date(v.resolved_at).toLocaleString() : ""}
                      </p>
                    )}
                  </div>
                  {v.status === "OPEN" && (
                    <div className="flex gap-2 flex-shrink-0">
                      <button
                        onClick={() => resolveMut.mutate({ varianceId: v.id, action: "RESOLVE" })}
                        disabled={resolveMut.isPending}
                        className="px-3 py-1.5 rounded-lg border border-emerald-200 text-emerald-700 text-xs hover:bg-emerald-50 transition-colors disabled:opacity-50"
                      >
                        Resolve
                      </button>
                      <button
                        onClick={() => resolveMut.mutate({ varianceId: v.id, action: "WAIVE" })}
                        disabled={resolveMut.isPending}
                        className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 text-xs hover:bg-slate-50 transition-colors disabled:opacity-50"
                      >
                        Waive
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {resolveMut.error && <p className="text-xs text-red-600 mt-2">{String(resolveMut.error)}</p>}
        </CardContent>
      </Card>
    </div>
  );
}

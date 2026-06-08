import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency, cn } from "@/utils/cn";
import {
  ThumbsUp, CheckCircle2, ChevronRight,
  Zap, BarChart3, AlertTriangle,
} from "lucide-react";
import { useState } from "react";
import { useToast } from "@/hooks/useToast";
import { useAppSelector } from "@/store";

const PIPELINE_STEPS = [
  { label: "Submit Invoice",  active: false },
  { label: "Ingest & Hash",   active: false },
  { label: "Validate",        active: false },
  { label: "AI Analysis",     active: true  },
  { label: "Propose",         active: false },
  { label: "Manager Approval",active: false },
  { label: "Execute & ACR",   active: false },
];

function ConfidenceRing({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 90 ? "#10b981" : pct >= 70 ? "#f59e0b" : "#ef4444";
  return (
    <div className="flex flex-col items-center gap-1 w-16 flex-shrink-0">
      <div className="relative h-14 w-14">
        <svg className="h-14 w-14 -rotate-90" viewBox="0 0 56 56">
          <circle cx="28" cy="28" r="22" fill="none" stroke="#f1f5f9" strokeWidth="5" />
          <circle
            cx="28" cy="28" r="22" fill="none"
            stroke={color} strokeWidth="5"
            strokeDasharray={`${(pct / 100) * 138.2} 138.2`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[13px] font-bold" style={{ color }}>{pct}%</span>
        </div>
      </div>
      <p className="text-[9px] text-slate-400 uppercase tracking-wide font-semibold text-center leading-tight">AI Confidence</p>
    </div>
  );
}

export default function AnalystReview() {
  const nav   = useNavigate();
  const qc    = useQueryClient();
  const toast = useToast();
  const { data: cases, isLoading } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases(), refetchInterval: 5000 });
  const [proposed, setProposed] = useState<Set<string>>(new Set());

  const queue = (cases || [])
    .filter(c => ["NEW","EVIDENCE_PENDING","FINDING_GENERATED"].includes(c.state))
    .sort((a, b) => (b.confidence || 0) - (a.confidence || 0));

  const propose = useMutation({
    mutationFn: (c: { id: string; diff: number; currency: string }) =>
      zoikoApi.proposeRecovery(c.id, {
        action:   "EXECUTE_CREDIT_MEMO",
        amount:   c.diff,
        currency: c.currency || "INR",
      }),
    onSuccess: (_d, vars) => {
      setProposed(prev => new Set(prev).add(vars.id));
      qc.invalidateQueries({ queryKey: ["cases"] });
      toast.success("Recovery proposed", `${formatCurrency(vars.diff, vars.currency)} sent for manager approval`);
    },
    onError: () => {
      toast.error("Proposal failed", "Check that the backend is running on port 8000");
    },
  });

  const user = useAppSelector(s => s.auth.user) || "Analyst";

  return (
    <div className="space-y-5">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Analyst Review</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Signed in as <span className="font-semibold text-slate-600">{user}</span> ·
            Review flagged invoices and propose recovery
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-1.5 text-xs text-amber-700 font-semibold">
          <AlertTriangle className="h-3.5 w-3.5" />
          {queue.length} awaiting review
        </div>
      </div>

      {/* ── Pipeline banner ─────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3">SC-001 Pipeline — Analyst Stage</p>
        <div className="flex items-center gap-0">
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step.label} className="flex items-center flex-1 min-w-0">
              <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
                <div className={cn(
                  "h-7 w-7 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0",
                  step.active
                    ? "bg-blue-600 text-white ring-2 ring-blue-200 ring-offset-1"
                    : i < PIPELINE_STEPS.findIndex(s => s.active)
                    ? "bg-emerald-500 text-white"
                    : "bg-slate-100 text-slate-400"
                )}>
                  {step.active ? <Zap className="h-3.5 w-3.5" /> : i < PIPELINE_STEPS.findIndex(s => s.active) ? <CheckCircle2 className="h-3.5 w-3.5" /> : i + 1}
                </div>
                <p className={cn(
                  "text-[9px] text-center hidden sm:block truncate w-full font-medium",
                  step.active ? "text-blue-600" : i < PIPELINE_STEPS.findIndex(s => s.active) ? "text-emerald-600" : "text-slate-400"
                )}>
                  {step.label}
                </p>
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <div className={cn("h-0.5 flex-1 mx-1", i < PIPELINE_STEPS.findIndex(s => s.active) ? "bg-emerald-400" : "bg-slate-200")} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Queue ────────────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="space-y-3">
          {[0,1,2].map(i => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse">
              <div className="flex items-center gap-4">
                <div className="h-14 w-14 rounded-full bg-slate-100" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 bg-slate-100 rounded-full w-1/3" />
                  <div className="h-3 bg-slate-100 rounded-full w-1/2" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : queue.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 shadow-sm flex flex-col items-center gap-3 text-center">
          <div className="h-12 w-12 rounded-full bg-emerald-50 flex items-center justify-center">
            <CheckCircle2 className="h-6 w-6 text-emerald-500" />
          </div>
          <p className="font-semibold text-slate-700">Queue clear</p>
          <p className="text-sm text-slate-400 max-w-xs">
            No cases waiting for analyst review. New invoices will appear here once overcharges are detected.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {queue.map(c => {
            const isDone = proposed.has(c.id);
            return (
              <div
                key={c.id}
                className={cn(
                  "bg-white rounded-xl border border-slate-200 p-5 shadow-sm transition-all",
                  isDone ? "opacity-60 bg-slate-50" : "hover:shadow-md hover:border-slate-300"
                )}
              >
                <div className="flex items-start gap-4">
                  {/* Confidence ring */}
                  <ConfidenceRing value={c.confidence || 0} />

                  {/* Details */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1.5">
                      <code className="text-[10px] font-mono text-slate-400 bg-slate-50 border border-slate-100 px-2 py-0.5 rounded">
                        {c.id.slice(0, 12)}…
                      </code>
                      <span className={cn(
                        "text-[10px] font-bold px-2 py-0.5 rounded-full",
                        c.state === "FINDING_GENERATED" ? "bg-purple-100 text-purple-700" : "bg-slate-100 text-slate-600"
                      )}>
                        {c.state.replace(/_/g," ")}
                      </span>
                    </div>

                    <p className="font-bold text-slate-800 text-sm">{c.carrier}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{c.shipment_ref}</p>

                    <div className="flex items-center gap-5 mt-3 flex-wrap">
                      <div>
                        <p className="text-[9px] text-slate-400 uppercase tracking-wide font-semibold">Invoice Amount</p>
                        <p className="text-sm font-bold text-slate-700 mt-0.5">{formatCurrency(c.amount, c.currency)}</p>
                      </div>
                      <div>
                        <p className="text-[9px] text-slate-400 uppercase tracking-wide font-semibold">Overcharge</p>
                        <p className="text-sm font-bold text-red-600 mt-0.5">{formatCurrency(c.diff, c.currency)}</p>
                      </div>
                      <div>
                        <p className="text-[9px] text-slate-400 uppercase tracking-wide font-semibold">Recovery Action</p>
                        <p className="text-xs font-semibold text-slate-600 mt-0.5">Credit Memo</p>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col gap-2 flex-shrink-0 items-end">
                    <button
                      onClick={() => nav(`/cases/${c.id}`)}
                      className="flex items-center gap-1 text-xs text-blue-600 hover:underline font-semibold"
                    >
                      Case detail <ChevronRight className="h-3 w-3" />
                    </button>

                    {isDone ? (
                      <div className="flex items-center gap-1.5 text-emerald-600 font-semibold text-xs bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Proposed
                      </div>
                    ) : (
                      <button
                        onClick={() => propose.mutate({ id: c.id, diff: c.diff, currency: c.currency })}
                        disabled={propose.isPending}
                        className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-xs font-semibold transition-colors shadow-sm shadow-blue-500/25"
                      >
                        <ThumbsUp className="h-3.5 w-3.5" />
                        Propose {formatCurrency(c.diff, c.currency)}
                      </button>
                    )}
                  </div>
                </div>

                {/* SC-001 scenario callout */}
                {c.carrier === "BlueDart" && !isDone && (
                  <div className="mt-4 rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 flex items-center gap-2">
                    <BarChart3 className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" />
                    <p className="text-[10px] text-blue-700">
                      <span className="font-bold">SC-001:</span> BlueDart billed ₹12,500 · Contract rate ₹8,000 · Overcharge ₹4,500 (fuel + accessorial surcharge, 96% confidence)
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

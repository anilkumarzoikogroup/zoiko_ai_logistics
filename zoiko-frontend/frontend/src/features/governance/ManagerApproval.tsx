import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency, cn } from "@/utils/cn";
import {
  CheckCircle2, XCircle, ShieldAlert, ChevronRight,
  Lock, Users, Zap, Clock,
} from "lucide-react";
import { useState } from "react";
import { useToast } from "@/hooks/useToast";
import { useAppSelector } from "@/store";

export default function ManagerApproval() {
  const nav   = useNavigate();
  const qc    = useQueryClient();
  const toast = useToast();
  const { data: cases, isLoading } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases(), refetchInterval: 5000 });
  const [decided, setDecided] = useState<Record<string, "EXECUTION_READY" | "ABORTED">>({});

  const queue = (cases || []).filter(c => c.state === "APPROVAL_PENDING");

  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "EXECUTION_READY" | "ABORTED" }) =>
      zoikoApi.approveDecision(id, { decision }),
    onSuccess: (_d, vars) => {
      setDecided(prev => ({ ...prev, [vars.id]: vars.decision }));
      qc.invalidateQueries({ queryKey: ["cases"] });
      if (vars.decision === "EXECUTION_READY") {
        toast.success("Case approved", "Governance token issued — 15-min execution window open");
      } else {
        toast.info("Case rejected", "Case marked ABORTED");
      }
    },
    onError: () => {
      toast.error("Decision failed", "SoD rule: you cannot approve your own proposal");
    },
  });

  const user = useAppSelector(s => s.auth.user) || "Manager";

  return (
    <div className="space-y-5">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Manager Approval</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Signed in as <span className="font-semibold text-slate-600">{user}</span> ·
            Final approver for recovery decisions
          </p>
        </div>
        {queue.length > 0 && (
          <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-1.5 text-xs text-amber-700 font-semibold">
            <Clock className="h-3.5 w-3.5" />
            {queue.length} pending decision
          </div>
        )}
      </div>

      {/* ── SoD compliance notice ────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-amber-200 bg-amber-50/30 p-4 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="h-9 w-9 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
            <ShieldAlert className="h-5 w-5 text-amber-700" />
          </div>
          <div>
            <p className="font-bold text-amber-900 text-sm">Separation of Duties (SoD) Enforced</p>
            <p className="text-xs text-amber-700 mt-1 leading-relaxed">
              You cannot approve a proposal you submitted yourself.
              If your <code className="bg-amber-100 px-1 rounded text-[10px]">sub</code> matches the proposer's,
              the backend rejects the request before any database write (no bypass possible).
            </p>
          </div>
          <div className="flex items-center gap-1.5 ml-auto text-[10px] text-amber-700 font-semibold whitespace-nowrap">
            <Lock className="h-3 w-3" /> WORM enforced
          </div>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-3">
          {[
            { icon: Users,        label: "Proposer",   sub: "Ravi Kumar (analyst)"   },
            { icon: ShieldAlert,  label: "Approver",   sub: "You (manager — different user)" },
            { icon: Lock,         label: "SoD Check",  sub: "JWT sub comparison"     },
          ].map(b => (
            <div key={b.label} className="rounded-lg bg-white border border-amber-100 px-3 py-2 flex items-center gap-2">
              <b.icon className="h-3.5 w-3.5 text-amber-600 flex-shrink-0" />
              <div>
                <p className="text-[10px] font-bold text-slate-700">{b.label}</p>
                <p className="text-[9px] text-slate-400">{b.sub}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Approval queue ───────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="space-y-3">
          {[0,1].map(i => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse">
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 rounded-full bg-slate-100" />
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
          <p className="font-semibold text-slate-700">No pending approvals</p>
          <p className="text-sm text-slate-400 max-w-xs">
            Cases awaiting your approval will appear here after analysts propose recovery.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {queue.map(c => {
            const result = decided[c.id];
            return (
              <div
                key={c.id}
                className={cn(
                  "bg-white rounded-xl border border-slate-200 p-5 shadow-sm transition-all",
                  result ? "opacity-70" : "hover:shadow-md"
                )}
              >
                <div className="flex items-start justify-between gap-4">
                  {/* Case info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <code className="text-[10px] font-mono text-slate-400 bg-slate-50 border border-slate-100 px-2 py-0.5 rounded">
                        {c.id.slice(0, 12)}…
                      </code>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
                        Pending Approval
                      </span>
                    </div>
                    <p className="font-bold text-slate-800">{c.carrier}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{c.shipment_ref}</p>

                    {/* Financial summary */}
                    <div className="mt-4 grid grid-cols-3 gap-3">
                      <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5 text-center">
                        <p className="text-[9px] text-slate-400 uppercase tracking-wide font-semibold">Invoice</p>
                        <p className="text-sm font-bold text-slate-700 mt-1">{formatCurrency(c.amount, c.currency)}</p>
                      </div>
                      <div className="rounded-lg bg-red-50 border border-red-100 px-3 py-2.5 text-center">
                        <p className="text-[9px] text-red-400 uppercase tracking-wide font-semibold">Overcharge</p>
                        <p className="text-sm font-bold text-red-600 mt-1">{formatCurrency(c.diff, c.currency)}</p>
                      </div>
                      <div className="rounded-lg bg-emerald-50 border border-emerald-100 px-3 py-2.5 text-center">
                        <p className="text-[9px] text-emerald-500 uppercase tracking-wide font-semibold">AI Score</p>
                        <p className="text-sm font-bold text-emerald-600 mt-1">{((c.confidence || 0) * 100).toFixed(0)}%</p>
                      </div>
                    </div>

                    {/* 8-gate callout */}
                    <div className="mt-3 rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 flex items-center gap-2">
                      <Zap className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" />
                      <p className="text-[10px] text-blue-700">
                        <span className="font-bold">If approved:</span> governance token issued (15-min TTL) · Phase 4 runs 8-gate execution before money moves
                      </p>
                    </div>
                  </div>

                  {/* Decision panel */}
                  <div className="flex flex-col gap-2 flex-shrink-0 items-stretch min-w-[140px]">
                    <button
                      onClick={() => nav(`/cases/${c.id}`)}
                      className="flex items-center justify-center gap-1 text-xs text-blue-600 hover:underline font-semibold py-1"
                    >
                      Review case <ChevronRight className="h-3 w-3" />
                    </button>

                    {result ? (
                      <div className={cn(
                        "flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold",
                        result === "EXECUTION_READY"
                          ? "bg-emerald-100 text-emerald-700 border border-emerald-200"
                          : "bg-red-100 text-red-700 border border-red-200"
                      )}>
                        {result === "EXECUTION_READY"
                          ? <><CheckCircle2 className="h-3.5 w-3.5" /> Approved</>
                          : <><XCircle className="h-3.5 w-3.5" /> Rejected</>
                        }
                      </div>
                    ) : (
                      <>
                        <button
                          onClick={() => decide.mutate({ id: c.id, decision: "EXECUTION_READY" })}
                          disabled={decide.isPending}
                          className="flex items-center justify-center gap-1.5 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-colors shadow-sm shadow-emerald-500/25"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Approve Recovery
                        </button>
                        <button
                          onClick={() => decide.mutate({ id: c.id, decision: "ABORTED" })}
                          disabled={decide.isPending}
                          className="flex items-center justify-center gap-1.5 px-4 py-2.5 bg-white border border-red-200 hover:bg-red-50 text-red-600 rounded-lg text-xs font-bold transition-colors"
                        >
                          <XCircle className="h-3.5 w-3.5" />
                          Reject
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── What happens next ──────────────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-[#0a0f1e] to-[#0d1424] rounded-xl p-5 border border-slate-800">
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">After Approval — 8-Gate Execution</p>
        <div className="grid grid-cols-4 gap-3">
          {[
            { n: "1", label: "Sig Valid",    sub: "Ed25519 verified"       },
            { n: "2", label: "Not Expired",  sub: "15-min token TTL"       },
            { n: "3", label: "Not Consumed", sub: "Redis SET NX replay lock"},
            { n: "4-8", label: "Compliance", sub: "Sanctions · FX · Connector"},
          ].map(g => (
            <div key={g.n} className="rounded-lg bg-white/5 border border-white/8 px-3 py-2.5 text-center">
              <div className="h-6 w-6 rounded-full bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-[9px] font-bold text-blue-400 mx-auto mb-1">
                {g.n}
              </div>
              <p className="text-[10px] font-bold text-white">{g.label}</p>
              <p className="text-[9px] text-slate-500 mt-0.5">{g.sub}</p>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

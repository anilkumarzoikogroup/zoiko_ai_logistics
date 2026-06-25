import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency, formatDate, cn } from "@/utils/cn";
import {
  ArrowLeft, CheckCircle2, Clock, FileText, Brain, Lock,
  AlertTriangle, ChevronRight, Zap, Users, RefreshCw, GitBranch,
  ShieldCheck, Download, ThumbsUp, ShieldAlert, XCircle, MessageSquareWarning,
} from "lucide-react";
import { useToast } from "@/hooks/useToast";
import { useAppSelector } from "@/store";
import type { ClaimState } from "@/types";

// SC-002 — mirrors CaseDetail.tsx's pipeline-visualization pattern, but is
// self-contained: propose/approve/execute happen inline on this page instead
// of routing to the shared (invoice-only) Analyst/Manager/Execute queues.
// Real SoD is enforced server-side exactly as it is for SC-001 — the same
// logged-in user cannot both propose and approve; switch accounts between
// the two steps, same as the existing Analyst Review -> Manager Approval flow.

const STATE_STAGE: Record<ClaimState, number> = {
  NEW: 3, EVIDENCE_PENDING: 4, FINDING_GENERATED: 5,
  APPROVAL_PENDING: 6, EXECUTION_READY: 6, DISPATCHED: 7,
  OUTCOME_RECORDED: 7, CLOSED: 7, ABORTED: 5,
};

const PIPELINE_STAGES = [
  { label: "Ingested",    icon: FileText },
  { label: "Canonical",   icon: ShieldCheck },
  { label: "Case Opened", icon: AlertTriangle },
  { label: "Evidence",    icon: FileText },
  { label: "AI Reasoned", icon: Brain },
  { label: "Governance",  icon: Users },
  { label: "Executed",    icon: Lock },
];

const STATE_STYLE: Record<string, { label: string; cls: string; dot: string }> = {
  NEW:               { label: "New",              cls: "bg-slate-100 text-slate-600",     dot: "bg-slate-400"  },
  EVIDENCE_PENDING:  { label: "Evidence Pending",  cls: "bg-slate-100 text-slate-600",     dot: "bg-slate-400"  },
  FINDING_GENERATED: { label: "AI Analyzed",       cls: "bg-purple-100 text-purple-700",   dot: "bg-purple-500" },
  APPROVAL_PENDING:  { label: "Pending Approval",  cls: "bg-amber-100 text-amber-700",     dot: "bg-amber-500"  },
  EXECUTION_READY:   { label: "Execution Ready",   cls: "bg-blue-100 text-blue-700",       dot: "bg-blue-500"   },
  DISPATCHED:        { label: "Dispatched",        cls: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-500"},
  OUTCOME_RECORDED:  { label: "Outcome Recorded",  cls: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-500"},
  CLOSED:            { label: "Closed",            cls: "bg-slate-100 text-slate-500",     dot: "bg-slate-400"  },
  ABORTED:           { label: "Aborted",           cls: "bg-red-100 text-red-700",         dot: "bg-red-500"    },
};

function StateBadge({ state }: { state: string }) {
  const cfg = STATE_STYLE[state] ?? { label: state, cls: "bg-slate-100 text-slate-600", dot: "bg-slate-400" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-1 rounded-full", cfg.cls)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

function SectionCard({ title, icon: Icon, status, children }: {
  title: string; icon: React.ElementType; status: "done" | "active" | "pending"; children: React.ReactNode;
}) {
  return (
    <div className={cn("bg-white rounded-xl border p-4 shadow-sm transition-opacity", status === "pending" ? "opacity-50 border-slate-200" : "border-slate-200")}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={cn("h-7 w-7 rounded-lg flex items-center justify-center",
            status === "done" ? "bg-emerald-100" : status === "active" ? "bg-blue-100" : "bg-slate-100")}>
            <Icon className={cn("h-3.5 w-3.5", status === "done" ? "text-emerald-600" : status === "active" ? "text-blue-600" : "text-slate-400")} />
          </div>
          <p className="text-sm font-bold text-slate-700">{title}</p>
        </div>
        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full",
          status === "done" ? "bg-emerald-100 text-emerald-700" : status === "active" ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-400")}>
          {status === "done" ? "DONE" : status === "active" ? "ACTIVE" : "PENDING"}
        </span>
      </div>
      {children}
    </div>
  );
}

export default function ClaimDetail() {
  const { id = "" } = useParams();
  const nav   = useNavigate();
  const qc    = useQueryClient();
  const toast = useToast();
  const user  = useAppSelector(s => s.auth.user) || "User";
  const [counterAmount, setCounterAmount] = useState("");

  const cq      = useQuery({ queryKey: ["claim",        id], queryFn: () => zoikoApi.getClaim(id),       retry: 1 });
  const eventsQ = useQuery({ queryKey: ["claim-events",  id], queryFn: () => zoikoApi.getClaimEvents(id), retry: 1 });
  const evQ     = useQuery({ queryKey: ["claim-evidence",id], queryFn: () => zoikoApi.getClaimEvidence(id),   retry: false });
  const findQ   = useQuery({ queryKey: ["claim-finding", id], queryFn: () => zoikoApi.getClaimFinding(id),    retry: false });
  const propQ   = useQuery({ queryKey: ["claim-proposal",id], queryFn: () => zoikoApi.getClaimProposal(id),   retry: false });
  const tokenQ  = useQuery({ queryKey: ["claim-token",   id], queryFn: () => zoikoApi.getClaimToken(id), retry: false });
  const acrQ    = useQuery({ queryKey: ["claim-acr",     id], queryFn: () => zoikoApi.getClaimAcr(id),        retry: false });
  const linesQ  = useQuery({ queryKey: ["claim-lines",   id], queryFn: () => zoikoApi.getClaimLines(id), retry: false });

  const proposeMut = useMutation({
    mutationFn: () => zoikoApi.proposeClaimSettlement(id, { action: "SETTLE_CLAIM", amount: cq.data?.amount ?? 0, currency: cq.data?.currency ?? "INR" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["claim", id] });
      qc.invalidateQueries({ queryKey: ["claim-proposal", id] });
      toast.success("Settlement proposed", "Sent for manager approval (SoD: a different user must approve)");
    },
    onError: () => toast.error("Proposal failed", "Check that the SC-002 backend is running on port 8010"),
  });

  const negotiateMut = useMutation({
    mutationFn: (vars: { action: "COUNTER" | "ACCEPT" | "PARTIALLY_ACCEPT" | "REJECT"; approved_amount?: number }) =>
      zoikoApi.negotiateClaim(id, vars),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["claim", id] });
      toast.success("Carrier response recorded", `Status: ${res.negotiation_status.replace(/_/g, " ")}`);
    },
    onError: () => toast.error("Update failed", "Check that the SC-002 backend is running on port 8010"),
  });

  const decideMut = useMutation({
    mutationFn: (decision: "EXECUTION_READY" | "ABORTED") => zoikoApi.approveClaimDecision(id, { decision }),
    onSuccess: (_d, decision) => {
      qc.invalidateQueries({ queryKey: ["claim", id] });
      qc.invalidateQueries({ queryKey: ["claim-token", id] });
      if (decision === "EXECUTION_READY") toast.success("Claim approved", "Governance token issued — 15-min execution window open");
      else toast.success("Claim rejected", "Case aborted");
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      toast.error("Decision failed", typeof detail === "string" ? detail : "Check that the SC-002 backend is running on port 8010");
    },
  });

  const executeMut = useMutation({
    mutationFn: () => zoikoApi.executeClaimRecovery(tokenQ.data!.id, id, tokenQ.data!.amount, tokenQ.data!.currency),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["claim", id] });
      qc.invalidateQueries({ queryKey: ["claim-token", id] });
      toast.success("Execution complete", "Claim settlement dispatched through all 8 gates");
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      toast.error("Execution failed", typeof detail === "string" ? detail : "Check that the SC-002 backend is running on port 8010");
    },
  });

  function handleDownloadAcr() {
    zoikoApi.downloadClaimAcr(id).then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `acr_${id.slice(0, 8)}.json`;
      a.click(); URL.revokeObjectURL(url);
    }).catch(() => toast.error("Download failed", "ACR not yet issued for this case"));
  }

  if (cq.isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 w-64 bg-slate-200 rounded-lg" />
        <div className="h-4 w-48 bg-slate-100 rounded-lg" />
        <div className="grid grid-cols-4 gap-3">{[0,1,2,3].map(i => <div key={i} className="h-20 bg-slate-100 rounded-xl" />)}</div>
        <div className="h-32 bg-slate-100 rounded-xl" />
      </div>
    );
  }

  if (!cq.data) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <div className="h-12 w-12 rounded-full bg-red-50 flex items-center justify-center"><AlertTriangle className="h-6 w-6 text-red-400" /></div>
        <p className="font-semibold text-slate-700">Claim case not found</p>
        <p className="text-sm text-slate-400">The case ID <code className="bg-slate-100 px-1 rounded">{id}</code> was not found.</p>
        <button onClick={() => nav("/claims")} className="flex items-center gap-1.5 text-blue-600 text-sm font-semibold hover:underline">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Claims
        </button>
      </div>
    );
  }

  const cs = cq.data;
  const completedStages = STATE_STAGE[cs.state] ?? 3;
  const stageStatus = (n: number): "done" | "active" | "pending" => n < completedStages ? "done" : n === completedStages ? "active" : "pending";
  const hasPendingProposal = !!propQ.data && cs.state === "APPROVAL_PENDING";

  return (
    <div className="space-y-5">

      <div>
        <button onClick={() => nav("/claims")} className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 mb-2 transition-colors">
          <ArrowLeft className="h-3 w-3" /> All Claims
        </button>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-800">
              {cs.carrier} <span className="text-slate-400 font-normal">·</span> {cs.shipment_ref}
            </h1>
            <div className="flex items-center gap-3 mt-1.5 flex-wrap">
              <code className="text-[10px] font-mono text-slate-400 bg-slate-100 px-2 py-0.5 rounded">{cs.id}</code>
              <StateBadge state={cs.state} />
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">{cs.claim_type}</span>
              <span className="text-[11px] text-slate-400">Opened {formatDate(cs.opened_at)}</span>
            </div>
          </div>
          <button onClick={() => cq.refetch()} className="p-2 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors" title="Refresh">
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Claimed Amount", value: formatCurrency(cs.amount, cs.currency), top: "border-l-blue-500", val: "text-slate-800" },
          { label: "Claim Type",     value: cs.claim_type,                          top: "border-l-indigo-500", val: "text-indigo-600" },
          { label: "Signed in as",   value: user,                                   top: "border-l-amber-500", val: "text-amber-600" },
          {
            label: findQ.data?.ai_confidence != null ? "AI Confidence" : "Rule Score",
            value: findQ.data?.ai_confidence != null
              ? `${(findQ.data.ai_confidence * 100).toFixed(0)}%`
              : cs.confidence
                ? `${(cs.confidence * 100).toFixed(0)}%`
                : "—",
            top: "border-l-emerald-500",
            val: (findQ.data?.ai_confidence ?? cs.confidence ?? 0) >= 0.9
              ? "text-emerald-600 font-bold"
              : "text-amber-600",
          },
        ].map(k => (
          <div key={k.label} className={cn("bg-white rounded-xl border border-slate-200 border-l-4 px-4 py-3.5 shadow-sm", k.top)}>
            <p className="text-[10px] text-slate-400 uppercase tracking-wide font-semibold">{k.label}</p>
            <p className={cn("text-xl font-bold mt-1.5 leading-tight truncate", k.val)}>{k.value}</p>
          </div>
        ))}
      </div>

      {/* ── Carrier negotiation (independent of the governance FSM) ────────── */}
      {!["CLOSED", "ABORTED"].includes(cs.state) && (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="h-9 w-9 rounded-lg border border-indigo-200 bg-indigo-100 flex items-center justify-center flex-shrink-0">
                <MessageSquareWarning className="h-5 w-5 text-indigo-700" />
              </div>
              <div>
                <p className="font-bold text-sm text-indigo-700">Carrier Negotiation</p>
                <p className="text-xs mt-0.5 leading-relaxed text-indigo-600">
                  Track the carrier's response separately from internal approval — counter-offer, accept in full, accept partially, or reject.
                </p>
              </div>
            </div>
            <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-indigo-100 text-indigo-700 whitespace-nowrap">
              {(cs.negotiation_status || "SUBMITTED").replace(/_/g, " ")}
            </span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="number" placeholder="Counter / approved amount"
              value={counterAmount} onChange={e => setCounterAmount(e.target.value)}
              className="w-48 rounded-lg border border-indigo-200 bg-white px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <button
              onClick={() => negotiateMut.mutate({ action: "COUNTER", approved_amount: Number(counterAmount) || undefined })}
              disabled={negotiateMut.isPending || !counterAmount}
              className="px-3 py-2 rounded-lg bg-white border border-indigo-300 text-indigo-700 text-xs font-bold hover:bg-indigo-100 disabled:opacity-50 transition-colors"
            >
              Record Counter-Offer
            </button>
            <button
              onClick={() => negotiateMut.mutate({ action: "ACCEPT", approved_amount: cs.amount })}
              disabled={negotiateMut.isPending}
              className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold disabled:opacity-50 transition-colors"
            >
              Carrier Accepted Full
            </button>
            <button
              onClick={() => negotiateMut.mutate({ action: "PARTIALLY_ACCEPT", approved_amount: Number(counterAmount) || undefined })}
              disabled={negotiateMut.isPending || !counterAmount}
              className="px-3 py-2 rounded-lg bg-amber-100 border border-amber-300 text-amber-700 text-xs font-bold hover:bg-amber-200 disabled:opacity-50 transition-colors"
            >
              Partially Accepted
            </button>
            <button
              onClick={() => negotiateMut.mutate({ action: "REJECT" })}
              disabled={negotiateMut.isPending}
              className="px-3 py-2 rounded-lg bg-white border border-red-200 text-red-600 text-xs font-bold hover:bg-red-50 disabled:opacity-50 transition-colors"
            >
              Carrier Rejected
            </button>
          </div>
          {cs.approved_amount != null && (
            <p className="text-[11px] text-indigo-600">Carrier-approved amount on file: <span className="font-bold">{formatCurrency(cs.approved_amount, cs.currency)}</span></p>
          )}
        </div>
      )}

      {/* ── Inline governance actions ───────────────────────────────────── */}
      {(cs.state === "NEW" || cs.state === "EVIDENCE_PENDING" || cs.state === "FINDING_GENERATED") && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 flex items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="h-9 w-9 rounded-lg border border-blue-200 bg-blue-100 flex items-center justify-center flex-shrink-0"><Brain className="h-5 w-5 text-blue-700" /></div>
            <div>
              <p className="font-bold text-sm text-blue-700">Analyst step: Propose Settlement</p>
              <p className="text-xs mt-0.5 leading-relaxed text-blue-600">
                AI scored this claim at {findQ.data ? `${((findQ.data.ai_confidence ?? findQ.data.confidence) * 100).toFixed(0)}%` : "…"} confidence. Propose settling {formatCurrency(cs.amount, cs.currency)} for manager approval.
              </p>
            </div>
          </div>
          <button onClick={() => proposeMut.mutate()} disabled={proposeMut.isPending || cs.state !== "FINDING_GENERATED"}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold whitespace-nowrap transition-colors flex-shrink-0">
            <ThumbsUp className="h-3.5 w-3.5" /> {proposeMut.isPending ? "Proposing…" : "Propose Settlement"}
          </button>
        </div>
      )}

      {hasPendingProposal && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-3">
          <div className="flex items-start gap-3">
            <div className="h-9 w-9 rounded-lg border border-amber-200 bg-amber-100 flex items-center justify-center flex-shrink-0"><ShieldAlert className="h-5 w-5 text-amber-700" /></div>
            <div>
              <p className="font-bold text-sm text-amber-700">Manager step: Approve or Reject</p>
              <p className="text-xs mt-0.5 leading-relaxed text-amber-600">
                Proposed by <span className="font-semibold">{propQ.data?.proposed_by}</span> — Separation of Duties is enforced server-side: sign in as a different user to approve.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => decideMut.mutate("EXECUTION_READY")} disabled={decideMut.isPending}
              className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold transition-colors">
              <CheckCircle2 className="h-3.5 w-3.5" /> Approve
            </button>
            <button onClick={() => decideMut.mutate("ABORTED")} disabled={decideMut.isPending}
              className="flex items-center gap-1.5 px-4 py-2 border border-slate-300 hover:bg-slate-100 text-slate-700 rounded-lg text-sm font-bold transition-colors">
              <XCircle className="h-3.5 w-3.5" /> Reject
            </button>
          </div>
        </div>
      )}

      {cs.state === "EXECUTION_READY" && tokenQ.data && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="h-9 w-9 rounded-lg border border-emerald-200 bg-emerald-100 flex items-center justify-center flex-shrink-0"><Zap className="h-5 w-5 text-emerald-700" /></div>
            <div>
              <p className="font-bold text-sm text-emerald-700">Execute Settlement</p>
              <p className="text-xs mt-0.5 leading-relaxed text-emerald-600">Token ACTIVE — expires {formatDate(tokenQ.data.exp)}. Run the 8-gate execution gateway before it expires.</p>
            </div>
          </div>
          <button onClick={() => executeMut.mutate()} disabled={executeMut.isPending}
            className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold whitespace-nowrap transition-colors flex-shrink-0">
            <Zap className="h-3.5 w-3.5" /> {executeMut.isPending ? "Executing…" : "Execute 8-Gate Check"}
          </button>
        </div>
      )}

      {/* ── Pipeline tracker ─────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-4">Pipeline Progress</p>
        <div className="flex items-start gap-0">
          {PIPELINE_STAGES.map((stage, i) => {
            const n = i + 1;
            const done = n < completedStages;
            const active = n === completedStages;
            const Icon = stage.icon;
            return (
              <div key={stage.label} className="flex items-start flex-1 min-w-0">
                <div className="flex flex-col items-center gap-1.5 flex-1 min-w-[54px]">
                  <div className={cn("h-9 w-9 rounded-full flex items-center justify-center flex-shrink-0 transition-all",
                    done ? "bg-emerald-500 text-white shadow-sm" : "",
                    active ? "bg-blue-600 text-white ring-2 ring-blue-200 ring-offset-1 shadow-sm" : "",
                    !done && !active ? "bg-slate-100 text-slate-300" : "")}>
                    {done ? <CheckCircle2 className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                  </div>
                  <div className="text-center hidden sm:block">
                    <p className={cn("text-[9px] font-semibold leading-tight", done ? "text-emerald-600" : active ? "text-blue-600" : "text-slate-300")}>{stage.label}</p>
                    {active && <p className="text-[8px] font-bold text-blue-500 bg-blue-50 rounded-full px-1 mt-0.5">NOW</p>}
                  </div>
                </div>
                {i < PIPELINE_STAGES.length - 1 && <div className={cn("h-0.5 mt-4 flex-1 mx-0.5 transition-colors", done ? "bg-emerald-400" : "bg-slate-200")} />}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Line-item breakdown (only shown when the claim has multiple lines) ── */}
      {!!linesQ.data?.length && (
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <p className="text-sm font-bold text-slate-800 mb-3">Line-Item Breakdown</p>
          <div className="divide-y divide-slate-50">
            {linesQ.data.map(l => (
              <div key={l.id} className="flex items-center justify-between py-2 text-sm">
                <span className="text-slate-600">{l.line_number}. {l.description || "—"}</span>
                <span className="font-semibold text-slate-800">{formatCurrency(l.claimed_amount, l.currency)}</span>
              </div>
            ))}
            <div className="flex items-center justify-between py-2 text-sm font-bold">
              <span>Total</span>
              <span>{formatCurrency(linesQ.data.reduce((s, l) => s + l.claimed_amount, 0), linesQ.data[0]?.currency ?? cs.currency)}</span>
            </div>
          </div>
        </div>
      )}

      {/* ── Artifact cards ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard title="Evidence Bundle" icon={FileText} status={stageStatus(4)}>
          {evQ.data ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5 text-center">
                  <p className="text-[9px] text-slate-400 uppercase font-semibold">Documents</p>
                  <p className="text-sm font-bold text-slate-700 mt-0.5">{evQ.data.item_count}</p>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5">
                  <p className="text-[9px] text-slate-400 uppercase font-semibold">Merkle Root</p>
                  <code className="text-[9px] font-mono text-purple-700 break-all">{evQ.data.merkle_root?.slice(0,16)}…</code>
                </div>
              </div>
              {evQ.data.items?.map(it => (
                <div key={it.id} className="flex items-center gap-2 text-[10px] py-1.5 border-b border-slate-50 last:border-0">
                  <CheckCircle2 className="h-3 w-3 text-emerald-500 flex-shrink-0" />
                  <span className="font-mono text-purple-700 w-28 flex-shrink-0 text-[10px]">{it.item_type}</span>
                  <code className="text-slate-400 font-mono text-[9px] truncate">{it.leaf_hash?.slice(0, 20)}…</code>
                </div>
              ))}
            </div>
          ) : <p className="text-xs text-slate-400 flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> Evidence not yet collected</p>}
        </SectionCard>

        <SectionCard title="AI Reasoning (SC-002)" icon={Brain} status={stageStatus(5)}>
          {findQ.data ? (
            <div className="space-y-3">
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <p className={cn("text-3xl font-bold", findQ.data.confidence >= 0.9 ? "text-emerald-600" : "text-amber-600")}>{(findQ.data.confidence * 100).toFixed(0)}%</p>
                  <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide">Rule Score</p>
                </div>
                {findQ.data.ai_confidence != null && (
                  <div className="text-center">
                    <p className={cn("text-3xl font-bold", findQ.data.ai_confidence >= 0.9 ? "text-blue-600" : "text-amber-600")}>
                      {(findQ.data.ai_confidence * 100).toFixed(0)}%
                    </p>
                    <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide">AI Score</p>
                  </div>
                )}
                <div className="flex-1 rounded-lg bg-emerald-50 border border-emerald-100 px-3 py-2">
                  <p className="text-xs font-bold text-emerald-700">Liability + policy-cap scored</p>
                  <p className="text-[10px] text-emerald-600 mt-0.5">Weighted rule-based scoring (SC-002)</p>
                  {findQ.data.risk_level && (
                    <span className={cn("inline-block mt-1.5 text-[10px] font-bold px-2 py-0.5 rounded border",
                      findQ.data.risk_level === "HIGH"   ? "bg-red-50    border-red-200    text-red-700"    :
                      findQ.data.risk_level === "MEDIUM" ? "bg-amber-50  border-amber-200  text-amber-700"  :
                                                           "bg-emerald-50 border-emerald-200 text-emerald-700")}>
                      AI Risk: {findQ.data.risk_level}
                    </span>
                  )}
                </div>
              </div>
              {findQ.data.ai_reasoning && (
                <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2.5">
                  <p className="text-[9px] text-blue-500 font-bold uppercase tracking-wide mb-1">AI Reasoning</p>
                  <p className="text-[11px] text-blue-800 leading-relaxed">{findQ.data.ai_reasoning}</p>
                </div>
              )}
              {Object.entries(findQ.data.trace ?? {}).filter(([k]) => k !== "weighted_average").map(([k, v]) => (
                <div key={k} className="flex items-center gap-2 rounded-lg bg-slate-50 border border-slate-100 px-3 py-2 text-[10px]">
                  <span className="font-mono text-purple-700 flex-1">{k}</span>
                  <span className="text-slate-400">conf {(v as any).confidence?.toFixed(2)} × wt {(v as any).weight?.toFixed(2)}</span>
                  <span className="font-bold text-slate-700">{((v as any).confidence * (v as any).weight).toFixed(3)}</span>
                </div>
              ))}
            </div>
          ) : <p className="text-xs text-slate-400 flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> AI analysis not yet run</p>}
        </SectionCard>

        <SectionCard title="Governance Token" icon={Lock} status={stageStatus(6)}>
          {tokenQ.data ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5 text-center">
                  <p className="text-[9px] text-slate-400 uppercase font-semibold">Scope</p>
                  <p className="text-[10px] font-bold text-slate-700 mt-0.5">{tokenQ.data.action}</p>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5 text-center">
                  <p className="text-[9px] text-slate-400 uppercase font-semibold">Amount</p>
                  <p className="text-sm font-bold text-emerald-600 mt-0.5">{formatCurrency(tokenQ.data.amount, tokenQ.data.currency)}</p>
                </div>
              </div>
              <div className={cn("flex items-center justify-between rounded-lg px-3 py-2 text-xs border", tokenQ.data.status === "ACTIVE" ? "bg-emerald-50 border-emerald-200" : "bg-slate-50 border-slate-200")}>
                <div className="flex items-center gap-1.5"><ShieldCheck className={cn("h-3.5 w-3.5", tokenQ.data.status === "ACTIVE" ? "text-emerald-600" : "text-slate-400")} /><span className="font-bold">{tokenQ.data.status}</span></div>
                <span className="text-slate-400 text-[10px]">Expires {formatDate(tokenQ.data.exp)}</span>
              </div>
            </div>
          ) : <p className="text-xs text-slate-400 flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> Token not yet issued</p>}
        </SectionCard>

        {acrQ.data && (
          <div className="bg-white rounded-xl border border-emerald-200 p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-lg bg-emerald-100 flex items-center justify-center"><Lock className="h-3.5 w-3.5 text-emerald-600" /></div>
                <p className="text-sm font-bold text-slate-700">Action Certification Record</p>
              </div>
              <button onClick={handleDownloadAcr} className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition-colors">
                <Download className="h-3.5 w-3.5" /> Download ACR
              </button>
            </div>
            <code className="text-[9px] font-mono text-purple-700 break-all">{acrQ.data.merkle_root?.slice(0, 32)}…</code>
          </div>
        )}
      </div>

      {/* ── Timeline ────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm font-bold text-slate-800">Claim Timeline</p>
          <div className="flex items-center gap-1.5 text-[10px] text-emerald-600 font-semibold"><GitBranch className="h-3 w-3" /> Append-only audit trail</div>
        </div>
        {eventsQ.isLoading ? (
          <div className="space-y-3">{[0,1,2].map(i => <div key={i} className="h-12 bg-slate-100 rounded-lg animate-pulse" />)}</div>
        ) : (eventsQ.data ?? []).length === 0 ? (
          <p className="text-xs text-slate-400">No timeline events yet.</p>
        ) : (
          <ol className="relative border-l-2 border-slate-200 ml-3 space-y-0">
            {(eventsQ.data ?? []).map((e, i) => (
              <li key={e.id} className="pl-5 pb-5 last:pb-0 relative">
                <div className={cn("absolute -left-[9px] top-0.5 h-4 w-4 rounded-full border-2 border-white flex items-center justify-center", i === 0 ? "bg-blue-600" : "bg-emerald-500")}>
                  {i === 0 ? <span className="h-1 w-1 rounded-full bg-white" /> : <CheckCircle2 className="h-2.5 w-2.5 text-white" />}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] text-slate-400">{formatDate(e.created_at)}</span>
                  {e.from_state && (<><StateBadge state={e.from_state} /><ChevronRight className="h-3 w-3 text-slate-300" /></>)}
                  <StateBadge state={e.to_state} />
                </div>
                <p className="text-[10px] text-slate-400 mt-1">by <span className="font-semibold text-slate-600">{e.actor}</span> · {e.reason.replace(/_/g, " ")}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

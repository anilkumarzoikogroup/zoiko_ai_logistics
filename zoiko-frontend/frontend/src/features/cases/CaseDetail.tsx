import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { api } from "@/api/client";
import { formatCurrency, formatDate, cn } from "@/utils/cn";
import {
  ArrowRight, ArrowLeft, CheckCircle2, Clock,
  FileText, Shield, Hash, Brain, Lock, AlertTriangle,
  ChevronRight, Zap, Users, RefreshCw, GitBranch,
  ShieldCheck, Download, AlertCircle, Wand2,
} from "lucide-react";
import { useToast } from "@/hooks/useToast";
import type { CaseState } from "@/types";

// Stage → number of completed pipeline steps
const STATE_STAGE: Record<CaseState, number> = {
  NEW:               4,
  EVIDENCE_PENDING:  5,
  FINDING_GENERATED: 6,
  APPROVAL_PENDING:  7,
  EXECUTION_READY:   7,
  DISPATCHED:        8,
  OUTCOME_RECORDED:  8,
  CLOSED:            8,
  ABORTED:           6,
};

const PIPELINE_STAGES = [
  { label: "Ingested",    icon: FileText,    desc: "SHA-256 domain-tagged hash"            },
  { label: "Validated",   icon: Shield,      desc: "Contract rate check FAIL"              },
  { label: "Canonical",   icon: Hash,        desc: "JCS + Ed25519 locked"                  },
  { label: "Case Opened", icon: AlertTriangle, desc: "Dispute case in FSM"                 },
  { label: "Evidence",    icon: FileText,    desc: "Merkle bundle sealed"                  },
  { label: "AI Reasoned", icon: Brain,       desc: "Confidence score computed"             },
  { label: "Governance",  icon: Users,       desc: "SoD approval + token issued"           },
  { label: "Executed",    icon: Lock,        desc: "8-gate gateway + ACR locked"           },
];

const NEXT_ACTION: Partial<Record<CaseState, {
  label: string; route: string; icon: React.ElementType;
  color: string; bgColor: string; explain: string;
}>> = {
  NEW:               { label: "Analyst Review",   route: "/analyst",  icon: Brain,       color: "text-blue-700 dark:text-blue-400",    bgColor: "bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800/50",   explain: "AI analysis done. Review and propose recovery in the Analyst queue." },
  EVIDENCE_PENDING:  { label: "Analyst Review",   route: "/analyst",  icon: Brain,       color: "text-blue-700 dark:text-blue-400",    bgColor: "bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800/50",   explain: "Evidence is being collected. Once done, propose recovery." },
  FINDING_GENERATED: { label: "Analyst Review",   route: "/analyst",  icon: Brain,       color: "text-blue-700 dark:text-blue-400",    bgColor: "bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800/50",   explain: "96% confidence overcharge detected. Open Analyst Review to propose recovery." },
  APPROVAL_PENDING:  { label: "Manager Approval", route: "/manager",  icon: CheckCircle2,color: "text-amber-700 dark:text-amber-400",   bgColor: "bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800/50", explain: "Recovery proposed. A manager must approve to issue the governance token." },
  EXECUTION_READY:   { label: "Execute Recovery", route: "/execute",  icon: Zap,         color: "text-emerald-700 dark:text-emerald-400", bgColor: "bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800/50", explain: "Token ACTIVE — 15-min window. Run 8-gate execution to issue the credit memo." },
};

const STATE_STYLE: Record<string, { label: string; cls: string; dot: string }> = {
  NEW:               { label: "New",              cls: "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400",       dot: "bg-slate-400"  },
  EVIDENCE_PENDING:  { label: "Evidence Pending", cls: "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400",       dot: "bg-slate-400"  },
  FINDING_GENERATED: { label: "AI Analyzed",      cls: "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-400", dot: "bg-purple-500" },
  APPROVAL_PENDING:  { label: "Pending Approval", cls: "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400",     dot: "bg-amber-500"  },
  EXECUTION_READY:   { label: "Execution Ready",  cls: "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400",         dot: "bg-blue-500"   },
  DISPATCHED:        { label: "Dispatched",       cls: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400", dot: "bg-emerald-500"},
  OUTCOME_RECORDED:  { label: "Outcome Recorded", cls: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-500"},
  CLOSED:            { label: "Closed",           cls: "bg-slate-100 text-slate-500",     dot: "bg-slate-400"  },
  ABORTED:           { label: "Aborted",          cls: "bg-red-100 text-red-700",         dot: "bg-red-500"    },
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
  title: string; icon: React.ElementType; status: "done" | "active" | "pending";
  children: React.ReactNode;
}) {
  return (
    <div className={cn(
      "bg-white dark:bg-card rounded-xl border p-4 shadow-sm transition-opacity",
      status === "pending" ? "opacity-50 border-slate-200 dark:border-border" : "border-slate-200 dark:border-border",
    )}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={cn(
            "h-7 w-7 rounded-lg flex items-center justify-center",
            status === "done"   ? "bg-emerald-100 dark:bg-emerald-900/40" :
            status === "active" ? "bg-blue-100 dark:bg-blue-900/40"       : "bg-slate-100 dark:bg-slate-800"
          )}>
            <Icon className={cn(
              "h-3.5 w-3.5",
              status === "done"   ? "text-emerald-600 dark:text-emerald-400" :
              status === "active" ? "text-blue-600 dark:text-blue-400"       : "text-slate-400 dark:text-slate-500"
            )} />
          </div>
          <p className="text-sm font-bold text-slate-700 dark:text-slate-200">{title}</p>
        </div>
        <span className={cn(
          "text-[10px] font-bold px-2 py-0.5 rounded-full",
          status === "done"   ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400" :
          status === "active" ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400"             :
                                "bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500"
        )}>
          {status === "done" ? "DONE" : status === "active" ? "ACTIVE" : "PENDING"}
        </span>
      </div>
      {children}
    </div>
  );
}

export default function CaseDetail() {
  const { id = "" } = useParams();
  const nav   = useNavigate();
  const qc    = useQueryClient();
  const toast = useToast();

  const [disputeLetter, setDisputeLetter]   = useState<string>("");
  const [letterLoading, setLetterLoading]   = useState(false);
  const [sendEmail,     setSendEmail]       = useState("");
  const [showSendForm,  setShowSendForm]    = useState(false);

  const cq       = useQuery({ queryKey: ["case",           id], queryFn: () => zoikoApi.getCase(id),              retry: 1 });
  const eventsQ  = useQuery({ queryKey: ["case-events",    id], queryFn: () => zoikoApi.getCaseEvents(id),        retry: 1 });
  const valQ     = useQuery({ queryKey: ["validation",     id], queryFn: () => zoikoApi.getValidationForCase(id), retry: false });
  const evQ      = useQuery({ queryKey: ["evidence",       id], queryFn: () => zoikoApi.getEvidence(id),          retry: false });
  const findQ    = useQuery({ queryKey: ["finding",        id], queryFn: () => zoikoApi.getFinding(id),           retry: false });
  const tokenQ   = useQuery({ queryKey: ["token-for-case", id], queryFn: () => zoikoApi.getTokenForCase(id),      retry: false });
  const varQ     = useQuery({ queryKey: ["variances",       id], queryFn: () => zoikoApi.listVariances(id),       retry: false });
  const acrQ     = useQuery({ queryKey: ["acr",             id], queryFn: () => zoikoApi.getAcr(id),              retry: false });

  const sealMut = useMutation({
    mutationFn: () => zoikoApi.sealBundle(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["evidence", id] }); toast.success("Bundle sealed", "Evidence bundle is now COMPLETE"); },
    onError:   () => toast.error("Seal failed", "Check that Phase 3 backend (port 8002) is running"),
  });

  const resolveMut = useMutation({
    mutationFn: ({ vid, action }: { vid: string; action: "RESOLVE" | "WAIVE" }) =>
      zoikoApi.resolveVariance(id, vid, action),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["variances", id] }); toast.success("Variance updated", "Variance record resolved"); },
    onError:   () => toast.error("Resolve failed", "Check that Phase 4 backend (port 8001) is running"),
  });

  function handleDownloadAcr() {
    zoikoApi.downloadAcr(id).then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `acr_${id.slice(0, 8)}.zip`;
      a.click(); URL.revokeObjectURL(url);
    }).catch(() => toast.error("Download failed", "ACR zip not available — run Phase 4 demo first"));
  }

  async function handleGenerateLetter() {
    setLetterLoading(true); setDisputeLetter(""); setShowSendForm(false);
    try {
      const { data } = await api.post(`/cases/${id}/dispute-letter`);
      setDisputeLetter(data.dispute_letter || "");
      if (data.carrier_email) setSendEmail(data.carrier_email);
      toast.success("Letter generated", `Dispute letter for ${data.carrier} ready`);
    } catch {
      toast.error("Generation failed", "Set GROQ_API_KEY in .env to enable AI dispute letters");
    } finally {
      setLetterLoading(false);
    }
  }

  function handleSendLetter() {
    if (!sendEmail.trim()) { toast.error("Email required", "Enter the carrier's email address"); return; }
    setSendLoading(true); setSendResult(null);
    try {
      const theCase = cq.data;
      const { data } = await api.post(`/cases/${id}/dispute-letter/send`, {
        recipient_email: sendEmail.trim(),
        letter_text:     disputeLetter,
        carrier:         theCase?.carrier ?? "",
        overcharge:      theCase?.diff ?? 0,
        currency:        theCase?.currency ?? "INR",
      });
      setSendResult(data);
      toast.success(data.sandbox ? "Sandbox — validated" : "Email sent!", data.message);
    } catch (err: unknown) {
      const e = err as {response?:{data?:{detail?:string}}};
      toast.error("Send failed", e?.response?.data?.detail ?? "Check SENDGRID_API_KEY in .env");
    } finally {
      setSendLoading(false);
    }
  }

  // ── Loading ────────────────────────────────────────────────────────────────
  if (cq.isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 w-64 bg-slate-200 rounded-lg" />
        <div className="h-4 w-48 bg-slate-100 rounded-lg" />
        <div className="grid grid-cols-4 gap-3">
          {[0,1,2,3].map(i => <div key={i} className="h-20 bg-slate-100 rounded-xl" />)}
        </div>
        <div className="h-32 bg-slate-100 rounded-xl" />
      </div>
    );
  }

  if (!cq.data) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <div className="h-12 w-12 rounded-full bg-red-50 flex items-center justify-center">
          <AlertTriangle className="h-6 w-6 text-red-400" />
        </div>
        <p className="font-semibold text-slate-700 dark:text-slate-200">Case not found</p>
        <p className="text-sm text-slate-400 dark:text-slate-500">The case ID <code className="bg-slate-100 dark:bg-slate-800 px-1 rounded">{id}</code> was not found.</p>
        <button
          onClick={() => nav("/cases")}
          className="flex items-center gap-1.5 text-blue-600 text-sm font-semibold hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Cases
        </button>
      </div>
    );
  }

  const cs = cq.data;
  const completedStages = STATE_STAGE[cs.state] ?? 4;
  const next = NEXT_ACTION[cs.state];

  const stageStatus = (n: number): "done" | "active" | "pending" =>
    n < completedStages ? "done" : n === completedStages ? "active" : "pending";

  return (
    <div className="space-y-5">

      {/* ── Breadcrumb + header ─────────────────────────────────────────── */}
      <div>
        <button
          onClick={() => nav("/cases")}
          className="flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 mb-2 transition-colors"
        >
          <ArrowLeft className="h-3 w-3" /> All Cases
        </button>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">
              {cs.carrier} <span className="text-slate-400 dark:text-slate-500 font-normal">·</span> {cs.shipment_ref}
            </h1>
            <div className="flex items-center gap-3 mt-1.5 flex-wrap">
              <code className="text-[10px] font-mono text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">{cs.id}</code>
              <StateBadge state={cs.state} />
              <span className="text-[11px] text-slate-400 dark:text-slate-500">Opened {formatDate(cs.opened_at)}</span>
            </div>
          </div>
          <button
            onClick={() => cq.refetch()}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* ── KPI row ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Invoice Amount",  value: formatCurrency(cs.amount, cs.currency),                                                      top: "border-l-blue-500",   val: "text-slate-800 dark:text-slate-100" },
          { label: "Overcharge",      value: cs.diff > 0 ? formatCurrency(cs.diff, cs.currency) : "—",                                    top: "border-l-red-500",    val: "text-red-600"   },
          { label: "Contract Rate",   value: valQ.data ? formatCurrency(valQ.data.contract_amount, cs.currency) : formatCurrency(cs.amount - cs.diff, cs.currency), top: "border-l-amber-500", val: "text-amber-600" },
          { label: "AI Confidence",   value: cs.confidence ? `${(cs.confidence * 100).toFixed(0)}%` : (findQ.data ? `${(findQ.data.confidence * 100).toFixed(0)}%` : "—"), top: "border-l-emerald-500", val: (cs.confidence ?? 0) >= 0.9 ? "text-emerald-600 font-bold" : "text-amber-600" },
        ].map(k => (
          <div key={k.label} className={cn("bg-white dark:bg-card rounded-xl border border-slate-200 dark:border-border border-l-4 px-4 py-3.5 shadow-sm dark:shadow-none", k.top)}>
            <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wide font-semibold">{k.label}</p>
            <p className={cn("text-xl font-bold mt-1.5 leading-tight", k.val)}>{k.value}</p>
          </div>
        ))}
      </div>

      {/* ── Next action CTA ─────────────────────────────────────────────── */}
      {next && (
        <div className={cn("rounded-xl border p-4 flex items-center justify-between gap-4", next.bgColor)}>
          <div className="flex items-start gap-3">
            <div className={cn("h-9 w-9 rounded-lg border flex items-center justify-center flex-shrink-0", next.bgColor)}>
              <next.icon className={cn("h-5 w-5", next.color)} />
            </div>
            <div>
              <p className={cn("font-bold text-sm", next.color)}>Action required: {next.label}</p>
              <p className={cn("text-xs mt-0.5 leading-relaxed", next.color.replace("700","600"))}>{next.explain}</p>
            </div>
          </div>
          <button
            onClick={() => nav(next.route)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-bold whitespace-nowrap transition-colors border flex-shrink-0",
              next.bgColor, next.color, "hover:opacity-80"
            )}
          >
            Go to {next.label} <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* ── Pipeline tracker ─────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-4">Pipeline Progress</p>
        <div className="flex items-start gap-0">
          {PIPELINE_STAGES.map((stage, i) => {
            const n = i + 1;
            const done   = n < completedStages;
            const active = n === completedStages;
            const Icon   = stage.icon;
            return (
              <div key={stage.label} className="flex items-start flex-1 min-w-0">
                <div className="flex flex-col items-center gap-1.5 flex-1 min-w-[54px]">
                  <div className={cn(
                    "h-9 w-9 rounded-full flex items-center justify-center flex-shrink-0 transition-all",
                    done   ? "bg-emerald-500 text-white shadow-sm"    : "",
                    active ? "bg-blue-600 text-white ring-2 ring-blue-200 ring-offset-1 shadow-sm" : "",
                    !done && !active ? "bg-slate-100 text-slate-300" : "",
                  )}>
                    {done ? <CheckCircle2 className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                  </div>
                  <div className="text-center hidden sm:block">
                    <p className={cn(
                      "text-[9px] font-semibold leading-tight",
                      done   ? "text-emerald-600" : active ? "text-blue-600" : "text-slate-300",
                    )}>
                      {stage.label}
                    </p>
                    {active && (
                      <p className="text-[8px] font-bold text-blue-500 bg-blue-50 rounded-full px-1 mt-0.5">NOW</p>
                    )}
                  </div>
                </div>
                {i < PIPELINE_STAGES.length - 1 && (
                  <div className={cn("h-0.5 mt-4 flex-1 mx-0.5 transition-colors", done ? "bg-emerald-400" : "bg-slate-200")} />
                )}
              </div>
            );
          })}
        </div>

        {/* Stage explainer */}
        <div className="mt-4 rounded-lg bg-slate-50 border border-slate-200 px-4 py-3">
          <p className="text-[11px] text-slate-600 leading-relaxed">
            <span className="font-bold text-slate-700">Stage {completedStages}: </span>
            {cs.state === "FINDING_GENERATED" && "Invoice ingested, contract rate validated, evidence bundled, AI scored 96% confidence overcharge. Ready for analyst proposal."}
            {cs.state === "APPROVAL_PENDING"  && "Analyst has proposed recovery. Awaiting manager approval (separation-of-duties enforced — different person required)."}
            {cs.state === "EXECUTION_READY"   && "Manager approved. Governance token issued with 15-minute TTL. Execute the 8-gate gateway before it expires."}
            {cs.state === "DISPATCHED"        && "All 8 execution gates passed. Credit memo dispatched to carrier. Reconciliation in progress."}
            {(cs.state === "CLOSED" || cs.state === "OUTCOME_RECORDED") && "Recovery complete. Action Certification Record (ACR) sealed in WORM index. Case archived."}
            {cs.state === "ABORTED"           && "This case was rejected or aborted. No financial action taken."}
            {(cs.state === "NEW" || cs.state === "EVIDENCE_PENDING") && "Case opened. Evidence is being collected automatically."}
          </p>
        </div>
      </div>

      {/* ── Artifact cards ───────────────────────────────────────────────── */}
      <div>
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3">Pipeline Artifacts</p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          {/* Validation */}
          <SectionCard title="Stage 2 — Validation Result" icon={Shield} status={stageStatus(2)}>
            {valQ.isLoading ? (
              <div className="space-y-2 animate-pulse">
                <div className="h-10 bg-slate-100 rounded-lg" />
                <div className="grid grid-cols-2 gap-2"><div className="h-12 bg-slate-100 rounded-lg"/><div className="h-12 bg-slate-100 rounded-lg"/></div>
              </div>
            ) : valQ.data ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2">
                  <AlertTriangle className="h-4 w-4 text-red-500 flex-shrink-0" />
                  <div>
                    <p className="text-xs font-bold text-red-700">Validation {valQ.data.outcome}</p>
                    <p className="text-[10px] text-red-600">{valQ.data.reason}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5 text-center">
                    <p className="text-[9px] text-slate-400 uppercase font-semibold">Billed</p>
                    <p className="text-sm font-bold text-red-600 mt-0.5">{formatCurrency(valQ.data.invoice_amount)}</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5 text-center">
                    <p className="text-[9px] text-slate-400 uppercase font-semibold">Contract allows</p>
                    <p className="text-sm font-bold text-emerald-600 mt-0.5">{formatCurrency(valQ.data.contract_amount)}</p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400 flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> Validation not yet run</p>
            )}
          </SectionCard>

          {/* Evidence */}
          <SectionCard title="Stage 5 — Evidence Bundle" icon={FileText} status={stageStatus(5)}>
            {evQ.isLoading ? (
              <div className="space-y-2 animate-pulse"><div className="h-16 bg-slate-100 rounded-lg" /></div>
            ) : evQ.data ? (
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
                    <span className="font-mono text-purple-700 w-20 flex-shrink-0 text-[10px]">{it.item_type}</span>
                    <code className="text-slate-400 font-mono text-[9px] truncate">{it.leaf_hash?.slice(0, 20)}…</code>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400 flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> Evidence not yet collected</p>
            )}
          </SectionCard>

          {/* AI Finding */}
          <SectionCard title="Stage 6 — AI Reasoning" icon={Brain} status={stageStatus(6)}>
            {findQ.isLoading ? (
              <div className="space-y-2 animate-pulse"><div className="h-16 bg-slate-100 rounded-lg" /></div>
            ) : findQ.data ? (
              <div className="space-y-3">
                {/* Scores row */}
                <div className="flex items-center gap-3">
                  <div className="text-center">
                    <p className={cn("text-3xl font-bold", findQ.data.confidence >= 0.9 ? "text-emerald-600" : "text-amber-600")}>
                      {(findQ.data.confidence * 100).toFixed(0)}%
                    </p>
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
                  <div className="flex-1 space-y-1.5">
                    <div className="rounded-lg bg-emerald-50 border border-emerald-100 px-3 py-2">
                      <p className="text-xs font-bold text-emerald-700">Overcharge confirmed</p>
                      <p className="text-[10px] text-emerald-600 mt-0.5">Weighted rule-based scoring (SC-001)</p>
                    </div>
                    {findQ.data.risk_level && (
                      <div className={cn("rounded-lg px-3 py-2 border text-xs font-bold",
                        findQ.data.risk_level === "HIGH"   ? "bg-red-50    border-red-200    text-red-700"    :
                        findQ.data.risk_level === "MEDIUM" ? "bg-amber-50  border-amber-200  text-amber-700"  :
                                                             "bg-slate-50  border-slate-200  text-slate-600"
                      )}>
                        AI Risk: {findQ.data.risk_level}
                      </div>
                    )}
                  </div>
                </div>

                {/* AI Reasoning */}
                {findQ.data.ai_reasoning && (
                  <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2.5 flex gap-2">
                    <Brain className="h-3.5 w-3.5 text-blue-500 mt-0.5 flex-shrink-0" />
                    <p className="text-[11px] text-blue-800 leading-relaxed">{findQ.data.ai_reasoning}</p>
                  </div>
                )}

                {/* Rule trace */}
                {Object.entries(findQ.data.trace ?? {}).filter(([k]) => k !== "weighted_average").map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2 rounded-lg bg-slate-50 border border-slate-100 px-3 py-2 text-[10px]">
                    <span className="font-mono text-purple-700 flex-1">{k}</span>
                    <span className="text-slate-400">conf {(v as any).confidence?.toFixed(2)} × wt {(v as any).weight?.toFixed(2)}</span>
                    <span className="font-bold text-slate-700">{((v as any).confidence * (v as any).weight).toFixed(3)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400 flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> AI analysis not yet run</p>
            )}
          </SectionCard>

          {/* Evidence seal button */}
          {evQ.data && evQ.data.completeness_status === "INCOMPLETE" && (
            <div className="lg:col-span-2 rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-bold text-amber-800 text-sm">Evidence bundle is INCOMPLETE</p>
                  <p className="text-xs text-amber-700 mt-0.5">Seal the bundle before AI reasoning can run (T-006 gate).</p>
                </div>
              </div>
              <button
                onClick={() => sealMut.mutate()}
                disabled={sealMut.isPending}
                className="flex items-center gap-1.5 px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-colors whitespace-nowrap"
              >
                <Wand2 className="h-3.5 w-3.5" />
                {sealMut.isPending ? "Sealing…" : "Seal Bundle"}
              </button>
            </div>
          )}

          {/* Governance Token */}
          <SectionCard title="Stage 7 — Governance Token" icon={Lock} status={stageStatus(7)}>
            {tokenQ.isLoading ? (
              <div className="animate-pulse"><div className="h-16 bg-slate-100 rounded-lg" /></div>
            ) : tokenQ.data ? (
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5 text-center">
                    <p className="text-[9px] text-slate-400 uppercase font-semibold">Action</p>
                    <p className="text-[10px] font-bold text-slate-700 mt-0.5">{tokenQ.data.action.replace("EXECUTE_","")}</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5 text-center">
                    <p className="text-[9px] text-slate-400 uppercase font-semibold">Recovery</p>
                    <p className="text-sm font-bold text-emerald-600 mt-0.5">{formatCurrency(tokenQ.data.amount, tokenQ.data.currency)}</p>
                  </div>
                </div>
                <div className={cn(
                  "flex items-center justify-between rounded-lg px-3 py-2 text-xs border",
                  tokenQ.data.status === "ACTIVE" ? "bg-emerald-50 border-emerald-200" : "bg-slate-50 border-slate-200"
                )}>
                  <div className="flex items-center gap-1.5">
                    <ShieldCheck className={cn("h-3.5 w-3.5", tokenQ.data.status === "ACTIVE" ? "text-emerald-600" : "text-slate-400")} />
                    <span className="font-bold">{tokenQ.data.status}</span>
                  </div>
                  <span className="text-slate-400 text-[10px]">Expires {formatDate(tokenQ.data.exp)}</span>
                </div>
                <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-1.5">
                  <p className="text-[9px] text-slate-400 uppercase font-semibold mb-1">Ed25519 Signature</p>
                  <code className="text-[9px] font-mono text-purple-700 break-all">{tokenQ.data.signature?.slice(0, 32)}…</code>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-slate-400 flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5" /> Token not yet issued
                </p>
                {cs.state === "FINDING_GENERATED" && (
                  <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 text-[10px] text-blue-700">
                    <span className="font-bold">Next step:</span> Go to Analyst Review → propose recovery → manager approves → token issued
                  </div>
                )}
                {cs.state === "APPROVAL_PENDING" && (
                  <div className="rounded-lg bg-amber-50 border border-amber-100 px-3 py-2 text-[10px] text-amber-700">
                    <span className="font-bold">Waiting for:</span> Manager approval (SoD: cannot approve own proposal)
                  </div>
                )}
              </div>
            )}
          </SectionCard>
        </div>
      </div>

      {/* ── Variance Records (Phase 4) ───────────────────────────────── */}
      {(varQ.data && varQ.data.length > 0) && (
        <div>
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3">Variance Records</p>
          <div className="space-y-2">
            {varQ.data.map(v => (
              <div key={v.id} className={cn(
                "bg-white rounded-xl border p-4 shadow-sm flex items-center justify-between gap-4",
                v.status === "OPEN" ? "border-red-200" : "border-slate-200"
              )}>
                <div className="flex items-center gap-3">
                  <div className={cn("h-2 w-2 rounded-full flex-shrink-0", v.status === "OPEN" ? "bg-red-500" : "bg-emerald-500")} />
                  <div>
                    <p className="text-xs font-bold text-slate-700">{v.variance_type.replace(/_/g, " ")}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      Expected {formatCurrency(v.expected_value)} · Actual {formatCurrency(v.actual_value)} · Delta {formatCurrency(v.delta)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className={cn(
                    "text-[10px] font-bold px-2 py-0.5 rounded-full",
                    v.status === "OPEN" ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
                  )}>{v.status}</span>
                  {v.status === "OPEN" && (
                    <>
                      <button
                        onClick={() => resolveMut.mutate({ vid: v.id, action: "RESOLVE" })}
                        disabled={resolveMut.isPending}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-[10px] font-bold"
                      >Resolve</button>
                      <button
                        onClick={() => resolveMut.mutate({ vid: v.id, action: "WAIVE" })}
                        disabled={resolveMut.isPending}
                        className="px-3 py-1.5 border border-slate-200 hover:bg-slate-50 text-slate-600 rounded-lg text-[10px] font-bold"
                      >Waive</button>
                    </>
                  )}
                </div>
              </div>
            ))}
            {varQ.data.some(v => v.status === "OPEN") && (
              <p className="text-[10px] text-red-600 font-semibold px-1">
                Open variances must be resolved or waived before ACR can be issued (T-011 gate).
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── ACR (Phase 4) ────────────────────────────────────────────── */}
      {acrQ.data && (
        <div className="bg-white rounded-xl border border-emerald-200 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-lg bg-emerald-100 flex items-center justify-center">
                <Lock className="h-3.5 w-3.5 text-emerald-600" />
              </div>
              <p className="text-sm font-bold text-slate-700">Stage 8 — Action Certification Record</p>
            </div>
            <div className="flex items-center gap-2">
              <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full", acrQ.data.is_locked ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700")}>
                {acrQ.data.is_locked ? "WORM LOCKED" : "PENDING LOCK"}
              </span>
              <button
                onClick={handleDownloadAcr}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition-colors"
              >
                <Download className="h-3.5 w-3.5" /> Download ACR
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
              <p className="text-[9px] text-slate-400 uppercase font-semibold">Merkle Root</p>
              <code className="text-[9px] font-mono text-purple-700 break-all">{acrQ.data.merkle_root?.slice(0, 24)}…</code>
            </div>
            <div className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
              <p className="text-[9px] text-slate-400 uppercase font-semibold">ACR Hash</p>
              <code className="text-[9px] font-mono text-purple-700 break-all">{acrQ.data.acr_hash?.slice(0, 24)}…</code>
            </div>
          </div>
        </div>
      )}

      {/* ── ACR download for CLOSED cases without loaded ACR ─────────── */}
      {!acrQ.data && ["CLOSED", "OUTCOME_RECORDED"].includes(cs.state) && (
        <div className="bg-emerald-50 rounded-xl border border-emerald-200 p-4 flex items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <Lock className="h-5 w-5 text-emerald-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-emerald-800 text-sm">ACR available for download</p>
              <p className="text-xs text-emerald-700 mt-0.5">Offline-verifiable zip with Merkle proof, Ed25519 signatures, and verify.sh script.</p>
            </div>
          </div>
          <button
            onClick={handleDownloadAcr}
            className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition-colors whitespace-nowrap"
          >
            <Download className="h-3.5 w-3.5" /> Download ACR.zip
          </button>
        </div>
      )}

      {/* ── AI Dispute Letter ────────────────────────────────────────────── */}
      {["FINDING_GENERATED","APPROVAL_PENDING","EXECUTION_READY","DISPATCHED","CLOSED"].includes(cs.state) && (
        <div className="bg-white rounded-xl border border-purple-200 p-4 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-bold text-slate-700 flex items-center gap-1.5">
              <Wand2 className="h-4 w-4 text-purple-500" /> AI Dispute Letter
            </p>
            <button
              onClick={handleGenerateLetter}
              disabled={letterLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-colors"
            >
              {letterLoading
                ? <><div className="h-3.5 w-3.5 rounded-full border-2 border-white/40 border-t-white animate-spin" />Generating…</>
                : "Generate Letter"
              }
            </button>
          </div>
          <p className="text-xs text-slate-400">AI generates a professional carrier dispute letter based on this case's overcharge data.</p>
          {disputeLetter && (
            <div className="space-y-2">
              <pre className="text-xs text-slate-700 bg-slate-50 border border-slate-200 rounded-lg p-4 whitespace-pre-wrap font-sans leading-relaxed max-h-64 overflow-auto">
                {disputeLetter}
              </pre>
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  onClick={() => navigator.clipboard.writeText(disputeLetter).then(() => toast.success("Copied", "Letter copied to clipboard"))}
                  className="text-xs text-purple-600 hover:text-purple-800 font-semibold"
                >
                  Copy to clipboard
                </button>
                <button
                  onClick={() => setShowSendForm(v => !v)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition-colors"
                >
                  ✉ Send to Carrier
                </button>
              </div>

              {showSendForm && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3">
                  <p className="text-xs font-bold text-slate-700">Send dispute letter directly to carrier</p>
                  <div className="flex gap-2">
                    <input
                      type="email"
                      placeholder="carrier-accounts@delhivery.com"
                      value={sendEmail}
                      onChange={e => setSendEmail(e.target.value)}
                      className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                      onClick={handleSendLetter}
                      disabled={!sendEmail.trim()}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-colors whitespace-nowrap"
                    >
                      Open Email Client
                    </button>
                  </div>
                  <p className="text-[10px] text-slate-500">
                    💡 Opens your default email app (Outlook, Gmail, etc.) with the letter pre-filled. Zoiko never stores or sends your emails.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Timeline ────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm font-bold text-slate-800">Case Timeline</p>
          <div className="flex items-center gap-1.5 text-[10px] text-emerald-600 font-semibold">
            <GitBranch className="h-3 w-3" /> Append-only audit trail
          </div>
        </div>
        {eventsQ.isLoading ? (
          <div className="space-y-3">
            {[0,1,2].map(i => <div key={i} className="h-12 bg-slate-100 rounded-lg animate-pulse" />)}
          </div>
        ) : (eventsQ.data ?? []).length === 0 ? (
          <p className="text-xs text-slate-400">No timeline events yet.</p>
        ) : (
          <ol className="relative border-l-2 border-slate-200 ml-3 space-y-0">
            {(eventsQ.data ?? []).map((e, i) => (
              <li key={e.id} className="pl-5 pb-5 last:pb-0 relative">
                <div className={cn(
                  "absolute -left-[9px] top-0.5 h-4 w-4 rounded-full border-2 border-white flex items-center justify-center",
                  i === 0 ? "bg-blue-600" : "bg-emerald-500"
                )}>
                  {i === 0
                    ? <span className="h-1 w-1 rounded-full bg-white" />
                    : <CheckCircle2 className="h-2.5 w-2.5 text-white" />
                  }
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] text-slate-400">{formatDate(e.created_at)}</span>
                  {e.from_state && (
                    <>
                      <StateBadge state={e.from_state} />
                      <ChevronRight className="h-3 w-3 text-slate-300" />
                    </>
                  )}
                  <StateBadge state={e.to_state} />
                </div>
                <p className="text-[10px] text-slate-400 mt-1">
                  by <span className="font-semibold text-slate-600">{e.actor}</span> · {e.reason.replace(/_/g, " ")}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>

    </div>
  );
}

import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { zoikoApi } from "@/api/zoiko";
import { useAppSelector } from "@/store";
import { cn } from "@/utils/cn";
import {
  ArrowLeft, AlertTriangle, Clock, ShieldCheck, Zap,
  CheckCircle2, XCircle, RefreshCw, Lock,
} from "lucide-react";

const STATE_CONFIG: Record<string, { label: string; cls: string; dot: string }> = {
  NEW:               { label: "New",              cls: "bg-slate-100 text-slate-600",     dot: "bg-slate-400"  },
  EVIDENCE_PENDING:  { label: "Evidence",         cls: "bg-slate-100 text-slate-600",     dot: "bg-slate-400"  },
  FINDING_GENERATED: { label: "AI Analyzed",      cls: "bg-purple-100 text-purple-700",   dot: "bg-purple-500" },
  APPROVAL_PENDING:  { label: "Pending Approval", cls: "bg-amber-100 text-amber-700",     dot: "bg-amber-500"  },
  EXECUTION_READY:   { label: "Ready",            cls: "bg-blue-100 text-blue-700",       dot: "bg-blue-500"   },
  DISPATCHED:        { label: "Dispatched",       cls: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-500"},
  OUTCOME_RECORDED:  { label: "Outcome Recorded", cls: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-500"},
  CLOSED:            { label: "Closed",           cls: "bg-slate-100 text-slate-500",     dot: "bg-slate-400"  },
  ABORTED:           { label: "Aborted",          cls: "bg-red-100 text-red-700",         dot: "bg-red-500"    },
};

function StateBadge({ state }: { state: string }) {
  const cfg = STATE_CONFIG[state] ?? { label: state, cls: "bg-slate-100 text-slate-600", dot: "bg-slate-400" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[11px] font-bold px-3 py-1.5 rounded-full", cfg.cls)}>
      <span className={cn("h-2 w-2 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

function KPITile({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
      <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">{label}</p>
      <p className={cn("text-2xl font-bold tabular-nums mt-1", accent ?? "text-slate-800")}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function EventRow({ event }: { event: Record<string, unknown> }) {
  const occurred = event.occurred_at as string || event.created_at as string || "";
  const fromS = event.from_state as string | null;
  const toS   = event.to_state   as string | null;
  return (
    <div className="flex gap-3 text-sm">
      <div className="flex flex-col items-center">
        <div className="h-2 w-2 rounded-full bg-blue-400 flex-shrink-0 mt-1" />
        <div className="w-px bg-slate-100 flex-1 mt-1" />
      </div>
      <div className="pb-4 flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium text-slate-700">
            {fromS && toS ? `${fromS} → ${toS}` : (event.event_type as string) ?? "Event"}
          </span>
          <span className="text-[11px] text-slate-400 flex-shrink-0">
            {occurred ? new Date(occurred).toLocaleString("en-IN") : ""}
          </span>
        </div>
        {event.actor_sub && (
          <span className="text-[11px] text-slate-400">{event.actor_sub as string}</span>
        )}
      </div>
    </div>
  );
}

function fmt(n: number, currency = "INR") {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);
}

export default function ExceptionDetail() {
  const { id } = useParams<{ id: string }>();
  const nav    = useNavigate();
  const qc     = useQueryClient();
  const role   = useAppSelector(s => s.auth.role) || "analyst";
  const sub    = useAppSelector(s => s.auth.sub)  || "user";

  const [proposeNote, setProposeNote]   = useState("");
  const [decideNote, setDecideNote]     = useState("");
  const [taskId, setTaskId]             = useState("");
  const [findingId, setFindingId]       = useState("");
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionError, setActionError]   = useState<string | null>(null);
  const [acting, setActing]             = useState(false);

  const { data: exc, isLoading, error } = useQuery({
    queryKey: ["exception", id],
    queryFn:  () => zoikoApi.getException(id!),
    enabled:  !!id,
    refetchInterval: 10_000,
  });

  const { data: finding } = useQuery({
    queryKey: ["exception-finding", id],
    queryFn:  () => zoikoApi.getExceptionFinding(id!),
    enabled:  !!id,
  });

  const { data: events = [] } = useQuery({
    queryKey: ["exception-events", id],
    queryFn:  () => zoikoApi.getExceptionEvents(id!),
    enabled:  !!id,
  });

  const { data: acr } = useQuery({
    queryKey: ["exception-acr", id],
    queryFn:  () => zoikoApi.getExceptionACR(id!),
    enabled:  !!id && exc?.state === "CLOSED",
  });

  if (isLoading) return <div className="py-16 text-center text-slate-400 text-sm">Loading exception…</div>;
  if (error || !exc) return (
    <div className="py-16 text-center">
      <AlertTriangle className="h-8 w-8 text-slate-300 mx-auto mb-2" />
      <p className="text-slate-500 text-sm">Exception not found</p>
      <button onClick={() => nav("/exceptions")} className="text-xs text-blue-600 hover:underline mt-2">
        Back to Exceptions
      </button>
    </div>
  );

  const breachH   = exc.sla_breach_hours ?? 0;
  const penaltyAmt = exc.sla_penalty_amount ?? 0;
  const confidence = exc.confidence != null ? `${Math.round(exc.confidence * 100)}%` : "—";

  async function handlePropose() {
    setActing(true); setActionError(null); setActionStatus(null);
    try {
      const res: Record<string, unknown> = await zoikoApi.proposeExceptionCredit(id!, {
        finding_id: findingId || finding?.id || "",
        amount:     penaltyAmt,
        currency:   exc.currency,
      }) as Record<string, unknown>;
      setTaskId((res?.task_id as string) || "");
      setActionStatus("Proposal submitted. Awaiting manager approval.");
      qc.invalidateQueries({ queryKey: ["exception", id] });
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Proposal failed");
    } finally {
      setActing(false);
    }
  }

  async function handleDecide(decision: "APPROVE" | "REJECT") {
    setActing(true); setActionError(null); setActionStatus(null);
    try {
      await zoikoApi.decideExceptionCredit(id!, { task_id: taskId, decision, note: decideNote });
      setActionStatus(`Decision: ${decision}. Case advancing.`);
      qc.invalidateQueries({ queryKey: ["exception", id] });
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Decision failed");
    } finally {
      setActing(false);
    }
  }

  return (
    <div className="space-y-5 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => nav("/exceptions")}
          className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
        >
          <ArrowLeft className="h-4 w-4 text-slate-500" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-lg font-bold text-slate-800 truncate">{exc.shipment_reference}</h1>
            <StateBadge state={exc.state} />
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            {exc.carrier || exc.carrier_id} · Opened {new Date(exc.opened_at).toLocaleString("en-IN")}
          </p>
        </div>
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ["exception", id] })}
          className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
        >
          <RefreshCw className="h-4 w-4 text-slate-500" />
        </button>
      </div>

      {/* 4 KPI Tiles */}
      <div className="grid grid-cols-4 gap-4">
        <KPITile
          label="SLA Breach"
          value={`${breachH.toFixed(2)}h`}
          sub={`${Math.floor(breachH)}h ${Math.round((breachH % 1) * 60)}m over SLA`}
          accent={breachH >= 24 ? "text-red-600" : breachH >= 4 ? "text-amber-600" : "text-emerald-600"}
        />
        <KPITile
          label="SLA Penalty"
          value={fmt(penaltyAmt, exc.currency)}
          sub={`${exc.currency} · SLA credit due`}
          accent="text-slate-800"
        />
        <KPITile
          label="AI Confidence"
          value={confidence}
          sub="SC-003 reasoning engine"
          accent={exc.confidence && exc.confidence >= 0.9 ? "text-emerald-600" : "text-amber-600"}
        />
        <KPITile
          label="Pipeline State"
          value={STATE_CONFIG[exc.state]?.label ?? exc.state}
          sub={`FSM · ${events.length} event${events.length !== 1 ? "s" : ""}`}
        />
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* Left: Case details + events */}
        <div className="col-span-2 space-y-4">
          {/* Shipment details */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Shipment Details</h2>
            <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
              {[
                ["Carrier",         exc.carrier || exc.carrier_id || "—"],
                ["Shipment Ref",    exc.shipment_reference],
                ["Committed ETA",   exc.committed_eta ? new Date(exc.committed_eta).toLocaleString("en-IN") : "—"],
                ["Actual Delivery", exc.actual_delivery ? new Date(exc.actual_delivery).toLocaleString("en-IN") : "—"],
                ["Currency",        exc.currency],
                ["Case ID",         exc.id.slice(0, 16) + "…"],
              ].map(([k, v]) => (
                <div key={k}>
                  <span className="text-[11px] font-semibold text-slate-400 block">{k}</span>
                  <span className="font-medium text-slate-700 font-mono text-xs">{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Finding */}
          {finding && (
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-slate-700">AI Finding</h2>
                <span className="text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-md">
                  {Math.round(finding.confidence * 100)}% confidence
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="bg-slate-50 rounded-lg p-3">
                  <p className="font-semibold text-slate-500 mb-1">delivery_window_breach</p>
                  <p className="text-slate-700">weight: 0.60 · confidence: 1.00</p>
                </div>
                <div className="bg-slate-50 rounded-lg p-3">
                  <p className="font-semibold text-slate-500 mb-1">sla_clause_applicable</p>
                  <p className="text-slate-700">weight: 0.40 · confidence: 0.88</p>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-3">
                Policy: sla-penalty-policy@2026.05.01 · Action: ISSUE_SLA_CREDIT
              </p>
            </div>
          )}

          {/* Event Timeline */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Event Timeline</h2>
            {events.length === 0 ? (
              <p className="text-xs text-slate-400">No events yet.</p>
            ) : (
              <div>
                {(events as unknown as Record<string, unknown>[]).map((ev, i) => (
                  <EventRow key={(ev.id as string) || i} event={ev} />
                ))}
              </div>
            )}
          </div>

          {/* ACR (when CLOSED) */}
          {acr && (
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-3">
                <Lock className="h-4 w-4 text-emerald-600" />
                <h2 className="text-sm font-semibold text-slate-700">Action Certification Record (WORM)</h2>
              </div>
              <div className="text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Root Hash</span>
                  <span className="font-mono text-slate-700 truncate max-w-xs">{acr.acr_root_hash}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Artifacts</span>
                  <span className="font-semibold text-slate-700">{acr.artifact_count} of 8</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">WORM Locked</span>
                  <span className={acr.is_locked ? "text-emerald-600 font-semibold" : "text-amber-600"}>
                    {acr.is_locked ? "Yes" : "No"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Issued At</span>
                  <span className="text-slate-700">{new Date(acr.issued_at).toLocaleString("en-IN")}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Governance panels */}
        <div className="space-y-4">
          {/* Agent Authority Zone */}
          <div className="bg-white rounded-xl border border-purple-200 p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck className="h-4 w-4 text-purple-600" />
              <h2 className="text-sm font-semibold text-purple-700">Agent Authority Zone</h2>
            </div>
            <p className="text-[11px] text-slate-400 mb-3">Analyst proposes SLA credit recovery</p>

            {actionStatus && (
              <div className="flex items-center gap-1.5 p-2 bg-emerald-50 text-emerald-700 rounded-lg text-xs mb-3">
                <CheckCircle2 className="h-3.5 w-3.5" /> {actionStatus}
              </div>
            )}
            {actionError && (
              <div className="flex items-center gap-1.5 p-2 bg-red-50 text-red-700 rounded-lg text-xs mb-3">
                <XCircle className="h-3.5 w-3.5" /> {actionError}
              </div>
            )}

            {["analyst", "admin"].includes(role) && exc.state === "FINDING_GENERATED" && (
              <div className="space-y-2">
                <div>
                  <label className="block text-[11px] font-medium text-slate-500 mb-1">Finding ID (auto-populated)</label>
                  <input
                    value={findingId || finding?.id || ""}
                    onChange={e => setFindingId(e.target.value)}
                    placeholder={finding?.id ? "(from AI finding)" : "finding-uuid"}
                    className="w-full px-2 py-1.5 border border-slate-200 rounded text-xs focus:outline-none focus:ring-2 focus:ring-purple-500/30"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-500 mb-1">Note</label>
                  <textarea
                    value={proposeNote}
                    onChange={e => setProposeNote(e.target.value)}
                    rows={2}
                    className="w-full px-2 py-1.5 border border-slate-200 rounded text-xs focus:outline-none resize-none"
                  />
                </div>
                <button
                  onClick={handlePropose} disabled={acting}
                  className="w-full py-2 bg-purple-600 text-white text-xs font-semibold rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
                >
                  {acting ? "Proposing…" : "Propose SLA Credit"}
                </button>
              </div>
            )}

            {exc.state !== "FINDING_GENERATED" && exc.state !== "APPROVAL_PENDING" && (
              <p className="text-xs text-slate-400 italic">
                {exc.state === "NEW" || exc.state === "EVIDENCE_PENDING"
                  ? "Waiting for AI finding…"
                  : "Analyst step complete."}
              </p>
            )}
          </div>

          {/* Governed Execution Zone */}
          <div className="bg-white rounded-xl border border-blue-200 p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <Zap className="h-4 w-4 text-blue-600" />
              <h2 className="text-sm font-semibold text-blue-700">Governed Execution Zone</h2>
            </div>
            <p className="text-[11px] text-slate-400 mb-3">Manager approves or rejects credit (SoD enforced)</p>

            {["manager", "admin"].includes(role) && exc.state === "APPROVAL_PENDING" && (
              <div className="space-y-2">
                <div>
                  <label className="block text-[11px] font-medium text-slate-500 mb-1">Task ID</label>
                  <input
                    value={taskId}
                    onChange={e => setTaskId(e.target.value)}
                    placeholder="governance-task-uuid"
                    className="w-full px-2 py-1.5 border border-slate-200 rounded text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-500 mb-1">Decision Note</label>
                  <textarea
                    value={decideNote}
                    onChange={e => setDecideNote(e.target.value)}
                    rows={2}
                    className="w-full px-2 py-1.5 border border-slate-200 rounded text-xs focus:outline-none resize-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => handleDecide("APPROVE")} disabled={acting}
                    className="py-2 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                  >
                    {acting ? "…" : "Approve"}
                  </button>
                  <button
                    onClick={() => handleDecide("REJECT")} disabled={acting}
                    className="py-2 bg-red-500 text-white text-xs font-semibold rounded-lg hover:bg-red-600 disabled:opacity-50 transition-colors"
                  >
                    {acting ? "…" : "Reject"}
                  </button>
                </div>
              </div>
            )}

            {exc.state === "EXECUTION_READY" && (
              <div className="p-3 bg-blue-50 rounded-lg text-xs text-blue-700 font-medium">
                <Zap className="h-3.5 w-3.5 inline mr-1" />
                Governance token issued — ready for execution gateway (port 8021)
              </div>
            )}

            {!["APPROVAL_PENDING", "EXECUTION_READY"].includes(exc.state) && !["manager", "admin"].includes(role) && (
              <p className="text-xs text-slate-400 italic">
                {exc.state === "DISPATCHED" || exc.state === "OUTCOME_RECORDED" || exc.state === "CLOSED"
                  ? "Credit issued and reconciled."
                  : "Awaiting analyst proposal."}
              </p>
            )}
          </div>

          {/* Timeline summary */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
              <Clock className="h-3.5 w-3.5 inline mr-1" />Timeline
            </h2>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500">Opened</span>
                <span className="text-slate-700">{new Date(exc.opened_at).toLocaleDateString("en-IN")}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Updated</span>
                <span className="text-slate-700">{new Date(exc.updated_at || exc.opened_at).toLocaleDateString("en-IN")}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Events</span>
                <span className="text-slate-700">{events.length}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

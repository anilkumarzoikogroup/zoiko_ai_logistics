import React, { useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { accessorialApi } from "@/api/zoiko"
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Shield,
  ChevronRight,
  FileText,
  Zap,
  RefreshCw,
  ArrowLeft,
  Lock,
  XCircle,
} from "lucide-react"
import { cn } from "@/utils/cn"

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number, currency = "INR") {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n)
}

function shortId(id: string) {
  return id.slice(0, 8)
}

// ── State config ──────────────────────────────────────────────────────────────

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
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StateBadge({ state }: { state: string }) {
  const cfg = STATE_CONFIG[state] ?? { label: state, cls: "bg-slate-100 text-slate-600", dot: "bg-slate-400" }
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[11px] font-bold px-3 py-1.5 rounded-full", cfg.cls)}>
      <span className={cn("h-2 w-2 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  )
}

function KPITile({
  label,
  value,
  sub,
  borderColor,
  valueColor,
}: {
  label: string
  value: string
  sub?: string
  borderColor: string
  valueColor: string
}) {
  return (
    <div className={cn("bg-white rounded-xl border border-slate-200 border-l-4 p-4 shadow-sm", borderColor)}>
      <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{label}</p>
      <p className={cn("text-2xl font-bold tabular-nums mt-1", valueColor)}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  )
}

function EventRow({ event }: { event: Record<string, unknown> }) {
  const occurred = (event.occurred_at as string) || (event.created_at as string) || ""
  const fromS = event.from_state as string | null
  const toS   = event.to_state   as string | null
  return (
    <div className="flex gap-3 text-sm">
      <div className="flex flex-col items-center">
        <div className="h-2 w-2 rounded-full bg-blue-400 flex-shrink-0 mt-1" />
        <div className="w-px bg-slate-100 flex-1 mt-1" />
      </div>
      <div className="pb-4 flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="font-medium text-slate-700 text-xs">
            {fromS && toS
              ? (
                <span className="flex items-center gap-1">
                  <span className="font-mono">{fromS}</span>
                  <ChevronRight className="h-3 w-3 text-slate-400" />
                  <span className="font-mono">{toS}</span>
                </span>
              )
              : (event.event_type as string) ?? "Event"}
          </span>
          <span className="text-[11px] text-slate-400 flex-shrink-0">
            {occurred ? new Date(occurred).toLocaleString("en-IN") : ""}
          </span>
        </div>
        {(event.actor_sub as string | undefined) && (
          <p className="text-[11px] text-slate-400 mt-0.5">{event.actor_sub as string}</p>
        )}
      </div>
    </div>
  )
}

// ── Three-way reconciliation bar ──────────────────────────────────────────────

function ThreeWayBar({
  accepted,
  disputed,
  writtenOff,
  currency,
}: {
  accepted: number
  disputed: number
  writtenOff: number
  currency: string
}) {
  const total = accepted + disputed + writtenOff
  if (total === 0) return null

  const acceptedPct  = Math.round((accepted  / total) * 100)
  const disputedPct  = Math.round((disputed  / total) * 100)
  const writtenOffPct = 100 - acceptedPct - disputedPct

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-700 mb-4">3-Way Reconciliation</h2>
      <div className="h-6 rounded-full overflow-hidden flex gap-0.5">
        {acceptedPct > 0 && (
          <div
            className="h-full bg-emerald-400 transition-all duration-700"
            style={{ width: `${acceptedPct}%` }}
          />
        )}
        {disputedPct > 0 && (
          <div
            className="h-full bg-amber-400 transition-all duration-700"
            style={{ width: `${disputedPct}%` }}
          />
        )}
        {writtenOffPct > 0 && (
          <div
            className="h-full bg-slate-300 rounded-r-full transition-all duration-700"
            style={{ width: `${writtenOffPct}%` }}
          />
        )}
      </div>
      <div className="flex items-start gap-6 mt-4 text-xs">
        <div className="flex items-start gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-slate-500 font-medium">Accepted</p>
            <p className="font-bold text-slate-800 tabular-nums mt-0.5">{fmt(accepted, currency)}</p>
          </div>
        </div>
        <div className="flex items-start gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-slate-500 font-medium">Disputed</p>
            <p className="font-bold text-slate-800 tabular-nums mt-0.5">{fmt(disputed, currency)}</p>
          </div>
        </div>
        <div className="flex items-start gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-300 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-slate-500 font-medium">Written Off</p>
            <p className="font-bold text-slate-800 tabular-nums mt-0.5">{fmt(writtenOff, currency)}</p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AccessorialDetail() {
  const { id } = useParams<{ id: string }>()
  const nav = useNavigate()
  const qc  = useQueryClient()

  const [actorSub,       setActorSub]       = useState("")
  const [proposalAmount, setProposalAmount] = useState("")
  const [decisionNote,   setDecisionNote]   = useState("")
  const [actionStatus,   setActionStatus]   = useState<string | null>(null)
  const [actionError,    setActionError]    = useState<string | null>(null)

  const { data: dispute, isLoading, error } = useQuery({
    queryKey: ["accessorial-dispute", id],
    queryFn:  () => accessorialApi.getById(id!),
    enabled:  !!id,
    refetchInterval: 10_000,
  })

  const { data: finding } = useQuery({
    queryKey: ["accessorial-finding", id],
    queryFn:  () => accessorialApi.getFinding(id!),
    enabled:  !!id,
  })

  const { data: events = [] } = useQuery({
    queryKey: ["accessorial-events", id],
    queryFn:  () => accessorialApi.getEvents(id!),
    enabled:  !!id,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ["accessorial-dispute", id] })

  const proposeMut = useMutation({
    mutationFn: (data: unknown) => accessorialApi.propose(id!, data),
    onSuccess: () => {
      setActionStatus("Proposal submitted. Awaiting manager approval.")
      setActionError(null)
      invalidate()
    },
    onError: (e: unknown) => {
      setActionError(e instanceof Error ? e.message : "Proposal failed")
    },
  })

  const decideMut = useMutation({
    mutationFn: (data: unknown) => accessorialApi.decide(id!, data),
    onSuccess: () => {
      setActionStatus("Decision recorded. Case advancing.")
      setActionError(null)
      invalidate()
    },
    onError: (e: unknown) => {
      setActionError(e instanceof Error ? e.message : "Decision failed")
    },
  })

  const executeMut = useMutation({
    mutationFn: async (data: { actorSub: string }) => {
      const execResult = await accessorialApi.execute(
        dispute!.case_id,
        dispute!.token_id,
        data.actorSub,
      )
      await accessorialApi.reconcile(
        dispute!.case_id,
        (execResult as Record<string, unknown>).envelope_id as string,
        data.actorSub,
      )
      return execResult
    },
    onSuccess: () => {
      setActionStatus("Partial credit executed and reconciled.")
      setActionError(null)
      invalidate()
    },
    onError: (e: unknown) => {
      setActionError(e instanceof Error ? e.message : "Execution failed")
    },
  })

  const acrMut = useMutation({
    mutationFn: (data: { actorSub: string }) =>
      accessorialApi.issueACR(dispute!.case_id, data.actorSub),
    onSuccess: () => {
      setActionStatus("ACR issued and WORM-locked.")
      setActionError(null)
      invalidate()
    },
    onError: (e: unknown) => {
      setActionError(e instanceof Error ? e.message : "ACR issuance failed")
    },
  })

  const busy =
    proposeMut.isPending ||
    decideMut.isPending  ||
    executeMut.isPending ||
    acrMut.isPending

  // ── Loading / error states ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-20">
        <div className="h-7 w-7 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
      </div>
    )
  }

  if (error || !dispute) {
    return (
      <div className="py-16 text-center">
        <AlertCircle className="h-8 w-8 text-slate-300 mx-auto mb-2" />
        <p className="text-slate-500 text-sm">Dispute not found</p>
        <button
          onClick={() => nav("/accessorial")}
          className="text-xs text-blue-600 hover:underline mt-2"
        >
          Back to Accessorial Disputes
        </button>
      </div>
    )
  }

  // ── Derived values ──────────────────────────────────────────────────────────

  const chargeLines: Array<{
    charge_type: string
    billed_amount: number
    contracted_cap: number
    tariff_id?: string
    tariff_version?: string
    dispute_amount: number
    status: string
  }> = (dispute as Record<string, unknown>).charge_lines as typeof chargeLines ?? []

  const billedTotal     = chargeLines.reduce((s, l) => s + l.billed_amount, 0)
  const capTotal        = chargeLines.reduce((s, l) => s + l.contracted_cap, 0)
  const disputeTotal    = (dispute as Record<string, unknown>).dispute_total as number ?? 0
  const currency        = (dispute as Record<string, unknown>).currency as string ?? "INR"
  const caseState       = (dispute as Record<string, unknown>).case_state as string ?? dispute.state ?? "NEW"
  const confidence      = (finding as Record<string, unknown> | undefined)?.confidence as number ?? 0
  const findingId       = (finding as Record<string, unknown> | undefined)?.finding_id as string | undefined
  const taskId          = (dispute as Record<string, unknown>).task_id as string | undefined
  const proposerSub     = (dispute as Record<string, unknown>).proposer_sub as string | undefined
  const acrId           = (dispute as Record<string, unknown>).acr_id as string | undefined

  // Reconciliation split (available when OUTCOME_RECORDED or CLOSED)
  const acceptedAmt   = (dispute as Record<string, unknown>).accepted_amount   as number ?? capTotal
  const disputedAmt   = (dispute as Record<string, unknown>).disputed_amount   as number ?? disputeTotal
  const writtenOffAmt = (dispute as Record<string, unknown>).written_off_amount as number ?? 0

  const ruleTrace = (finding as Record<string, unknown> | undefined)?.rule_trace as Record<string, {
    confidence: number; weight: number
  }> | undefined

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5 max-w-5xl mx-auto">

      {/* ── Header ── */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => nav("/accessorial")}
          className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
          aria-label="Back to list"
        >
          <ArrowLeft className="h-4 w-4 text-slate-500" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-lg font-bold text-slate-800 truncate">
              Accessorial Dispute #{shortId(id ?? "00000000")}
            </h1>
            <StateBadge state={caseState} />
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            {(dispute as Record<string, unknown>).carrier_id as string ?? "—"} ·{" "}
            Opened{" "}
            {dispute.opened_at
              ? new Date(dispute.opened_at as string).toLocaleString("en-IN")
              : "—"}
          </p>
        </div>
        <button
          onClick={invalidate}
          className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
          aria-label="Refresh"
        >
          <RefreshCw className="h-4 w-4 text-slate-500" />
        </button>
      </div>

      {/* ── 4 KPI Tiles ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPITile
          label="Total Billed"
          value={fmt(billedTotal, currency)}
          sub="Sum of all charge lines"
          borderColor="border-l-blue-400"
          valueColor="text-blue-700"
        />
        <KPITile
          label="Contracted Cap"
          value={fmt(capTotal, currency)}
          sub="Maximum allowable"
          borderColor="border-l-emerald-400"
          valueColor="text-emerald-700"
        />
        <KPITile
          label="Dispute Amount"
          value={fmt(disputeTotal, currency)}
          sub={`${chargeLines.filter(l => l.dispute_amount > 0).length} charges over cap`}
          borderColor="border-l-red-400"
          valueColor="text-red-600"
        />
        <KPITile
          label="AI Confidence"
          value={confidence ? `${(confidence * 100).toFixed(1)}%` : "—"}
          sub="SC-005 reasoning engine"
          borderColor="border-l-indigo-400"
          valueColor={confidence >= 0.9 ? "text-indigo-700" : "text-amber-600"}
        />
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* ── Left column: tables + audit ── */}
        <div className="col-span-2 space-y-5">

          {/* ── Tariff Comparison Table ── */}
          {chargeLines.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-5 pt-5 pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-slate-400" />
                  <h2 className="text-sm font-semibold text-slate-700">Side-by-Side Tariff Comparison</h2>
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Each line compared against the contracted rate cap for this carrier route
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide bg-slate-50">
                      <th className="px-5 py-2.5 font-semibold">Charge Type</th>
                      <th className="px-4 py-2.5 text-right font-semibold">Billed</th>
                      <th className="px-4 py-2.5 text-right font-semibold">Cap</th>
                      <th className="px-4 py-2.5 font-semibold">Tariff Ref</th>
                      <th className="px-4 py-2.5 text-right font-semibold">Dispute</th>
                      <th className="px-5 py-2.5 font-semibold">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {chargeLines.map((line, i) => (
                      <tr key={i} className="hover:bg-slate-50 transition-colors">
                        <td className="px-5 py-3 font-medium text-slate-700">{line.charge_type}</td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700">
                          {fmt(line.billed_amount, currency)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-500">
                          {fmt(line.contracted_cap, currency)}
                        </td>
                        <td className="px-4 py-3">
                          {line.tariff_id ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-100 text-slate-600 rounded font-mono text-[10px]">
                              {line.tariff_id.slice(0, 8)}
                              {line.tariff_version && (
                                <span className="text-slate-400">v{line.tariff_version}</span>
                              )}
                            </span>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums">
                          {line.dispute_amount > 0 ? (
                            <span className="font-semibold text-red-600">
                              {fmt(line.dispute_amount, currency)}
                            </span>
                          ) : (
                            <span className="text-slate-300">{fmt(0, currency)}</span>
                          )}
                        </td>
                        <td className="px-5 py-3">
                          {line.status === "DISPUTED" ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-50 text-red-600 rounded-full text-[10px] font-semibold">
                              <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
                              Disputed
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-50 text-emerald-600 rounded-full text-[10px] font-semibold">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                              Within Cap
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-slate-50 border-t border-slate-200">
                      <td className="px-5 py-3 text-[11px] font-bold text-slate-500 uppercase tracking-wide">Totals</td>
                      <td className="px-4 py-3 text-right font-mono font-bold tabular-nums text-slate-700">
                        {fmt(billedTotal, currency)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono font-bold tabular-nums text-slate-500">
                        {fmt(capTotal, currency)}
                      </td>
                      <td />
                      <td className="px-4 py-3 text-right font-mono font-bold tabular-nums text-red-600">
                        {fmt(disputeTotal, currency)}
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          )}

          {/* ── 3-Way Reconciliation Bar (OUTCOME_RECORDED / CLOSED) ── */}
          {["OUTCOME_RECORDED", "CLOSED"].includes(caseState) && (
            <ThreeWayBar
              accepted={acceptedAmt}
              disputed={disputedAmt}
              writtenOff={writtenOffAmt}
              currency={currency}
            />
          )}

          {/* ── Audit Trail ── */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <Clock className="h-4 w-4 text-slate-400" />
              <h2 className="text-sm font-semibold text-slate-700">Audit Trail</h2>
              <span className="ml-auto text-[11px] text-slate-400 tabular-nums">
                {(events as unknown[]).length} event{(events as unknown[]).length !== 1 ? "s" : ""}
              </span>
            </div>
            {(events as unknown[]).length === 0 ? (
              <p className="text-xs text-slate-400">No events recorded yet.</p>
            ) : (
              <div>
                {(events as Record<string, unknown>[]).map((ev, i) => (
                  <EventRow key={(ev.id as string) || i} event={ev} />
                ))}
              </div>
            )}
          </div>

        </div>

        {/* ── Right column: AI zone + Governance zone ── */}
        <div className="space-y-4">

          {/* ── AI Agent Authority Zone ── */}
          <div className="bg-blue-50/60 rounded-xl border border-blue-200 border-dashed p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-1">
              <Shield className="h-4 w-4 text-blue-600" />
              <h2 className="text-sm font-semibold text-blue-700">AI Proposed</h2>
            </div>
            <p className="text-[11px] text-blue-500 mb-4">
              Read-only — AI reasoning output
            </p>

            {finding ? (
              <div className="space-y-3">
                {/* Confidence */}
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                    Confidence
                  </span>
                  <span className={cn(
                    "text-sm font-bold tabular-nums",
                    confidence >= 0.9 ? "text-indigo-600" : "text-amber-600"
                  )}>
                    {(confidence * 100).toFixed(1)}%
                  </span>
                </div>

                {/* Rule trace */}
                {ruleTrace ? (
                  <div className="space-y-2">
                    {Object.entries(ruleTrace).map(([rule, detail]) => (
                      <div key={rule} className="bg-white rounded-lg border border-blue-100 p-3">
                        <p className="text-[11px] font-bold text-slate-600 font-mono truncate">{rule}</p>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          confidence {detail.confidence.toFixed(2)} · weight {detail.weight.toFixed(2)}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {[
                      { name: "cap_exceeded_rule",        confidence: 1.00, weight: 0.65 },
                      { name: "tariff_clause_match_rule", confidence: 0.92, weight: 0.35 },
                    ].map(rule => (
                      <div key={rule.name} className="bg-white rounded-lg border border-blue-100 p-3">
                        <p className="text-[11px] font-bold text-slate-600 font-mono">{rule.name}</p>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          confidence {rule.confidence.toFixed(2)} · weight {rule.weight.toFixed(2)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}

                {/* Finding ID chip */}
                {findingId && (
                  <div className="flex items-center gap-2 pt-1">
                    <span className="text-[11px] text-slate-400">Finding ID:</span>
                    <span className="font-mono text-[10px] bg-white border border-blue-100 px-2 py-0.5 rounded text-blue-700">
                      {shortId(findingId)}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-400 italic">
                {["NEW", "EVIDENCE_PENDING"].includes(caseState)
                  ? "AI analysis in progress…"
                  : "Finding not available."}
              </p>
            )}
          </div>

          {/* ── Action status / error banners ── */}
          {actionStatus && (
            <div className="flex items-start gap-2 p-3 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-xl text-xs">
              <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
              <span>{actionStatus}</span>
            </div>
          )}
          {actionError && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs">
              <XCircle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
              <span>{actionError}</span>
            </div>
          )}

          {/* ── Governed Execution Zone ── */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-1">
              <Zap className="h-4 w-4 text-slate-600" />
              <h2 className="text-sm font-semibold text-slate-700">Governed Execution</h2>
            </div>
            <p className="text-[11px] text-slate-400 mb-4">
              Human-in-the-loop pipeline · SoD enforced
            </p>

            {/* Actor sub field (shared across all steps) */}
            <div className="mb-3">
              <label className="block text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wide">
                Your User ID (actor_sub)
              </label>
              <input
                value={actorSub}
                onChange={e => setActorSub(e.target.value)}
                placeholder="user@example.com"
                className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>

            {/* FINDING_GENERATED — Analyst proposes */}
            {caseState === "FINDING_GENERATED" && (
              <div className="space-y-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wide">
                    Proposed Credit Amount (₹)
                  </label>
                  <input
                    type="number"
                    value={proposalAmount || disputeTotal.toString()}
                    onChange={e => setProposalAmount(e.target.value)}
                    className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  />
                  <p className="text-[10px] text-slate-400 mt-1">
                    Pre-filled with AI dispute total — adjust for partial credit
                  </p>
                </div>
                <button
                  onClick={() =>
                    proposeMut.mutate({
                      finding_id: findingId ?? "",
                      amount:     parseFloat(proposalAmount) || disputeTotal,
                      currency,
                      actor_sub:  actorSub,
                    })
                  }
                  disabled={busy || !actorSub}
                  className="w-full py-2 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {proposeMut.isPending ? "Proposing…" : "Propose Partial Credit"}
                </button>
              </div>
            )}

            {/* APPROVAL_PENDING — Manager decides */}
            {caseState === "APPROVAL_PENDING" && (
              <div className="space-y-3">
                {taskId && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-slate-400">Task:</span>
                    <span className="font-mono text-slate-600 bg-slate-50 px-1.5 py-0.5 rounded">
                      {shortId(taskId)}…
                    </span>
                  </div>
                )}
                {proposerSub && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-slate-400">Proposed by:</span>
                    <span className="text-slate-600 truncate">{proposerSub}</span>
                  </div>
                )}
                <p className="text-[11px] text-amber-600 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                  A different user must approve (SoD enforced server-side)
                </p>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wide">
                    Decision Note
                  </label>
                  <textarea
                    value={decisionNote}
                    onChange={e => setDecisionNote(e.target.value)}
                    rows={2}
                    className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs focus:outline-none resize-none"
                    placeholder="Optional note…"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() =>
                      decideMut.mutate({
                        task_id:  taskId ?? "",
                        decision: "APPROVE",
                        note:     decisionNote,
                        actor_sub: actorSub,
                      })
                    }
                    disabled={busy || !actorSub}
                    className="py-2 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                  >
                    {decideMut.isPending ? "…" : "Approve"}
                  </button>
                  <button
                    onClick={() =>
                      decideMut.mutate({
                        task_id:  taskId ?? "",
                        decision: "REJECT",
                        note:     decisionNote,
                        actor_sub: actorSub,
                      })
                    }
                    disabled={busy || !actorSub}
                    className="py-2 bg-red-500 text-white text-xs font-semibold rounded-lg hover:bg-red-600 disabled:opacity-50 transition-colors"
                  >
                    Reject
                  </button>
                </div>
              </div>
            )}

            {/* EXECUTION_READY — Execute + reconcile */}
            {caseState === "EXECUTION_READY" && (
              <div className="space-y-3">
                <p className="text-xs text-slate-500">
                  Governance token issued. 8-gate execution check will issue the partial credit and
                  reconcile immediately.
                </p>
                <button
                  onClick={() => executeMut.mutate({ actorSub })}
                  disabled={busy || !actorSub}
                  className="w-full py-2 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
                >
                  <Zap className="h-3.5 w-3.5" />
                  {executeMut.isPending ? "Executing…" : "Execute Partial Credit"}
                </button>
              </div>
            )}

            {/* OUTCOME_RECORDED — Issue ACR */}
            {caseState === "OUTCOME_RECORDED" && (
              <div className="space-y-3">
                <p className="text-xs text-slate-500">
                  Reconciliation complete. Issue the 8-artifact Merkle ACR to WORM-lock and close
                  this case.
                </p>
                <button
                  onClick={() => acrMut.mutate({ actorSub })}
                  disabled={busy || !actorSub}
                  className="w-full py-2 bg-slate-800 text-white text-xs font-semibold rounded-lg hover:bg-slate-900 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
                >
                  <Lock className="h-3.5 w-3.5" />
                  {acrMut.isPending ? "Issuing ACR…" : "Issue ACR & Close Case"}
                </button>
              </div>
            )}

            {/* CLOSED — Show ACR confirmation */}
            {caseState === "CLOSED" && (
              <div className="rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-3 flex items-start gap-3">
                <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-emerald-700">ACR Issued — WORM Locked</p>
                  {acrId && (
                    <p className="text-[11px] text-emerald-600 mt-0.5 font-mono">
                      {shortId(acrId)}…
                    </p>
                  )}
                  <p className="text-[11px] text-emerald-500 mt-1">
                    Download from the ACR Verifier for long-term audit records
                  </p>
                </div>
              </div>
            )}

            {/* ABORTED */}
            {caseState === "ABORTED" && (
              <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-2.5 text-xs text-red-700">
                Case aborted at manager decision.
              </div>
            )}

            {/* Waiting states */}
            {["NEW", "EVIDENCE_PENDING"].includes(caseState) && (
              <p className="text-xs text-slate-400 italic">
                Waiting for AI finding to be generated…
              </p>
            )}
          </div>

        </div>
      </div>
    </div>
  )
}

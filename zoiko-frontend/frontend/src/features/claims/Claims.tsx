import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency, cn } from "@/utils/cn";
import { Search, Plus, ChevronRight, FileWarning, Zap, User, TrendingUp } from "lucide-react";
import type { ClaimState } from "@/types";

const STATE_TABS: (ClaimState | "ALL")[] = [
  "ALL", "FINDING_GENERATED", "APPROVAL_PENDING",
  "EXECUTION_READY", "DISPATCHED", "CLOSED", "ABORTED",
];

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

// Claim type display config — covers auto-created (OVERCHARGE) and
// manually submitted (DAMAGE, LOSS, DELAY, SHORTAGE, MISDELIVERY) types.
const CLAIM_TYPE_CONFIG: Record<string, { label: string; cls: string }> = {
  OVERCHARGE:       { label: "Overcharge",       cls: "bg-orange-100 text-orange-700" },
  DAMAGE:           { label: "Damage",           cls: "bg-red-100 text-red-700"       },
  LOSS:             { label: "Loss",             cls: "bg-red-100 text-red-700"       },
  LOST_SHIPMENT:    { label: "Lost",             cls: "bg-red-100 text-red-700"       },
  DELAY:            { label: "Delay",            cls: "bg-purple-100 text-purple-700" },
  DELAY_PENALTY:    { label: "Delay Penalty",    cls: "bg-purple-100 text-purple-700" },
  SHORTAGE:         { label: "Shortage",         cls: "bg-amber-100 text-amber-700"   },
  SHORT_DELIVERY:   { label: "Short Delivery",   cls: "bg-amber-100 text-amber-700"   },
  MISDELIVERY:      { label: "Misdelivery",      cls: "bg-amber-100 text-amber-700"   },
  INVOICE_DISPUTE:  { label: "Invoice Dispute",  cls: "bg-blue-100 text-blue-700"     },
  OTHER:            { label: "Other",            cls: "bg-slate-100 text-slate-600"   },
};

function StateBadge({ state }: { state: string }) {
  const cfg = STATE_CONFIG[state] ?? { label: state, cls: "bg-slate-100 text-slate-600", dot: "bg-slate-400" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[10px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap", cfg.cls)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

function ClaimTypeBadge({ type }: { type: string }) {
  const cfg = CLAIM_TYPE_CONFIG[type] ?? { label: type ?? "—", cls: "bg-slate-100 text-slate-500" };
  return (
    <span className={cn("inline-flex text-[10px] font-semibold px-2 py-0.5 rounded-md whitespace-nowrap", cfg.cls)}>
      {cfg.label}
    </span>
  );
}

function ConfidenceBadge({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-slate-300">—</span>;
  const pct = Math.round(value * 100);
  const cls = pct >= 90 ? "text-emerald-600 bg-emerald-50" : pct >= 70 ? "text-amber-600 bg-amber-50" : "text-red-600 bg-red-50";
  return <span className={cn("text-[11px] font-bold px-2 py-0.5 rounded-md", cls)}>{pct}%</span>;
}

// Auto-created claims from SC-001 have reference starting with "AUTO-"
function isAutoCreated(shipmentRef: string | null | undefined): boolean {
  return (shipmentRef ?? "").startsWith("AUTO-");
}

export default function Claims() {
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<ClaimState | "ALL">("ALL");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 50;

  const { data: paged, isLoading } = useQuery({
    queryKey: ["claims", page, filter !== "ALL" ? filter : undefined],
    queryFn:  () => zoikoApi.listClaimsPaged({
      page, page_size: PAGE_SIZE,
      state: filter !== "ALL" ? filter : undefined,
    }),
    refetchInterval: 10000,
  });

  const claims   = paged?.claims ?? [];
  const total    = paged?.total  ?? 0;
  const pages    = paged?.pages  ?? 1;

  const filtered = claims.filter(c =>
    !search ||
    c.id.includes(search) ||
    (c.carrier      ?? "").toLowerCase().includes(search.toLowerCase()) ||
    (c.shipment_ref ?? "").toLowerCase().includes(search.toLowerCase())
  );

  const byState = claims.reduce<Record<string, number>>((acc, c) => {
    acc[c.state] = (acc[c.state] ?? 0) + 1;
    return acc;
  }, {});

  const autoCount   = claims.filter(c => isAutoCreated(c.shipment_ref)).length;
  const manualCount = claims.length - autoCount;

  const tabLabel = (s: ClaimState | "ALL") => {
    if (s === "ALL") return `All (${claims.length})`;
    const cfg = STATE_CONFIG[s];
    return `${cfg?.label ?? s} (${byState[s] ?? 0})`;
  };

  return (
    <div className="space-y-5">

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Carrier Claims</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {claims.length} total · {claims.filter(c => !["CLOSED","ABORTED"].includes(c.state)).length} open
          </p>
        </div>
        <button
          onClick={() => nav("/claims/new")}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold shadow-sm shadow-blue-500/25 transition-all hover:-translate-y-0.5"
        >
          <Plus className="h-4 w-4" />
          Submit Claim
        </button>
      </div>

      {/* ── Summary cards ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Pending Approval", value: byState["APPROVAL_PENDING"] ?? 0,
            color: "border-l-amber-400 text-amber-700" },
          { label: "AI Analyzed",      value: byState["FINDING_GENERATED"] ?? 0,
            color: "border-l-purple-400 text-purple-700" },
          { label: "Dispatched",       value: (byState["DISPATCHED"] ?? 0) + (byState["OUTCOME_RECORDED"] ?? 0),
            color: "border-l-emerald-400 text-emerald-700" },
          { label: "Closed",           value: byState["CLOSED"] ?? 0,
            color: "border-l-slate-400 text-slate-600" },
        ].map(t => (
          <div key={t.label} className={cn("bg-white rounded-xl border border-slate-200 border-l-4 px-4 py-3 shadow-sm", t.color.split(" ")[0])}>
            <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">{t.label}</p>
            <p className={cn("text-2xl font-bold mt-1", t.color.split(" ")[1])}>{t.value}</p>
          </div>
        ))}
      </div>

      {/* ── Source banner — auto vs manual ────────────────────────────────── */}
      {claims.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-emerald-100 flex items-center justify-center flex-shrink-0">
              <Zap className="h-4 w-4 text-emerald-600" />
            </div>
            <div>
              <p className="text-[10px] font-semibold text-emerald-600 uppercase tracking-wide">Auto-Created</p>
              <p className="text-lg font-bold text-emerald-800">{autoCount}</p>
              <p className="text-[10px] text-emerald-500">From SC-001 overcharge execution</p>
            </div>
          </div>
          <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-blue-100 flex items-center justify-center flex-shrink-0">
              <User className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <p className="text-[10px] font-semibold text-blue-600 uppercase tracking-wide">Manually Submitted</p>
              <p className="text-lg font-bold text-blue-800">{manualCount}</p>
              <p className="text-[10px] text-blue-500">Submitted via Submit Claim form</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Recovery tip banner — show when dispatched claims exist ──────── */}
      {(byState["DISPATCHED"] ?? 0) > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-center gap-3">
          <TrendingUp className="h-4 w-4 text-amber-600 flex-shrink-0" />
          <p className="text-[12px] text-amber-800">
            <span className="font-bold">{byState["DISPATCHED"]} dispatched claim{(byState["DISPATCHED"] ?? 0) > 1 ? "s" : ""}</span>
            {" "}have recovery tracking available.{" "}
            <span className="font-semibold">Click a Dispatched row</span> to see expected recovery, payment confirmation, and proof generation.
          </p>
        </div>
      )}

      {/* ── Table ─────────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100">
          <div className="relative flex-1 max-w-xs">
            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 w-full"
              placeholder="Search by ID, carrier, claim ref…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="flex gap-0 overflow-x-auto border-b border-slate-100 px-4 scrollbar-thin">
          {STATE_TABS.map(s => (
            <button key={s} onClick={() => { setFilter(s); setPage(1); }}
              className={cn(
                "flex-shrink-0 px-3 py-2.5 text-[11px] font-semibold border-b-2 transition-colors whitespace-nowrap",
                filter === s ? "border-blue-500 text-blue-600" : "border-transparent text-slate-500 hover:text-slate-700"
              )}
            >
              {tabLabel(s)}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="divide-y divide-slate-50">
            {[0,1,2,3,4].map(i => (
              <div key={i} className="flex items-center gap-4 px-5 py-4 animate-pulse">
                <div className="h-3 w-20 bg-slate-100 rounded-full" />
                <div className="h-3 w-24 bg-slate-100 rounded-full" />
                <div className="h-3 w-32 bg-slate-100 rounded-full" />
                <div className="h-3 w-16 bg-slate-100 rounded-full ml-auto" />
                <div className="h-5 w-20 bg-slate-100 rounded-full" />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-slate-400 gap-3">
            <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center">
              <FileWarning className="h-6 w-6 text-slate-300" />
            </div>
            <div className="text-center">
              <p className="font-semibold text-slate-600 text-sm">No claims found</p>
              <p className="text-xs mt-1">Submit a carrier claim or execute an SC-001 overcharge case to auto-create one</p>
            </div>
          </div>
        ) : (
          <>
            {/* Column headers */}
            <div className="grid grid-cols-[1fr_1fr_1.5fr_1fr_1fr_1fr_1.5fr_auto] items-center gap-3 px-5 py-2 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-slate-400 border-b border-slate-100">
              <span>Case ID</span>
              <span>Carrier</span>
              <span>Claim Ref</span>
              <span>Type</span>
              <span className="text-right">Amount</span>
              <span>AI Score</span>
              <span>State</span>
              <span />
            </div>

            <div className="divide-y divide-slate-50">
              {filtered.map(c => {
                const auto = isAutoCreated(c.shipment_ref);
                const isDispatched = ["DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state);
                return (
                  <div
                    key={c.id}
                    onClick={() => nav(`/claims/${c.id}`)}
                    className={cn(
                      "grid grid-cols-[1fr_1fr_1.5fr_1fr_1fr_1fr_1.5fr_auto] items-center gap-3 px-5 py-3.5 cursor-pointer transition-colors group",
                      isDispatched ? "hover:bg-emerald-50/50" : "hover:bg-slate-50"
                    )}
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <code className="text-[11px] text-blue-600 font-mono truncate">{c.id.slice(0, 8)}</code>
                    </div>

                    <span className="text-[12px] font-semibold text-slate-700 truncate">
                      {c.carrier || "—"}
                    </span>

                    <div className="flex items-center gap-1.5 min-w-0">
                      {auto && (
                        <span title="Auto-created from SC-001 execution"
                          className="flex-shrink-0 inline-flex items-center gap-0.5 text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
                          <Zap className="h-2.5 w-2.5" /> AUTO
                        </span>
                      )}
                      <span className="text-[11px] text-slate-400 truncate">{c.shipment_ref || "—"}</span>
                    </div>

                    <span>
                      <ClaimTypeBadge type={(c as any).claim_type ?? "OVERCHARGE"} />
                    </span>

                    <span className="text-right text-[11px] text-slate-600 font-medium">
                      {formatCurrency(c.amount, c.currency)}
                    </span>

                    <span><ConfidenceBadge value={c.confidence} /></span>

                    <div className="flex items-center gap-1.5">
                      <StateBadge state={c.state} />
                      {isDispatched && (
                        <span title="Recovery tracking available"
                          className="inline-flex items-center text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
                          <TrendingUp className="h-2.5 w-2.5" />
                        </span>
                      )}
                    </div>

                    <ChevronRight className="h-4 w-4 text-slate-300 group-hover:text-slate-500 transition-colors" />
                  </div>
                );
              })}
            </div>
          </>
        )}

        {!isLoading && (
          <div className="px-5 py-3 border-t border-slate-100 flex items-center justify-between gap-3">
            <span className="text-[10px] text-slate-400">{total} total · page {page} of {pages}</span>
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                className="px-2.5 py-1 text-[11px] border border-slate-200 rounded-md text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                ‹ Prev
              </button>
              {Array.from({ length: Math.min(5, pages) }, (_, i) => {
                const p = page <= 3 ? i + 1 : page - 2 + i;
                if (p > pages) return null;
                return (
                  <button key={p} onClick={() => setPage(p)}
                    className={cn("w-7 h-7 text-[11px] rounded-md border transition-colors",
                      p === page ? "bg-blue-600 border-blue-600 text-white font-bold" : "border-slate-200 text-slate-600 hover:bg-slate-50")}>
                    {p}
                  </button>
                );
              })}
              <button onClick={() => setPage(p => Math.min(pages, p + 1))} disabled={page >= pages}
                className="px-2.5 py-1 text-[11px] border border-slate-200 rounded-md text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                Next ›
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

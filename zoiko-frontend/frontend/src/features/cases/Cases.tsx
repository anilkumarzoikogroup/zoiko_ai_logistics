import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency } from "@/utils/cn";
import { Search, Upload, AlertTriangle, X, FileText, ChevronRight } from "lucide-react";
import type { CaseState } from "@/types";

// ── Status config ─────────────────────────────────────────────────────────────
const STATUS_OPTIONS: { value: CaseState | "ALL"; label: string }[] = [
  { value: "ALL",              label: "All Statuses"      },
  { value: "NEW",              label: "New"               },
  { value: "EVIDENCE_PENDING", label: "Processing"        },
  { value: "FINDING_GENERATED",label: "AI Analyzed"       },
  { value: "APPROVAL_PENDING", label: "Pending Approval"  },
  { value: "EXECUTION_READY",  label: "Ready"             },
  { value: "DISPATCHED",       label: "Dispatched"        },
  { value: "OUTCOME_RECORDED", label: "Recovered"         },
  { value: "CLOSED",           label: "Completed"         },
  { value: "ABORTED",          label: "Rejected"          },
];

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  CLOSED:            { label: "completed",       cls: "bg-[#dcfce7] text-[#16a34a]" },
  DISPATCHED:        { label: "completed",       cls: "bg-[#dcfce7] text-[#16a34a]" },
  OUTCOME_RECORDED:  { label: "completed",       cls: "bg-[#dcfce7] text-[#16a34a]" },
  FINDING_GENERATED: { label: "ai analyzed",     cls: "bg-[#f3e8ff] text-[#7c3aed]" },
  APPROVAL_PENDING:  { label: "pending approval",cls: "bg-[#fef3c7] text-[#d97706]" },
  EXECUTION_READY:   { label: "ready",           cls: "bg-[#dbeafe] text-[#2563eb]" },
  NEW:               { label: "processing",      cls: "bg-[#f1f5f9] text-[#64748b]" },
  EVIDENCE_PENDING:  { label: "processing",      cls: "bg-[#f1f5f9] text-[#64748b]" },
  ABORTED:           { label: "rejected",        cls: "bg-[#fee2e2] text-[#dc2626]" },
};

function StatusBadge({ state }: { state: string }) {
  const s = STATUS_BADGE[state] ?? { label: state.toLowerCase(), cls: "bg-[#f1f5f9] text-[#64748b]" };
  return (
    <span className={`inline-block text-[10px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap ${s.cls}`}>
      {s.label}
    </span>
  );
}

export default function Cases() {
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const [statusFilter, setStatusFilter] = useState<CaseState | "ALL">("ALL");

  const { data: cases, isLoading } = useQuery({
    queryKey: ["cases"],
    queryFn:  () => zoikoApi.listCases(),
    refetchInterval: 5000,
  });

  const allCases = (cases || []) as any[];

  const filtered = allCases
    .filter(c => statusFilter === "ALL" || c.state === statusFilter)
    .filter(c =>
      !search ||
      (c.carrier ?? "").toLowerCase().includes(search.toLowerCase()) ||
      c.id.toLowerCase().includes(search.toLowerCase()) ||
      (c.shipment_ref ?? "").toLowerCase().includes(search.toLowerCase())
    )
    .sort((a: any, b: any) => new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime());

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" });

  return (
    <div className="space-y-5">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-extrabold text-[#1e293b]">Invoices</h1>
          <p className="text-[13px] text-slate-500 mt-0.5">All uploaded freight invoices and their audit status.</p>
        </div>
        <button
          onClick={() => nav("/cases/new")}
          className="flex items-center gap-2 px-4 py-2.5 bg-[#0d2137] hover:bg-[#1a3a5c] text-white rounded-lg text-[13px] font-bold transition-colors shadow-sm flex-shrink-0"
        >
          <Upload className="h-4 w-4" />
          Upload Invoice
        </button>
      </div>

      {/* ── Search + filter ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by carrier or invoice #..."
            className="w-full pl-10 pr-3 py-2.5 bg-white border border-[#e2e8f0] rounded-lg text-[13px] text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 transition-all"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-300 hover:text-slate-500"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <div className="relative">
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as CaseState | "ALL")}
            className="appearance-none bg-white border border-[#e2e8f0] rounded-lg pl-3 pr-8 py-2.5 text-[13px] text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 transition-all cursor-pointer"
          >
            {STATUS_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <ChevronRight className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 rotate-90 pointer-events-none" />
        </div>
      </div>

      {/* ── Table card ──────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-[#e2e8f0] shadow-[0_1px_3px_rgba(0,0,0,0.06)] overflow-hidden">

        {/* Column headers */}
        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1.2fr_auto] items-center gap-4 px-5 py-3 border-b border-[#f1f5f9]">
          {["CARRIER / INVOICE", "DATE", "AMOUNT", "ERRORS", "STATUS", ""].map(h => (
            <span key={h} className="text-[10px] font-bold uppercase tracking-widest text-[#94a3b8]">{h}</span>
          ))}
        </div>

        {/* Rows */}
        {isLoading ? (
          <div className="divide-y divide-[#f8fafc]">
            {[1,2,3,4].map(i => (
              <div key={i} className="grid grid-cols-[2fr_1fr_1fr_1fr_1.2fr_auto] gap-4 px-5 py-4 animate-pulse">
                <div className="space-y-1.5">
                  <div className="h-3 w-32 bg-slate-100 rounded" />
                  <div className="h-2.5 w-20 bg-slate-100 rounded" />
                </div>
                <div className="h-3 w-20 bg-slate-100 rounded self-center" />
                <div className="h-3 w-16 bg-slate-100 rounded self-center" />
                <div className="h-3 w-8 bg-slate-100 rounded self-center" />
                <div className="h-5 w-24 bg-slate-100 rounded-full self-center" />
                <div className="h-3 w-10 bg-slate-100 rounded self-center" />
              </div>
            ))}
          </div>

        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <div className="h-14 w-14 rounded-xl bg-[#f8fafc] border border-[#e8edf2] flex items-center justify-center">
              <FileText className="h-6 w-6 text-slate-300" />
            </div>
            <div className="text-center">
              <p className="text-[14px] font-bold text-[#374151]">
                {search || statusFilter !== "ALL" ? "No invoices match your filter" : "No invoices yet"}
              </p>
              <p className="text-[12px] text-slate-400 mt-1">
                {search || statusFilter !== "ALL"
                  ? "Try clearing the search or changing the status filter"
                  : "Upload your first freight invoice to get started"}
              </p>
            </div>
            {!search && statusFilter === "ALL" && (
              <button
                onClick={() => nav("/cases/new")}
                className="flex items-center gap-2 px-4 py-2 bg-[#0d2137] hover:bg-[#1a3a5c] text-white rounded-lg text-[12px] font-bold transition-colors mt-1"
              >
                <Upload className="h-3.5 w-3.5" /> Upload Invoice
              </button>
            )}
          </div>

        ) : (
          <div className="divide-y divide-[#f8fafc]">
            {filtered.map((c: any) => (
              <div
                key={c.id}
                className="grid grid-cols-[2fr_1fr_1fr_1fr_1.2fr_auto] items-center gap-4 px-5 py-4 hover:bg-[#fafbfc] transition-colors group"
              >
                {/* Carrier + Invoice # */}
                <div>
                  <p className="text-[13px] font-bold text-[#1e293b]">{c.carrier || "Unknown Carrier"}</p>
                  <p className="text-[11px] text-slate-400 mt-0.5 font-mono">
                    {c.id.slice(0, 8).toUpperCase()} · {fmtDate(c.opened_at)}
                  </p>
                </div>

                {/* Date */}
                <span className="text-[12px] text-slate-600">{new Date(c.opened_at).toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" })}</span>

                {/* Amount */}
                <span className="text-[13px] font-bold text-[#1e293b]">{formatCurrency(c.amount, c.currency)}</span>

                {/* Errors */}
                <span>
                  {(c.diff ?? 0) > 0
                    ? <span className="flex items-center gap-1"><AlertTriangle className="h-4 w-4 text-orange-500" /><span className="text-[11px] font-semibold text-orange-600">{formatCurrency(c.diff, c.currency)}</span></span>
                    : <span className="text-slate-300 text-[12px]">—</span>
                  }
                </span>

                {/* Status */}
                <StatusBadge state={c.state} />

                {/* Actions */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => nav(`/cases/${c.id}`)}
                    className="text-[12px] font-semibold text-[#374151] hover:text-[#1e293b] transition-colors"
                  >
                    View
                  </button>
                  <div className="h-5 w-5 rounded-full border border-[#e2e8f0] flex items-center justify-center text-slate-400 hover:border-slate-300 hover:text-slate-600 cursor-pointer transition-colors">
                    <X className="h-3 w-3" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Footer */}
        {!isLoading && filtered.length > 0 && (
          <div className="px-5 py-3 border-t border-[#f1f5f9] flex items-center justify-between">
            <span className="text-[11px] text-slate-400">
              Showing <strong className="text-slate-600">{filtered.length}</strong> of <strong className="text-slate-600">{allCases.length}</strong> invoices
            </span>
            <span className="text-[11px] text-slate-300">Auto-refreshes every 5s</span>
          </div>
        )}
      </div>
    </div>
  );
}

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  FileText,
  PlusCircle,
  AlertCircle,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import { accessorialApi } from "@/api/zoiko";

type DisputeState =
  | "FINDING_GENERATED"
  | "APPROVAL_PENDING"
  | "EXECUTION_READY"
  | "DISPATCHED"
  | "OUTCOME_RECORDED"
  | "CLOSED"
  | "ABORTED";

interface AccessorialDispute {
  case_id: string;
  invoice_reference: string;
  carrier_id: string;
  dispute_total: number;
  confidence: number;
  state: DisputeState;
  opened_at: string;
}

const STATE_PILL: Record<DisputeState, { bg: string; text: string; label: string }> = {
  FINDING_GENERATED: { bg: "bg-blue-100", text: "text-blue-700", label: "Finding Generated" },
  APPROVAL_PENDING:  { bg: "bg-amber-100", text: "text-amber-700", label: "Approval Pending" },
  EXECUTION_READY:   { bg: "bg-indigo-100", text: "text-indigo-700", label: "Execution Ready" },
  DISPATCHED:        { bg: "bg-purple-100", text: "text-purple-700", label: "Dispatched" },
  OUTCOME_RECORDED:  { bg: "bg-teal-100", text: "text-teal-700", label: "Outcome Recorded" },
  CLOSED:            { bg: "bg-emerald-100", text: "text-emerald-700", label: "Closed" },
  ABORTED:           { bg: "bg-red-100", text: "text-red-700", label: "Aborted" },
};

function StatePill({ state }: { state: DisputeState }) {
  const cfg = STATE_PILL[state] ?? {
    bg: "bg-gray-100",
    text: "text-gray-600",
    label: state,
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}
      style={{ letterSpacing: "0.02em" }}
    >
      {cfg.label}
    </span>
  );
}

function SkeletonRow() {
  return (
    <tr className="border-b border-gray-100">
      {[140, 100, 90, 72, 110, 80].map((w, i) => (
        <td key={i} className="px-4 py-3">
          <div
            className="animate-pulse bg-gray-200 rounded h-4"
            style={{ width: w }}
          />
        </td>
      ))}
      <td className="px-4 py-3 w-10" />
    </tr>
  );
}

export default function AccessorialList() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery<
    AccessorialDispute[]
  >({
    queryKey: ["accessorial-disputes"],
    queryFn: () => accessorialApi.list(),
  });

  const disputes = data ?? [];

  return (
    <div className="min-h-screen bg-gray-50" style={{ backgroundColor: "#F8F9FB" }}>
      <div className="max-w-6xl mx-auto px-6 py-8">

        {/* ── Page header ── */}
        <div className="flex items-start justify-between gap-4 mb-2">
          <div className="flex items-center gap-3">
            <h1
              className="text-2xl font-semibold text-gray-900"
              style={{ color: "#1A2233", letterSpacing: "-0.01em" }}
            >
              Accessorial Disputes
            </h1>
            {!isLoading && !isError && (
              <span className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-2 rounded-full bg-blue-100 text-blue-700 text-xs font-semibold tabular-nums">
                {disputes.length}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-gray-600 hover:bg-gray-100 border border-gray-200 transition-colors disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw
                size={14}
                className={isFetching ? "animate-spin" : ""}
              />
              Refresh
            </button>
            <Link
              to="/accessorial/new"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors shadow-sm"
            >
              <PlusCircle size={15} />
              New Dispute
            </Link>
          </div>
        </div>

        <p className="text-sm text-gray-500 mb-6" style={{ color: "#64748B" }}>
          AI-validated accessorial charge disputes against contracted tariff caps
        </p>

        {/* ── Main card ── */}
        <div
          className="rounded-xl border bg-white overflow-hidden shadow-sm"
          style={{ borderColor: "#E2E6ED" }}
        >

          {/* ── Error state ── */}
          {isError && (
            <div className="flex items-center gap-3 px-6 py-10 text-red-600">
              <AlertCircle size={20} className="shrink-0" />
              <div>
                <p className="font-medium text-sm">Failed to load disputes</p>
                <p className="text-xs text-red-500 mt-0.5">
                  {error instanceof Error ? error.message : "An unexpected error occurred."}
                </p>
              </div>
            </div>
          )}

          {/* ── Table ── */}
          {!isError && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" style={{ minWidth: 680 }}>
                <thead>
                  <tr
                    className="border-b text-left"
                    style={{ borderColor: "#E2E6ED", backgroundColor: "#F8F9FB" }}
                  >
                    {[
                      { label: "Invoice Ref", w: "w-[18%]" },
                      { label: "Carrier", w: "w-[16%]" },
                      { label: "Dispute Total", w: "w-[14%]", numeric: true },
                      { label: "Confidence", w: "w-[11%]", numeric: true },
                      { label: "State", w: "w-[18%]" },
                      { label: "Date", w: "w-[14%]" },
                    ].map((col) => (
                      <th
                        key={col.label}
                        className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-gray-400 ${col.w} ${col.numeric ? "text-right" : "text-left"}`}
                        style={{ letterSpacing: "0.06em", color: "#94A3B8" }}
                      >
                        {col.label}
                      </th>
                    ))}
                    {/* arrow col */}
                    <th className="w-10" />
                  </tr>
                </thead>

                <tbody>
                  {/* Loading skeletons */}
                  {isLoading && (
                    <>
                      <SkeletonRow />
                      <SkeletonRow />
                      <SkeletonRow />
                    </>
                  )}

                  {/* Empty state */}
                  {!isLoading && disputes.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-6 py-16 text-center">
                        <div className="flex flex-col items-center gap-3 text-gray-400">
                          <FileText size={32} strokeWidth={1.25} />
                          <p className="text-sm font-medium text-gray-500">
                            No accessorial disputes yet.
                          </p>
                          <p className="text-xs text-gray-400">
                            Submit an invoice to detect overcharges.
                          </p>
                        </div>
                      </td>
                    </tr>
                  )}

                  {/* Data rows */}
                  {!isLoading &&
                    disputes.map((d) => (
                      <tr
                        key={d.case_id}
                        className="border-b last:border-0 transition-colors"
                        style={{ borderColor: "#F1F4F9" }}
                        onMouseEnter={(e) =>
                          (e.currentTarget.style.backgroundColor = "#F0F4FF")
                        }
                        onMouseLeave={(e) =>
                          (e.currentTarget.style.backgroundColor = "")
                        }
                      >
                        {/* Invoice Ref */}
                        <td className="px-4 py-3 font-mono text-xs text-gray-700 whitespace-nowrap">
                          {d.invoice_reference}
                        </td>

                        {/* Carrier */}
                        <td className="px-4 py-3 text-gray-800 font-medium whitespace-nowrap">
                          {d.carrier_id}
                        </td>

                        {/* Dispute Total */}
                        <td
                          className="px-4 py-3 text-right font-medium text-gray-900 whitespace-nowrap"
                          style={{ fontVariantNumeric: "tabular-nums" }}
                        >
                          ₹{d.dispute_total.toLocaleString("en-IN")}
                        </td>

                        {/* Confidence */}
                        <td
                          className="px-4 py-3 text-right text-gray-600 whitespace-nowrap"
                          style={{ fontVariantNumeric: "tabular-nums" }}
                        >
                          {(d.confidence * 100).toFixed(1)}%
                        </td>

                        {/* State */}
                        <td className="px-4 py-3">
                          <StatePill state={d.state as DisputeState} />
                        </td>

                        {/* Date */}
                        <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                          {new Date(d.opened_at).toLocaleDateString("en-IN")}
                        </td>

                        {/* Arrow link */}
                        <td className="px-3 py-3 text-right">
                          <Link
                            to={`/accessorial/${d.case_id}`}
                            className="inline-flex items-center justify-center w-7 h-7 rounded-md text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                            aria-label={`View dispute ${d.invoice_reference}`}
                          >
                            <ChevronRight size={15} />
                          </Link>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Footer count ── */}
        {!isLoading && !isError && disputes.length > 0 && (
          <p className="mt-3 text-xs text-gray-400 text-right" style={{ fontVariantNumeric: "tabular-nums" }}>
            {disputes.length} dispute{disputes.length !== 1 ? "s" : ""}
          </p>
        )}
      </div>
    </div>
  );
}

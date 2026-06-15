import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import { Trash2, Plus, X, AlertCircle, ShieldCheck } from "lucide-react";
import type { PurgeJob } from "@/types";

const STATUS_BADGE: Record<string, string> = {
  PENDING:   "bg-amber-100 text-amber-700 border-amber-200",
  APPROVED:  "bg-blue-100 text-blue-700 border-blue-200",
  EXECUTING: "bg-purple-100 text-purple-700 border-purple-200",
  COMPLETED: "bg-emerald-100 text-emerald-700 border-emerald-200",
  BLOCKED:   "bg-red-100 text-red-700 border-red-200",
  FAILED:    "bg-red-100 text-red-600 border-red-200",
};

function JobCard({ job, onApprove }: { job: PurgeJob; onApprove: (id: string) => void }) {
  const [approvalId, setApprovalId] = useState("");
  const [showApprove, setShowApprove] = useState(false);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <Trash2 className={cn("h-4 w-4 flex-shrink-0", job.status === "BLOCKED" ? "text-red-500" : job.status === "COMPLETED" ? "text-emerald-500" : "text-slate-500")} />
          <div>
            <p className="font-semibold text-slate-700 text-sm">{job.purge_scope}</p>
            <p className="text-[11px] text-slate-500">{job.record_count.toLocaleString()} records</p>
          </div>
        </div>
        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border flex-shrink-0", STATUS_BADGE[job.status] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
          {job.status}
        </span>
      </div>

      {job.legal_hold_blocked && (
        <div className="flex items-center gap-1.5 text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-2 py-1">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          Blocked — active legal hold on one or more records
        </div>
      )}

      <p className="text-[11px] text-slate-400">
        Requested by {job.requested_by} · {new Date(job.created_at).toLocaleDateString()}
        {job.approved_by && <> · Approved by {job.approved_by}</>}
      </p>

      {job.status === "PENDING" && !job.legal_hold_blocked && (
        <div>
          {!showApprove ? (
            <button onClick={() => setShowApprove(true)}
              className="flex items-center gap-1 px-3 py-1.5 bg-slate-700 hover:bg-slate-800 text-white text-xs rounded-lg transition-colors">
              <ShieldCheck className="h-3 w-3" /> Approve Purge
            </button>
          ) : (
            <div className="space-y-2">
              <input
                value={approvalId}
                onChange={e => setApprovalId(e.target.value)}
                placeholder="Approval reference ID"
                className="w-full border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-slate-500/30"
              />
              <div className="flex gap-2">
                <button onClick={() => setShowApprove(false)} className="px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-100 rounded-lg transition-colors">Cancel</button>
                <button onClick={() => { onApprove(job.id); setShowApprove(false); }} disabled={!approvalId}
                  className="px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs rounded-lg transition-colors font-medium">
                  Confirm Approve
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function PurgeJobs() {
  const [showForm, setShowForm] = useState(false);
  const [jobs, setJobs] = useState<PurgeJob[]>([]);

  const [form, setForm] = useState({
    purge_scope: "case",
    record_count: 1,
    retention_policy_id: "",
    scope_ids: "",
  });

  const createMut = useMutation({
    mutationFn: () => zoikoApi.createPurgeJob({
      purge_scope: form.purge_scope,
      record_count: form.record_count,
      retention_policy_id: form.retention_policy_id || undefined,
      scope_ids: form.scope_ids.split(",").map(s => s.trim()).filter(Boolean),
    }),
    onSuccess: (j) => {
      setJobs(prev => [j, ...prev]);
      setShowForm(false);
      setForm({ purge_scope: "case", record_count: 1, retention_policy_id: "", scope_ids: "" });
    },
  });

  const approveMut = useMutation({
    mutationFn: ({ id, approvalId }: { id: string; approvalId: string }) =>
      zoikoApi.approvePurge(id, approvalId),
    onSuccess: (updated) => {
      setJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
    },
  });

  const blockedCount = jobs.filter(j => j.legal_hold_blocked).length;
  const pendingCount = jobs.filter(j => j.status === "PENDING" && !j.legal_hold_blocked).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Purge Jobs</h1>
          <p className="text-sm text-slate-500 mt-0.5">C07 §12 — Permanent deletion with dual-approval and legal hold check</p>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1.5 px-4 py-2 bg-slate-700 hover:bg-slate-800 text-white rounded-lg text-sm font-medium transition-colors"
        >
          {showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {showForm ? "Cancel" : "New Purge Job"}
        </button>
      </div>

      {/* Warning banner */}
      <div className="rounded-xl border border-red-200 bg-red-50 p-4">
        <div className="flex items-start gap-2.5">
          <AlertCircle className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-800">Destructive and irreversible</p>
            <p className="text-xs text-red-700 mt-0.5">
              Purge permanently deletes records. Legal holds on any scope_id will block the entire job.
              Dual-approval is required: the job must be created by one authorized user and approved by another.
            </p>
          </div>
        </div>
      </div>

      {/* Status summary */}
      {(blockedCount > 0 || pendingCount > 0) && (
        <div className="flex gap-3">
          {pendingCount > 0 && (
            <span className="text-xs bg-amber-100 text-amber-700 border border-amber-200 px-3 py-1.5 rounded-full font-medium">
              {pendingCount} pending approval
            </span>
          )}
          {blockedCount > 0 && (
            <span className="text-xs bg-red-100 text-red-700 border border-red-200 px-3 py-1.5 rounded-full font-medium">
              {blockedCount} blocked by legal hold
            </span>
          )}
        </div>
      )}

      {/* Create form */}
      {showForm && (
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-slate-700 text-sm mb-4">Create Purge Job</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Purge Scope</label>
                <select value={form.purge_scope} onChange={e => setForm(f => ({ ...f, purge_scope: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-slate-500/30">
                  {["case","source_record","evidence_bundle","ledger_entry","recovery_proof","tenant"].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Record Count *</label>
                <input type="number" min={1} value={form.record_count}
                  onChange={e => setForm(f => ({ ...f, record_count: Number(e.target.value) }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500/30" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Retention Policy ID (optional)</label>
                <input value={form.retention_policy_id}
                  onChange={e => setForm(f => ({ ...f, retention_policy_id: e.target.value }))}
                  placeholder="UUID"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-500/30" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Scope IDs (comma-separated)</label>
                <input value={form.scope_ids}
                  onChange={e => setForm(f => ({ ...f, scope_ids: e.target.value }))}
                  placeholder="uuid-1, uuid-2 (checked for legal holds)"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-500/30" />
              </div>
            </div>
            {createMut.error && <p className="text-xs text-red-600 mt-2">{String(createMut.error)}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">Cancel</button>
              <button onClick={() => createMut.mutate()} disabled={!form.record_count || createMut.isPending}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                {createMut.isPending ? "Creating…" : "Create Purge Job"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Jobs list */}
      <div>
        <h2 className="font-semibold text-slate-600 text-xs uppercase tracking-wide mb-3">Purge Jobs</h2>
        {jobs.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-8 border border-dashed border-slate-200 rounded-xl">
            No purge jobs in this session.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {jobs.map(j => (
              <JobCard
                key={j.id}
                job={j}
                onApprove={(id) => {
                  const approvalId = `APPROVAL-${Date.now()}`;
                  approveMut.mutate({ id, approvalId });
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

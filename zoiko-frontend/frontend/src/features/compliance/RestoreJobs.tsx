import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import { RefreshCw, Plus, X, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import type { RestoreJob, RestoreVerification } from "@/types";

const JOB_STATUS_BADGE: Record<string, string> = {
  PENDING:               "bg-slate-100 text-slate-500 border-slate-200",
  VERIFICATION_PENDING:  "bg-amber-100 text-amber-700 border-amber-200",
  VERIFICATION_PASSED:   "bg-emerald-100 text-emerald-700 border-emerald-200",
  VERIFICATION_FAILED:   "bg-red-100 text-red-700 border-red-200",
  APPROVED_FOR_USE:      "bg-blue-100 text-blue-700 border-blue-200",
  REJECTED:              "bg-red-100 text-red-600 border-red-200",
};

const VERIFICATION_CHECKS: { key: keyof RestoreVerification; label: string }[] = [
  { key: "source_records_verified",         label: "Source records verified" },
  { key: "evidence_chain_verified",         label: "Evidence chain verified" },
  { key: "acr_verified",                    label: "ACR verified" },
  { key: "ledger_continuity_verified",      label: "Ledger continuity verified" },
  { key: "tenant_isolation_verified",       label: "Tenant isolation verified" },
  { key: "residency_verified",              label: "Data residency verified" },
  { key: "permissions_verified",            label: "Permissions verified" },
  { key: "legal_hold_verified",             label: "Legal hold state verified" },
  { key: "indexes_rebuilt",                 label: "Indexes rebuilt" },
  { key: "projection_consistency_verified", label: "Projection consistency verified" },
];

function JobCard({
  job, onVerify, onApprove
}: {
  job: RestoreJob;
  onVerify: (id: string) => void;
  onApprove: (id: string) => void;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <RefreshCw className="h-4 w-4 text-blue-500 flex-shrink-0" />
          <div>
            <p className="font-semibold text-slate-700 text-sm">{job.restore_type}</p>
            <p className="text-[11px] text-slate-500">{job.restored_scope}</p>
          </div>
        </div>
        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border flex-shrink-0", JOB_STATUS_BADGE[job.status] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
          {job.status.replace(/_/g, " ")}
        </span>
      </div>
      <p className="text-[11px] text-slate-400">
        Requested by {job.requested_by} · {new Date(job.created_at).toLocaleDateString()}
      </p>
      <div className="flex gap-2">
        {(job.status === "PENDING" || job.status === "VERIFICATION_PENDING") && (
          <button onClick={() => onVerify(job.id)}
            className="flex items-center gap-1 px-3 py-1.5 border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 rounded-lg transition-colors">
            <CheckCircle2 className="h-3 w-3" /> Submit Verification
          </button>
        )}
        {job.status === "VERIFICATION_PASSED" && (
          <button onClick={() => onApprove(job.id)}
            className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs rounded-lg transition-colors">
            <CheckCircle2 className="h-3 w-3" /> Approve for Use
          </button>
        )}
      </div>
    </div>
  );
}

type VerifyState = Record<string, boolean>;

export default function RestoreJobs() {
  const [showForm, setShowForm] = useState(false);
  const [showVerifyFor, setShowVerifyFor] = useState<string | null>(null);
  const [jobs, setJobs] = useState<RestoreJob[]>([]);
  const [verifications, setVerifications] = useState<Record<string, RestoreVerification>>({});

  const [form, setForm] = useState({ restore_type: "point_in_time", restored_scope: "" });
  const [verifyChecks, setVerifyChecks] = useState<VerifyState>(
    Object.fromEntries(VERIFICATION_CHECKS.map(c => [c.key, false]))
  );

  const createMut = useMutation({
    mutationFn: () => zoikoApi.createRestoreJob(form),
    onSuccess: (job) => {
      setJobs(prev => [job, ...prev]);
      setShowForm(false);
      setForm({ restore_type: "point_in_time", restored_scope: "" });
    },
  });

  const verifyMut = useMutation({
    mutationFn: ({ id, checks }: { id: string; checks: Record<string, boolean> }) =>
      zoikoApi.submitRestoreVerification(id, checks),
    onSuccess: (v) => {
      setVerifications(prev => ({ ...prev, [v.restore_job_id]: v }));
      setJobs(prev => prev.map(j =>
        j.id === v.restore_job_id
          ? { ...j, status: v.verification_status === "PASSED" ? "VERIFICATION_PASSED" : "VERIFICATION_FAILED" }
          : j
      ));
      setShowVerifyFor(null);
    },
  });

  const approveMut = useMutation({
    mutationFn: (id: string) => zoikoApi.approveRestoreUse(id),
    onSuccess: (updated) => {
      setJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
    },
  });

  const allChecked = Object.values(verifyChecks).every(Boolean);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Restore Jobs</h1>
          <p className="text-sm text-slate-500 mt-0.5">C07 §14 — 10-check verification before restored data can be used</p>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          {showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {showForm ? "Cancel" : "New Restore"}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-slate-700 text-sm mb-4">Create Restore Job</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Restore Type</label>
                <select value={form.restore_type} onChange={e => setForm(f => ({ ...f, restore_type: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30">
                  {["point_in_time","archive_restore","disaster_recovery","test_restore"].map(t => (
                    <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Restored Scope *</label>
                <input value={form.restored_scope} onChange={e => setForm(f => ({ ...f, restored_scope: e.target.value }))}
                  placeholder="e.g. tenant:abc / case:uuid"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
              </div>
            </div>
            {createMut.error && <p className="text-xs text-red-600 mt-2">{String(createMut.error)}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">Cancel</button>
              <button onClick={() => createMut.mutate()} disabled={!form.restored_scope || createMut.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                {createMut.isPending ? "Creating…" : "Create Restore Job"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Verification panel */}
      {showVerifyFor && (
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-slate-700 text-sm">Submit Verification — {showVerifyFor.slice(0, 8)}…</h2>
              <button onClick={() => setShowVerifyFor(null)} className="text-slate-400 hover:text-slate-600">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-4">
              {VERIFICATION_CHECKS.map(({ key, label }) => (
                <label key={key} className={cn(
                  "flex items-center gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-colors",
                  verifyChecks[key] ? "border-emerald-200 bg-emerald-50" : "border-slate-200 hover:bg-slate-50"
                )}>
                  <input type="checkbox" checked={verifyChecks[key] as boolean}
                    onChange={e => setVerifyChecks(prev => ({ ...prev, [key]: e.target.checked }))}
                    className="accent-emerald-600 h-3.5 w-3.5 flex-shrink-0" />
                  <span className={cn("text-xs", verifyChecks[key] ? "text-emerald-700 font-medium" : "text-slate-600")}>
                    {label}
                  </span>
                  {verifyChecks[key] && <CheckCircle2 className="h-3 w-3 text-emerald-500 ml-auto flex-shrink-0" />}
                </label>
              ))}
            </div>
            {!allChecked && (
              <div className="flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
                <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                All 10 checks must pass for the restore to be approved for use
              </div>
            )}
            {verifyMut.error && <p className="text-xs text-red-600 mb-2">{String(verifyMut.error)}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowVerifyFor(null)} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">Cancel</button>
              <button
                onClick={() => verifyMut.mutate({ id: showVerifyFor, checks: verifyChecks as Record<string, boolean> })}
                disabled={verifyMut.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
              >
                {verifyMut.isPending ? "Submitting…" : "Submit Verification"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Jobs list */}
      <div>
        <h2 className="font-semibold text-slate-600 text-xs uppercase tracking-wide mb-3">Restore Jobs</h2>
        {jobs.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-8 border border-dashed border-slate-200 rounded-xl">
            No restore jobs in this session.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {jobs.map(j => (
              <div key={j.id}>
                <JobCard
                  job={j}
                  onVerify={(id) => setShowVerifyFor(id)}
                  onApprove={(id) => approveMut.mutate(id)}
                />
                {verifications[j.id] && (
                  <div className={cn(
                    "mt-2 rounded-lg border px-3 py-2 text-xs",
                    verifications[j.id].verification_status === "PASSED"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-red-200 bg-red-50 text-red-700"
                  )}>
                    <div className="flex items-center gap-1.5 font-semibold">
                      {verifications[j.id].verification_status === "PASSED"
                        ? <CheckCircle2 className="h-3.5 w-3.5" />
                        : <XCircle className="h-3.5 w-3.5" />}
                      Verification: {verifications[j.id].verification_status}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

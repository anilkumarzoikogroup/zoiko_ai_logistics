import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import { HardDrive, Plus, X, RotateCcw, AlertCircle } from "lucide-react";
import type { ArchiveJob, RestoreJob } from "@/types";

const STATUS_BADGE: Record<string, string> = {
  PENDING:     "bg-slate-100 text-slate-500 border-slate-200",
  IN_PROGRESS: "bg-amber-100 text-amber-700 border-amber-200",
  COMPLETED:   "bg-emerald-100 text-emerald-700 border-emerald-200",
  FAILED:      "bg-red-100 text-red-700 border-red-200",
};

function JobCard({ job, onRestore }: { job: ArchiveJob; onRestore: (id: string) => void }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <HardDrive className="h-4 w-4 text-slate-500 flex-shrink-0" />
          <div>
            <p className="font-semibold text-slate-700 text-sm">{job.archive_scope}</p>
            <p className="text-[11px] text-slate-500">{job.record_ids.length} records</p>
          </div>
        </div>
        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border flex-shrink-0", STATUS_BADGE[job.status] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
          {job.status}
        </span>
      </div>
      <p className="text-[11px] text-slate-400">
        Requested by {job.requested_by} · {new Date(job.created_at).toLocaleDateString()}
      </p>
      {job.retention_policy_id && (
        <p className="text-[11px] text-slate-400 font-mono">Policy: {job.retention_policy_id.slice(0, 12)}…</p>
      )}
      {job.status === "COMPLETED" && (
        <button
          onClick={() => onRestore(job.id)}
          className="flex items-center gap-1 px-3 py-1.5 border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 rounded-lg transition-colors"
        >
          <RotateCcw className="h-3 w-3" /> Restore from Archive
        </button>
      )}
    </div>
  );
}

export default function ArchiveJobs() {
  const [showForm, setShowForm] = useState(false);
  const [jobs, setJobs] = useState<ArchiveJob[]>([]);
  const [restoreResults, setRestoreResults] = useState<Record<string, RestoreJob>>({});

  const [form, setForm] = useState({
    archive_scope: "case",
    record_ids: "",
    retention_policy_id: "",
  });

  const createMut = useMutation({
    mutationFn: () => zoikoApi.createArchiveJob({
      archive_scope: form.archive_scope,
      record_ids: form.record_ids.split(",").map(s => s.trim()).filter(Boolean),
      retention_policy_id: form.retention_policy_id || undefined,
    }),
    onSuccess: (j) => {
      setJobs(prev => [j, ...prev]);
      setShowForm(false);
      setForm({ archive_scope: "case", record_ids: "", retention_policy_id: "" });
    },
  });

  const restoreMut = useMutation({
    mutationFn: (archiveId: string) => zoikoApi.restoreFromArchive(archiveId),
    onSuccess: (rj, archiveId) => {
      setRestoreResults(prev => ({ ...prev, [archiveId]: rj }));
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Archive Jobs</h1>
          <p className="text-sm text-slate-500 mt-0.5">C07 §9 — Move records to long-term archive with legal hold check</p>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          {showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {showForm ? "Cancel" : "New Archive Job"}
        </button>
      </div>

      {/* Info banner */}
      <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
        <div className="flex items-start gap-2.5">
          <AlertCircle className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-blue-700">
            Records with active legal holds cannot be archived (C07 §9.1). The backend checks all records
            before creating the job. After archiving, use "Restore from Archive" to start a restore job,
            which requires 10-check verification before the data can be used.
          </p>
        </div>
      </div>

      {/* Create form */}
      {showForm && (
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-slate-700 text-sm mb-4">Create Archive Job</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Archive Scope</label>
                <select value={form.archive_scope} onChange={e => setForm(f => ({ ...f, archive_scope: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30">
                  {["case","source_record","evidence_bundle","ledger_entry","recovery_proof","tenant"].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Record IDs (comma-separated) *</label>
                <textarea
                  value={form.record_ids}
                  onChange={e => setForm(f => ({ ...f, record_ids: e.target.value }))}
                  placeholder="uuid-1, uuid-2, uuid-3"
                  rows={3}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30 resize-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Retention Policy ID (optional)</label>
                <input
                  value={form.retention_policy_id}
                  onChange={e => setForm(f => ({ ...f, retention_policy_id: e.target.value }))}
                  placeholder="UUID of retention policy"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>
            </div>
            {createMut.error && <p className="text-xs text-red-600 mt-2">{String(createMut.error)}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">Cancel</button>
              <button onClick={() => createMut.mutate()} disabled={!form.record_ids || createMut.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                {createMut.isPending ? "Creating…" : "Create Archive Job"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Jobs list */}
      <div>
        <h2 className="font-semibold text-slate-600 text-xs uppercase tracking-wide mb-3">Archive Jobs</h2>
        {jobs.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-8 border border-dashed border-slate-200 rounded-xl">
            No archive jobs in this session.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {jobs.map(j => (
              <div key={j.id}>
                <JobCard job={j} onRestore={(id) => restoreMut.mutate(id)} />
                {restoreResults[j.id] && (
                  <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-700">
                    <p className="font-semibold">Restore job created</p>
                    <p className="font-mono mt-0.5">{restoreResults[j.id].id.slice(0, 12)}… · {restoreResults[j.id].status}</p>
                    <p className="mt-0.5 text-blue-600">Go to Restore Jobs to complete 10-check verification.</p>
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

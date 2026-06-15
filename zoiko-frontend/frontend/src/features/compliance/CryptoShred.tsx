import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import { ShieldOff, Plus, X, CheckCircle2, AlertCircle } from "lucide-react";
import type { CryptoShredRequest, CryptoShredVerification } from "@/types";

const STATUS_BADGE: Record<string, string> = {
  COMPLETED: "bg-emerald-100 text-emerald-700 border-emerald-200",
  BLOCKED:   "bg-red-100 text-red-700 border-red-200",
  PENDING:   "bg-amber-100 text-amber-700 border-amber-200",
  VERIFIED:  "bg-blue-100 text-blue-700 border-blue-200",
};

function ShredCard({ r, onVerify }: { r: CryptoShredRequest; onVerify: (id: string) => void }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldOff className={cn("h-4 w-4 flex-shrink-0", r.status === "COMPLETED" ? "text-emerald-500" : r.status === "BLOCKED" ? "text-red-500" : "text-amber-500")} />
          <p className="font-semibold text-slate-700 text-sm">{r.subject_ref}</p>
        </div>
        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border flex-shrink-0", STATUS_BADGE[r.status] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
          {r.status}
        </span>
      </div>
      {r.legal_hold_blocked && (
        <div className="flex items-center gap-1.5 text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-2 py-1">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          Blocked by active legal hold
        </div>
      )}
      <div className="text-[11px] text-slate-500 space-y-0.5">
        <p>Keys: {r.affected_key_ids.length} · Records: {r.affected_record_ids.length}</p>
        <p>Requested by {r.requested_by} · {new Date(r.created_at).toLocaleDateString()}</p>
        {r.completed_at && <p>Completed: {new Date(r.completed_at).toLocaleDateString()}</p>}
      </div>
      {r.status === "COMPLETED" && (
        <button
          onClick={() => onVerify(r.id)}
          className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium transition-colors"
        >
          <CheckCircle2 className="h-3.5 w-3.5" /> Verify shred
        </button>
      )}
    </div>
  );
}

export default function CryptoShred() {
  const [showForm, setShowForm] = useState(false);
  const [requests, setRequests] = useState<CryptoShredRequest[]>([]);
  const [verifications, setVerifications] = useState<Record<string, CryptoShredVerification>>({});

  const [form, setForm] = useState({
    subject_ref: "",
    affected_key_ids: "",
    affected_record_ids: "",
  });

  const createMut = useMutation({
    mutationFn: () => zoikoApi.requestCryptoShred({
      subject_ref: form.subject_ref,
      affected_key_ids: form.affected_key_ids.split(",").map(s => s.trim()).filter(Boolean),
      affected_record_ids: form.affected_record_ids.split(",").map(s => s.trim()).filter(Boolean),
    }),
    onSuccess: (r) => {
      setRequests(prev => [r, ...prev]);
      setShowForm(false);
      setForm({ subject_ref: "", affected_key_ids: "", affected_record_ids: "" });
    },
  });

  const verifyMut = useMutation({
    mutationFn: (id: string) => zoikoApi.verifyCryptoShred(id),
    onSuccess: (v) => {
      setVerifications(prev => ({ ...prev, [v.crypto_shred_id]: v }));
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Crypto-Shred / Privacy</h1>
          <p className="text-sm text-slate-500 mt-0.5">C07 §11 — DEK destruction with evidence preservation</p>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1.5 px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          {showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {showForm ? "Cancel" : "Request Shred"}
        </button>
      </div>

      {/* Warning banner */}
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div className="flex items-start gap-2.5">
          <AlertCircle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-amber-800">Irreversible operation</p>
            <p className="text-xs text-amber-700 mt-0.5">
              Crypto-shredding destroys DEK access permanently. Evidence structure and hashes are preserved.
              Any active legal hold on affected records will block the operation.
            </p>
          </div>
        </div>
      </div>

      {/* Create form */}
      {showForm && (
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-slate-700 text-sm mb-4">Request Crypto-Shred</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Subject Reference *</label>
                <input
                  value={form.subject_ref}
                  onChange={e => setForm(f => ({ ...f, subject_ref: e.target.value }))}
                  placeholder="e.g. GDPR-REQUEST-2025-001 or subject email"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/30"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Affected Key IDs (comma-separated) *</label>
                <input
                  value={form.affected_key_ids}
                  onChange={e => setForm(f => ({ ...f, affected_key_ids: e.target.value }))}
                  placeholder="key-id-1, key-id-2"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-rose-500/30"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Affected Record IDs (comma-separated) *</label>
                <textarea
                  value={form.affected_record_ids}
                  onChange={e => setForm(f => ({ ...f, affected_record_ids: e.target.value }))}
                  placeholder="uuid-1, uuid-2, uuid-3"
                  rows={3}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-rose-500/30 resize-none"
                />
              </div>
            </div>
            {createMut.error && <p className="text-xs text-red-600 mt-2">{String(createMut.error)}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">Cancel</button>
              <button
                onClick={() => createMut.mutate()}
                disabled={!form.subject_ref || !form.affected_key_ids || createMut.isPending}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
              >
                {createMut.isPending ? "Processing…" : "Submit Shred Request"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Requests list */}
      <div>
        <h2 className="font-semibold text-slate-600 text-xs uppercase tracking-wide mb-3">Shred Requests</h2>
        {requests.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-8 border border-dashed border-slate-200 rounded-xl">
            No shred requests in this session.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {requests.map(r => (
              <div key={r.id}>
                <ShredCard r={r} onVerify={(id) => verifyMut.mutate(id)} />
                {verifications[r.id] && (
                  <div className={cn(
                    "mt-2 rounded-lg border px-3 py-2 text-xs",
                    verifications[r.id].verified ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"
                  )}>
                    <div className="flex items-center gap-1.5 font-semibold">
                      {verifications[r.id].verified ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
                      {verifications[r.id].verified ? "Verified — all records shredded" : "Verification failed"}
                    </div>
                    <p className="mt-0.5">Shredded: {verifications[r.id].shredded_count} records</p>
                    {verifications[r.id].unshredded_ids.length > 0 && (
                      <p>Unshredded: {verifications[r.id].unshredded_ids.length} records</p>
                    )}
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

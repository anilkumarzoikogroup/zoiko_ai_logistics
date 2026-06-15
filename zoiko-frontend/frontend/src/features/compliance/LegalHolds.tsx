import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import { Lock, Unlock, Plus, X } from "lucide-react";
import { useAppSelector } from "@/store";
import type { LegalHold } from "@/types";

const STATUS_BADGE: Record<string, string> = {
  ACTIVE:   "bg-red-100 text-red-700 border-red-200",
  RELEASED: "bg-slate-100 text-slate-500 border-slate-200",
};

// Demo: query a well-known scope_id to list holds. In production a list endpoint would be added.
const DEMO_SCOPE = "case";

function HoldRow({ h, onRelease }: { h: LegalHold; onRelease: (id: string) => void }) {
  return (
    <div className="flex items-start justify-between gap-3 py-3 border-b border-slate-100 last:border-0">
      <div className="flex items-start gap-2.5 flex-1 min-w-0">
        <Lock className={cn("h-4 w-4 mt-0.5 flex-shrink-0", h.status === "ACTIVE" ? "text-red-500" : "text-slate-400")} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-slate-700 truncate">{h.reason_code}</p>
            <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border", STATUS_BADGE[h.status] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
              {h.status}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Scope: <span className="font-medium">{h.hold_scope}</span> · ID: <span className="font-mono">{h.scope_id.slice(0, 8)}…</span>
          </p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Requested by {h.requested_by} · {new Date(h.created_at).toLocaleDateString()}
            {h.approved_by && <> · Approved by {h.approved_by}</>}
          </p>
        </div>
      </div>
      {h.status === "ACTIVE" && (
        <button
          onClick={() => onRelease(h.id)}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition-colors flex-shrink-0"
        >
          <Unlock className="h-3 w-3" /> Release
        </button>
      )}
    </div>
  );
}

export default function LegalHolds() {
  const sub = useAppSelector(s => s.auth.sub) ?? "system";
  const qc = useQueryClient();

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    hold_scope: "case",
    scope_id: "",
    reason_code: "",
    approved_by: "",
  });
  const [lookupScope, setLookupScope] = useState(DEMO_SCOPE);
  const [lookupId, setLookupId] = useState("");
  const [holds, setHolds] = useState<LegalHold[]>([]);
  const [lookupErr, setLookupErr] = useState("");

  const createMut = useMutation({
    mutationFn: () => zoikoApi.createLegalHold({
      hold_scope: form.hold_scope,
      scope_id: form.scope_id,
      reason_code: form.reason_code,
      approved_by: form.approved_by || undefined,
    }),
    onSuccess: (h) => {
      setHolds(prev => [h, ...prev]);
      setShowForm(false);
      setForm({ hold_scope: "case", scope_id: "", reason_code: "", approved_by: "" });
    },
  });

  const releaseMut = useMutation({
    mutationFn: (id: string) => zoikoApi.releaseLegalHold(id, sub),
    onSuccess: (updated) => {
      setHolds(prev => prev.map(h => h.id === updated.id ? updated : h));
    },
  });

  async function handleLookup() {
    setLookupErr("");
    try {
      const results = await zoikoApi.legalHoldsByScope(lookupId);
      setHolds(results);
    } catch {
      setLookupErr("Lookup failed — check the scope ID.");
    }
  }

  const activeCount = holds.filter(h => h.status === "ACTIVE").length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Legal Holds</h1>
          <p className="text-sm text-slate-500 mt-0.5">C07 §10 — Freeze records from purge, archive, and crypto-shred</p>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          {showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {showForm ? "Cancel" : "New Hold"}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-slate-700 text-sm mb-4">Place Legal Hold</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Hold Scope *</label>
                <select
                  value={form.hold_scope}
                  onChange={e => setForm(f => ({ ...f, hold_scope: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                >
                  {["case","source_record","evidence_bundle","ledger_entry","recovery_proof","tenant"].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Scope ID (UUID) *</label>
                <input
                  value={form.scope_id}
                  onChange={e => setForm(f => ({ ...f, scope_id: e.target.value }))}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30 font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Reason Code *</label>
                <input
                  value={form.reason_code}
                  onChange={e => setForm(f => ({ ...f, reason_code: e.target.value }))}
                  placeholder="e.g. LITIGATION_HOLD, REGULATORY_INVESTIGATION"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Approved By</label>
                <input
                  value={form.approved_by}
                  onChange={e => setForm(f => ({ ...f, approved_by: e.target.value }))}
                  placeholder="approver email or sub"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>
            </div>
            {createMut.error && (
              <p className="text-xs text-red-600 mt-2">{String(createMut.error)}</p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
                Cancel
              </button>
              <button
                onClick={() => createMut.mutate()}
                disabled={!form.scope_id || !form.reason_code || createMut.isPending}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
              >
                {createMut.isPending ? "Placing hold…" : "Place Hold"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Lookup */}
      <Card>
        <CardContent className="p-5">
          <h2 className="font-semibold text-slate-700 text-sm mb-3">Look up holds by Scope ID</h2>
          <div className="flex gap-2">
            <input
              value={lookupId}
              onChange={e => setLookupId(e.target.value)}
              placeholder="Scope ID (UUID)"
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
            />
            <button
              onClick={handleLookup}
              disabled={!lookupId}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Lookup
            </button>
          </div>
          {lookupErr && <p className="text-xs text-red-600 mt-2">{lookupErr}</p>}
        </CardContent>
      </Card>

      {/* Holds list */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <Lock className="h-4 w-4 text-red-500" />
            <h2 className="font-semibold text-slate-700 text-sm">Holds</h2>
            {activeCount > 0 && (
              <span className="ml-auto text-[10px] font-bold bg-red-100 text-red-600 px-2 py-0.5 rounded-full">
                {activeCount} ACTIVE
              </span>
            )}
          </div>
          {holds.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-6">No holds found. Use "Look up" to search by scope ID or create a new hold.</p>
          ) : (
            <div>
              {holds.map(h => (
                <HoldRow key={h.id} h={h} onRelease={(id) => releaseMut.mutate(id)} />
              ))}
            </div>
          )}
          {releaseMut.error && <p className="text-xs text-red-600 mt-2">{String(releaseMut.error)}</p>}
        </CardContent>
      </Card>
    </div>
  );
}

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { Plus, X, Search, Clock } from "lucide-react";
import type { RetentionPolicy, RetentionAssignment } from "@/types";

function PolicyCard({ p }: { p: RetentionPolicy }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold text-slate-700 text-sm">{p.policy_name}</p>
        <span className="text-[10px] font-bold bg-blue-50 text-blue-600 border border-blue-100 px-2 py-0.5 rounded-full flex-shrink-0">
          {p.retention_class}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <div>
          <p className="text-slate-400">Retention</p>
          <p className="font-medium text-slate-700">{p.retention_days} days</p>
        </div>
        <div>
          <p className="text-slate-400">Archive after</p>
          <p className="font-medium text-slate-700">{p.archive_after_days ?? "—"} {p.archive_after_days ? "days" : ""}</p>
        </div>
        <div>
          <p className="text-slate-400">Purge after</p>
          <p className="font-medium text-slate-700">{p.purge_after_days ?? "—"} {p.purge_after_days ? "days" : ""}</p>
        </div>
      </div>
      <p className="text-[10px] text-slate-400">Class: {p.data_class} · Created by {p.created_by}</p>
    </div>
  );
}

function AssignmentCard({ a }: { a: RetentionAssignment }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3 space-y-1">
      <div className="flex items-center gap-2">
        <Clock className="h-3.5 w-3.5 text-blue-500" />
        <p className="text-xs font-semibold text-slate-700">{a.record_type}</p>
      </div>
      <p className="text-[11px] font-mono text-slate-500">{a.record_id?.slice(0, 12)}…</p>
      <div className="grid grid-cols-3 gap-2 text-[10px] text-slate-500 mt-1">
        <div><span className="text-slate-400">Until </span>{a.retention_until ? new Date(a.retention_until).toLocaleDateString() : "—"}</div>
        <div><span className="text-slate-400">Archive </span>{a.archive_after ? new Date(a.archive_after).toLocaleDateString() : "—"}</div>
        <div><span className="text-slate-400">Purge </span>{a.purge_after ? new Date(a.purge_after).toLocaleDateString() : "—"}</div>
      </div>
    </div>
  );
}

export default function DataRetention() {
  const [showPolicyForm, setShowPolicyForm] = useState(false);
  const [showAssignForm, setShowAssignForm] = useState(false);
  const [policies, setPolicies] = useState<RetentionPolicy[]>([]);
  const [assignments, setAssignments] = useState<RetentionAssignment[]>([]);
  const [lookupId, setLookupId] = useState("");
  const [lookupResult, setLookupResult] = useState<RetentionAssignment | null>(null);
  const [lookupErr, setLookupErr] = useState("");

  const [pForm, setPForm] = useState({
    policy_name: "", data_class: "CLASS_A", retention_class: "REGULATORY",
    retention_days: 2555, archive_after_days: "", purge_after_days: "",
  });
  const [aForm, setAForm] = useState({ record_type: "case", record_id: "", policy_id: "" });

  const createPolicyMut = useMutation({
    mutationFn: () => zoikoApi.createRetentionPolicy({
      policy_name: pForm.policy_name,
      data_class: pForm.data_class,
      retention_class: pForm.retention_class,
      retention_days: pForm.retention_days,
      archive_after_days: pForm.archive_after_days ? Number(pForm.archive_after_days) : undefined,
      purge_after_days: pForm.purge_after_days ? Number(pForm.purge_after_days) : undefined,
    }),
    onSuccess: (p) => {
      setPolicies(prev => [p, ...prev]);
      setShowPolicyForm(false);
      setPForm({ policy_name: "", data_class: "CLASS_A", retention_class: "REGULATORY", retention_days: 2555, archive_after_days: "", purge_after_days: "" });
    },
  });

  const assignMut = useMutation({
    mutationFn: () => zoikoApi.assignRetention(aForm),
    onSuccess: (a) => {
      setAssignments(prev => [a, ...prev]);
      setShowAssignForm(false);
    },
  });

  async function handleLookup() {
    setLookupErr(""); setLookupResult(null);
    const r = await zoikoApi.retentionByRecord(lookupId).catch(() => null);
    if (r) setLookupResult(r);
    else setLookupErr("No retention assignment found for this record ID.");
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Data Retention</h1>
          <p className="text-sm text-slate-500 mt-0.5">C07 §8 — Retention policies and record lifecycle dates</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => { setShowAssignForm(v => !v); setShowPolicyForm(false); }}
            className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-sm transition-colors"
          >
            Assign
          </button>
          <button
            onClick={() => { setShowPolicyForm(v => !v); setShowAssignForm(false); }}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {showPolicyForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            New Policy
          </button>
        </div>
      </div>

      {/* Policy form */}
      {showPolicyForm && (
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-slate-700 text-sm mb-4">Create Retention Policy</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="md:col-span-3">
                <label className="block text-xs font-medium text-slate-600 mb-1">Policy Name *</label>
                <input
                  value={pForm.policy_name}
                  onChange={e => setPForm(f => ({ ...f, policy_name: e.target.value }))}
                  placeholder="e.g. 7-Year Regulatory Hold"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Data Class</label>
                <select value={pForm.data_class} onChange={e => setPForm(f => ({ ...f, data_class: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30">
                  {["CLASS_A","CLASS_B","CLASS_C"].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Retention Class</label>
                <select value={pForm.retention_class} onChange={e => setPForm(f => ({ ...f, retention_class: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30">
                  {["REGULATORY","LEGAL","OPERATIONAL","SHORT_TERM"].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Retention Days *</label>
                <input type="number" value={pForm.retention_days}
                  onChange={e => setPForm(f => ({ ...f, retention_days: Number(e.target.value) }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Archive After (days)</label>
                <input type="number" value={pForm.archive_after_days}
                  onChange={e => setPForm(f => ({ ...f, archive_after_days: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Purge After (days)</label>
                <input type="number" value={pForm.purge_after_days}
                  onChange={e => setPForm(f => ({ ...f, purge_after_days: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
              </div>
            </div>
            {createPolicyMut.error && <p className="text-xs text-red-600 mt-2">{String(createPolicyMut.error)}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setShowPolicyForm(false)} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">Cancel</button>
              <button onClick={() => createPolicyMut.mutate()} disabled={!pForm.policy_name || createPolicyMut.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                {createPolicyMut.isPending ? "Creating…" : "Create Policy"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Assign form */}
      {showAssignForm && (
        <Card>
          <CardContent className="p-5">
            <h2 className="font-semibold text-slate-700 text-sm mb-4">Assign Retention to Record</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Record Type</label>
                <select value={aForm.record_type} onChange={e => setAForm(f => ({ ...f, record_type: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30">
                  {["case","source_record","evidence_bundle","ledger_entry","recovery_proof"].map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Record ID *</label>
                <input value={aForm.record_id} onChange={e => setAForm(f => ({ ...f, record_id: e.target.value }))}
                  placeholder="UUID" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Policy ID *</label>
                <input value={aForm.policy_id} onChange={e => setAForm(f => ({ ...f, policy_id: e.target.value }))}
                  placeholder="retention policy UUID" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
              </div>
            </div>
            {assignMut.error && <p className="text-xs text-red-600 mt-2">{String(assignMut.error)}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setShowAssignForm(false)} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">Cancel</button>
              <button onClick={() => assignMut.mutate()} disabled={!aForm.record_id || !aForm.policy_id || assignMut.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                {assignMut.isPending ? "Assigning…" : "Assign"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Lookup */}
      <Card>
        <CardContent className="p-5">
          <h2 className="font-semibold text-slate-700 text-sm mb-3">Look up retention by Record ID</h2>
          <div className="flex gap-2">
            <input value={lookupId} onChange={e => setLookupId(e.target.value)} placeholder="Record UUID"
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
            <button onClick={handleLookup} disabled={!lookupId}
              className="flex items-center gap-1 px-4 py-2 bg-slate-700 hover:bg-slate-800 disabled:opacity-50 text-white rounded-lg text-sm transition-colors">
              <Search className="h-3.5 w-3.5" /> Lookup
            </button>
          </div>
          {lookupErr && <p className="text-xs text-red-600 mt-2">{lookupErr}</p>}
          {lookupResult && <div className="mt-3"><AssignmentCard a={lookupResult} /></div>}
        </CardContent>
      </Card>

      {/* Policies list */}
      <div>
        <h2 className="font-semibold text-slate-600 text-xs uppercase tracking-wide mb-3">Policies created this session</h2>
        {policies.length === 0
          ? <p className="text-sm text-slate-400 text-center py-6 border border-dashed border-slate-200 rounded-xl">No policies created yet. Use "New Policy" to create one.</p>
          : <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{policies.map(p => <PolicyCard key={p.id} p={p} />)}</div>
        }
      </div>

      {/* Assignments list */}
      {assignments.length > 0 && (
        <div>
          <h2 className="font-semibold text-slate-600 text-xs uppercase tracking-wide mb-3">Assignments created this session</h2>
          <div className="space-y-2">{assignments.map((a, i) => <AssignmentCard key={i} a={a} />)}</div>
        </div>
      )}
    </div>
  );
}

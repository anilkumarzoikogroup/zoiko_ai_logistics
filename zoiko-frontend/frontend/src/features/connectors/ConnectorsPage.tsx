import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Plus, Plug, CheckCircle2, AlertTriangle, Clock, Trash2, RefreshCw } from "lucide-react";

interface Connector {
  id: string;
  name: string;
  connector_type: string;
  auth_method: string;
  trust_tier: string;
  certification_state: string;
  operational_state: string;
  endpoint_url: string;
  rate_limit_rps: number;
  created_at: string;
}

const STATE_COLOR: Record<string, string> = {
  healthy:   "text-green-600 bg-green-50",
  degraded:  "text-yellow-600 bg-yellow-50",
  frozen:    "text-red-600 bg-red-50",
  suspended: "text-red-600 bg-red-50",
};

const CERT_COLOR: Record<string, string> = {
  Active:           "text-green-700 bg-green-50",
  Certified:        "text-blue-700 bg-blue-50",
  SandboxValidated: "text-indigo-700 bg-indigo-50",
  Registered:       "text-slate-700 bg-slate-100",
  Draft:            "text-slate-500 bg-slate-50",
  Suspended:        "text-red-700 bg-red-50",
  Deprecated:       "text-orange-700 bg-orange-50",
};

export default function ConnectorsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", connector_type: "API", auth_method: "API_KEY", trust_tier: "T2", endpoint_url: "", rate_limit_rps: 10 });

  const { data: connectors = [], isLoading } = useQuery<Connector[]>({
    queryKey: ["connectors"],
    queryFn: async () => {
      const { data } = await api.get("/v1/connectors");
      return data;
    },
    refetchInterval: 15000,
  });

  const createMut = useMutation({
    mutationFn: async (body: typeof form) => {
      const { data } = await api.post("/v1/connectors", body, { headers: { "Idempotency-Key": crypto.randomUUID() } });
      return data;
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["connectors"] }); setShowForm(false); },
  });

  const syncMut = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`/v1/ingestion/connectors/${id}/sync`, {}, { headers: { "Idempotency-Key": crypto.randomUUID() } });
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connectors"] }),
  });

  const deleteMut = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/v1/connectors/${id}`); },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connectors"] }),
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Plug className="h-6 w-6 text-slate-600" />
          <div>
            <h1 className="text-xl font-semibold text-slate-800">Connectors</h1>
            <p className="text-sm text-slate-500">External system integrations — API, EDI, SFTP, Webhook</p>
          </div>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition"
        >
          <Plus className="h-4 w-4" /> Add Connector
        </button>
      </div>

      {/* Add form */}
      {showForm && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-700">New Connector</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-500 mb-1">Name</label>
              <input className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Type</label>
              <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm" value={form.connector_type} onChange={e => setForm(p => ({ ...p, connector_type: e.target.value }))}>
                {["API","EDI","Email","SFTP","Batch","Webhook","Portal"].map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Auth Method</label>
              <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm" value={form.auth_method} onChange={e => setForm(p => ({ ...p, auth_method: e.target.value }))}>
                {["API_KEY","OAuth2","mTLS","SFTP_KEY","WEBHOOK_HMAC"].map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Trust Tier</label>
              <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm" value={form.trust_tier} onChange={e => setForm(p => ({ ...p, trust_tier: e.target.value }))}>
                {["T1","T2","T3","T4"].map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-slate-500 mb-1">Endpoint URL</label>
              <input className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm" value={form.endpoint_url} onChange={e => setForm(p => ({ ...p, endpoint_url: e.target.value }))} placeholder="https://" />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50">Cancel</button>
            <button onClick={() => createMut.mutate(form)} disabled={!form.name || createMut.isPending} className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
              {createMut.isPending ? "Creating…" : "Create"}
            </button>
          </div>
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />)}</div>
      ) : connectors.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <Plug className="h-10 w-10 mx-auto mb-3 opacity-30" />
          <p className="font-medium">No connectors yet</p>
          <p className="text-sm mt-1">Add your first connector to start ingesting data.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {connectors.map(c => (
            <div key={c.id} className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-800">{c.name}</span>
                  <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded">{c.connector_type}</span>
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${CERT_COLOR[c.certification_state] ?? "bg-slate-100 text-slate-600"}`}>{c.certification_state}</span>
                </div>
                <div className="flex items-center gap-4 mt-1 text-xs text-slate-500">
                  <span>Auth: {c.auth_method}</span>
                  <span>Tier: {c.trust_tier}</span>
                  <span>{c.rate_limit_rps} rps</span>
                  {c.endpoint_url && <span className="truncate max-w-xs">{c.endpoint_url}</span>}
                </div>
              </div>
              <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATE_COLOR[c.operational_state] ?? "bg-slate-100 text-slate-600"}`}>
                {c.operational_state}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => syncMut.mutate(c.id)}
                  disabled={syncMut.isPending}
                  title="Trigger sync"
                  className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition"
                >
                  <RefreshCw className="h-4 w-4" />
                </button>
                <button
                  onClick={() => { if (confirm(`Delete connector "${c.name}"?`)) deleteMut.mutate(c.id); }}
                  title="Delete"
                  className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { FileSearch, ArrowLeft, CheckCircle2, Clock, Hash } from "lucide-react";

interface EvidenceBundle {
  id: string;
  case_id: string;
  completeness_score: number;
  status: string;
  created_at: string;
  items: { id: string; item_type: string; content_hash: string; created_at: string }[];
}

interface EvidenceResponse {
  case_id: string;
  bundles: { id: string; case_id: string; completeness_score: number; status: string; item_count: number; created_at: string }[];
}

export default function EvidencePage() {
  const { id: caseId } = useParams<{ id: string }>();

  const { data, isLoading } = useQuery<EvidenceResponse>({
    queryKey: ["case-evidence", caseId],
    queryFn: async () => { const { data } = await api.get(`/cases/${caseId}/evidence`); return data; },
    enabled: !!caseId,
  });

  const [selectedBundle, setSelectedBundle] = useState<string | null>(null);

  const { data: bundleDetail } = useQuery<EvidenceBundle>({
    queryKey: ["bundle", selectedBundle],
    queryFn: async () => { const { data } = await api.get(`/evidence/bundles/${selectedBundle}`); return data; },
    enabled: !!selectedBundle,
  });

  const scoreColor = (s: number) => s >= 0.8 ? "text-green-600" : s >= 0.5 ? "text-yellow-600" : "text-red-600";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to={`/cases/${caseId}`} className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <FileSearch className="h-6 w-6 text-slate-600" />
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Evidence Bundles</h1>
          <p className="text-xs text-slate-400 font-mono">Case {caseId}</p>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-3">{[1,2].map(i => <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />)}</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Bundle list */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Bundles</h2>
          {!data?.bundles.length && !isLoading && (
            <p className="text-sm text-slate-400 py-6 text-center">No evidence bundles for this case.</p>
          )}
          {data?.bundles.map(b => (
            <button
              key={b.id}
              onClick={() => setSelectedBundle(b.id)}
              className={`w-full text-left bg-white border rounded-xl p-4 hover:border-blue-300 transition ${selectedBundle === b.id ? "border-blue-500 ring-1 ring-blue-200" : "border-slate-200"}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-slate-400">{b.id.slice(0, 8)}…</span>
                <span className={`text-xs font-semibold ${scoreColor(b.completeness_score)}`}>
                  {(b.completeness_score * 100).toFixed(0)}% complete
                </span>
              </div>
              <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3" />{b.item_count} items</span>
                <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{new Date(b.created_at).toLocaleDateString()}</span>
                <span className={`px-2 py-0.5 rounded font-medium ${b.status === "COMPLETE" ? "bg-green-50 text-green-700" : "bg-slate-100 text-slate-600"}`}>{b.status}</span>
              </div>
            </button>
          ))}
        </div>

        {/* Bundle detail */}
        <div>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Items</h2>
          {!selectedBundle && (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center text-slate-400 text-sm">
              Select a bundle to view items
            </div>
          )}
          {bundleDetail && (
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              {bundleDetail.items.length === 0 && (
                <p className="text-sm text-slate-400 text-center py-8">No items in this bundle.</p>
              )}
              {bundleDetail.items.map(item => (
                <div key={item.id} className="px-4 py-3 border-b border-slate-100 last:border-0">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-700">{item.item_type}</span>
                    <span className="text-xs text-slate-400">{new Date(item.created_at).toLocaleString()}</span>
                  </div>
                  <div className="flex items-center gap-1 mt-1 text-xs text-slate-400 font-mono">
                    <Hash className="h-3 w-3 flex-shrink-0" />
                    <span className="truncate">{item.content_hash}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

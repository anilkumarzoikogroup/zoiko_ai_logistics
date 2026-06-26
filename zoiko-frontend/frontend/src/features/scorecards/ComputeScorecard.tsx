import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { scorecardApi } from "@/api/zoiko";

export default function ComputeScorecard() {
  const navigate = useNavigate();
  const [carrierId, setCarrierId]   = useState("");
  const [periodDays, setPeriodDays] = useState(30);
  const [threshold, setThreshold]   = useState(70);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState("");

  const { data: carriers = [] } = useQuery({
    queryKey: ["scorecard-carriers"],
    queryFn: () => scorecardApi.listCarriers(),
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!carrierId) { setError("Select a carrier"); return; }
    setLoading(true);
    setError("");
    try {
      const sc = await scorecardApi.computeScorecard(carrierId, periodDays, threshold);
      navigate(`/scorecards/${sc.id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg || "Computation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 max-w-xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Compute Scorecard</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Auto-calculates on-time rate, claim quality, frequency and resolution speed from live data.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-5">
        {/* Carrier */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Carrier</label>
          {carriers.length > 0 ? (
            <select
              value={carrierId}
              onChange={e => setCarrierId(e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            >
              <option value="">Select carrier…</option>
              {carriers.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : (
            <input
              type="text"
              value={carrierId}
              onChange={e => setCarrierId(e.target.value)}
              placeholder="e.g. BlueDart"
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
          )}
        </div>

        {/* Period */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Period — last <span className="font-mono text-blue-600">{periodDays}</span> days
          </label>
          <input
            type="range"
            min={7} max={90} step={7}
            value={periodDays}
            onChange={e => setPeriodDays(Number(e.target.value))}
            className="w-full accent-blue-600"
          />
          <div className="flex justify-between text-xs text-slate-400 mt-0.5">
            <span>7 days</span><span>30 days</span><span>90 days</span>
          </div>
        </div>

        {/* Threshold */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Breach threshold — <span className="font-mono text-blue-600">{threshold}</span>/100
          </label>
          <input
            type="range"
            min={50} max={95} step={5}
            value={threshold}
            onChange={e => setThreshold(Number(e.target.value))}
            className="w-full accent-blue-600"
          />
          <div className="flex justify-between text-xs text-slate-400 mt-0.5">
            <span>50</span><span>70 (default)</span><span>95</span>
          </div>
        </div>

        {/* Formula preview */}
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3">
          <p className="text-xs font-medium text-slate-600 mb-1">Composite formula</p>
          <p className="text-xs text-slate-500 font-mono">
            0.40 × on_time + 0.30 × quality + 0.20 × frequency + 0.10 × resolution
          </p>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-blue-600 text-white font-medium rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Computing…" : "Compute Scorecard"}
        </button>
      </form>
    </div>
  );
}

import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { cn } from "@/utils/cn";
import { ArrowLeft, AlertTriangle, Clock, DollarSign, Truck } from "lucide-react";

const CARRIERS = [
  "BlueDart", "Delhivery", "FedEx India", "DTDC", "Ekart",
  "UPS India", "Xpressbees", "Shadowfax", "Ecom Express", "Other",
];

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "SGD"];

function computeBreach(committedEta: string, actualDelivery: string): number {
  if (!committedEta || !actualDelivery) return 0;
  const eta  = new Date(committedEta).getTime();
  const actual = new Date(actualDelivery).getTime();
  if (isNaN(eta) || isNaN(actual)) return 0;
  return Math.max(0, (actual - eta) / 3_600_000);
}

function computePenalty(breachHours: number, ratePerHour: number, cap: number): number {
  return Math.min(cap, breachHours * ratePerHour);
}

export default function NewException() {
  const nav = useNavigate();
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState<string | null>(null);

  const [form, setForm] = useState({
    carrier:              "",
    shipment_reference:   "",
    committed_eta:        "",
    actual_delivery:      "",
    origin:               "",
    destination:          "",
    penalty_rate_per_hour: 500,
    penalty_cap:          50000,
    currency:             "INR",
    description:          "",
  });

  const set = (field: string, value: string | number) =>
    setForm(f => ({ ...f, [field]: value }));

  const breachHours = useMemo(
    () => computeBreach(form.committed_eta, form.actual_delivery),
    [form.committed_eta, form.actual_delivery]
  );

  const penaltyAmount = useMemo(
    () => computePenalty(breachHours, Number(form.penalty_rate_per_hour), Number(form.penalty_cap)),
    [breachHours, form.penalty_rate_per_hour, form.penalty_cap]
  );

  const fmt = (n: number) => new Intl.NumberFormat("en-IN", {
    style: "currency", currency: form.currency, maximumFractionDigits: 0,
  }).format(n);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.carrier || !form.shipment_reference || !form.committed_eta || !form.actual_delivery) {
      setError("Please fill in all required fields.");
      return;
    }
    if (breachHours <= 0) {
      setError("Actual delivery must be after committed ETA to report an SLA breach.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const exc = await zoikoApi.createException({
        carrier:              form.carrier,
        shipment_reference:   form.shipment_reference,
        committed_eta:        new Date(form.committed_eta).toISOString(),
        actual_delivery:      new Date(form.actual_delivery).toISOString(),
        origin:               form.origin,
        destination:          form.destination,
        penalty_rate_per_hour: Number(form.penalty_rate_per_hour),
        penalty_cap:          Number(form.penalty_cap),
        currency:             form.currency,
        description:          form.description,
        event_stream:         [],
      });
      nav(`/exceptions/${exc.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submission failed. Check that the SC-003 gateway is running on port 8020.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => nav(-1)}
          className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
        >
          <ArrowLeft className="h-4 w-4 text-slate-500" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-slate-800">Report Shipment Exception</h1>
          <p className="text-xs text-slate-500 mt-0.5">SC-003 · SLA breach detection pipeline</p>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" /> {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Carrier & Reference */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Truck className="h-4 w-4 text-slate-400" />
            <span className="text-sm font-semibold text-slate-700">Carrier & Shipment</span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Carrier <span className="text-red-500">*</span></label>
              <select
                value={form.carrier}
                onChange={e => set("carrier", e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30 bg-white"
                required
              >
                <option value="">Select carrier…</option>
                {CARRIERS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Shipment Reference <span className="text-red-500">*</span></label>
              <input
                value={form.shipment_reference}
                onChange={e => set("shipment_reference", e.target.value)}
                placeholder="AWB-2024-001234"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Origin</label>
              <input
                value={form.origin}
                onChange={e => set("origin", e.target.value)}
                placeholder="Mumbai"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Destination</label>
              <input
                value={form.destination}
                onChange={e => set("destination", e.target.value)}
                placeholder="Delhi"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
          </div>
        </div>

        {/* SLA Timeline */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="h-4 w-4 text-slate-400" />
            <span className="text-sm font-semibold text-slate-700">SLA Timeline</span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Committed ETA <span className="text-red-500">*</span></label>
              <input
                type="datetime-local"
                value={form.committed_eta}
                onChange={e => set("committed_eta", e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Actual Delivery <span className="text-red-500">*</span></label>
              <input
                type="datetime-local"
                value={form.actual_delivery}
                onChange={e => set("actual_delivery", e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                required
              />
            </div>
          </div>

          {/* Live breach preview */}
          {form.committed_eta && form.actual_delivery && (
            <div className={cn(
              "rounded-lg p-4 border",
              breachHours > 0
                ? "bg-amber-50 border-amber-200"
                : "bg-emerald-50 border-emerald-200"
            )}>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-600">SLA Breach</span>
                <span className={cn(
                  "text-lg font-bold tabular-nums",
                  breachHours > 0 ? "text-amber-700" : "text-emerald-700"
                )}>
                  {breachHours > 0 ? `+${breachHours.toFixed(2)}h` : "On time"}
                </span>
              </div>
              {breachHours > 0 && (
                <p className="text-xs text-amber-600 mt-1">
                  {Math.floor(breachHours)}h {Math.round((breachHours % 1) * 60)}m past committed ETA
                </p>
              )}
            </div>
          )}
        </div>

        {/* Penalty Config */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <DollarSign className="h-4 w-4 text-slate-400" />
            <span className="text-sm font-semibold text-slate-700">Penalty Configuration</span>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Currency</label>
              <select
                value={form.currency}
                onChange={e => set("currency", e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30 bg-white"
              >
                {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Rate / Hour</label>
              <input
                type="number" min={1} step={1}
                value={form.penalty_rate_per_hour}
                onChange={e => set("penalty_rate_per_hour", Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Penalty Cap</label>
              <input
                type="number" min={1} step={1}
                value={form.penalty_cap}
                onChange={e => set("penalty_cap", Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
          </div>

          {/* Live penalty preview */}
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-slate-500">Calculated Penalty</p>
              <p className="text-2xl font-bold text-slate-800 tabular-nums mt-0.5">{fmt(penaltyAmount)}</p>
              {penaltyAmount >= Number(form.penalty_cap) && (
                <p className="text-[10px] text-amber-600 mt-1">Capped at maximum</p>
              )}
            </div>
            <div className="text-right text-xs text-slate-400">
              <p>{breachHours.toFixed(2)}h × {fmt(Number(form.penalty_rate_per_hour))}/h</p>
              <p>Cap: {fmt(Number(form.penalty_cap))}</p>
            </div>
          </div>
        </div>

        {/* Description */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <label className="block text-xs font-medium text-slate-600 mb-2">Description / Notes</label>
          <textarea
            value={form.description}
            onChange={e => set("description", e.target.value)}
            rows={3}
            placeholder="Add context about the SLA breach…"
            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30 resize-none"
          />
        </div>

        {/* Submit */}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => nav(-1)}
            className="flex-1 px-4 py-2.5 border border-slate-200 text-slate-600 text-sm font-semibold rounded-lg hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex-1 px-4 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving ? "Submitting…" : "Submit Exception"}
          </button>
        </div>
      </form>
    </div>
  );
}

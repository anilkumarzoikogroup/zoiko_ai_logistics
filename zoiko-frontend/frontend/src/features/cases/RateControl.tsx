import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { api } from "@/api/client";
import { cn } from "@/utils/cn";
import { Trash2, Plus, Info, X, ChevronDown, ChevronUp, Wand2, UploadCloud, CheckCircle2 } from "lucide-react";
import { useToast } from "@/hooks/useToast";

const RATE_TYPE_META: Record<string, { label: string; color: string; desc: string }> = {
  fuel_charge:  { label: "Fuel Charge",  color: "bg-blue-100 text-blue-700",   desc: "Fuel surcharge agreed per shipment" },
  accessorial:  { label: "Accessorial",  color: "bg-orange-100 text-orange-700", desc: "Handling, loading, additional fees" },
  base_rate:    { label: "Base Rate",    color: "bg-purple-100 text-purple-700", desc: "Base freight rate for the lane"     },
  surcharge:    { label: "Surcharge",    color: "bg-cyan-100 text-cyan-700",    desc: "Temporary or seasonal surcharge"    },
};

const CARRIERS = ["BlueDart", "Delhivery", "FedEx India", "DTDC", "Ekart", "UPS India", "V Express", "Gati", "DHL", "Aramex", "Other"];
const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED"];

interface AddForm {
  carrier_id:   string;
  rate_type:    string;
  rate_value:   string;
  currency:     string;
  effective_on: string;
  expires_on:   string;
}

const EMPTY: AddForm = {
  carrier_id: "", rate_type: "fuel_charge", rate_value: "",
  currency: "INR", effective_on: new Date().toISOString().slice(0, 10), expires_on: "",
};

export default function RateControl() {
  const qc    = useQueryClient();
  const toast = useToast();

  const [showAdd, setShowAdd]       = useState(false);
  const [form, setForm]             = useState<AddForm>(EMPTY);
  const [expandedCarrier, setExpanded] = useState<string | null>(null);
  const [err, setErr]               = useState("");

  // AI contract extraction
  const [aiLoading,   setAiLoading]   = useState(false);
  const [aiRates,     setAiRates]     = useState<AddForm[]>([]);
  const [aiSaving,    setAiSaving]    = useState(false);
  const contractRef = useRef<HTMLInputElement>(null);

  const { data: rates = [], isLoading } = useQuery({
    queryKey: ["contract-rates"],
    queryFn:  zoikoApi.listContractRates,
  });

  const addM = useMutation({
    mutationFn: () => zoikoApi.createContractRate({
      carrier_id:   form.carrier_id,
      rate_type:    form.rate_type,
      rate_value:   parseFloat(form.rate_value),
      currency:     form.currency,
      effective_on: form.effective_on,
      ...(form.expires_on ? { expires_on: form.expires_on } : {}),
    } as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contract-rates"] });
      toast.success("Rate added", `${form.carrier_id} · ${form.rate_type} · ${form.currency} ${form.rate_value}`);
      setForm(EMPTY);
      setShowAdd(false);
      setErr("");
    },
    onError: (e: any) => {
      setErr(e?.response?.data?.detail ?? "Failed to add rate.");
    },
  });

  const delM = useMutation({
    mutationFn: zoikoApi.deleteContractRate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contract-rates"] });
      toast.success("Rate deleted");
    },
  });

  // Group rates by carrier to show totals
  const byCarrier: Record<string, typeof rates> = {};
  for (const r of rates) {
    if (!byCarrier[r.carrier]) byCarrier[r.carrier] = [];
    byCarrier[r.carrier].push(r);
  }

  const canAdd = form.carrier_id && form.rate_value && parseFloat(form.rate_value) > 0 && form.effective_on;

  async function handleContractUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAiLoading(true); setAiRates([]);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/ingestion/extract-contract-rates", fd);
      setAiRates((data.extracted_rates || []).map((r: any) => ({
        carrier_id:   r.carrier_id,
        rate_type:    r.rate_type,
        rate_value:   String(r.rate_value),
        currency:     r.currency,
        effective_on: r.effective_on,
        expires_on:   r.expires_on || "",
      })));
      toast.success("AI extracted rates", `Found ${data.count} rate(s). Review and save.`);
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? "AI extraction failed.";
      toast.error("Extraction failed", msg);
    } finally {
      setAiLoading(false);
      if (contractRef.current) contractRef.current.value = "";
    }
  }

  async function saveAiRates() {
    setAiSaving(true);
    let saved = 0;
    for (const r of aiRates) {
      try {
        await zoikoApi.createContractRate({
          carrier_id:   r.carrier_id,
          rate_type:    r.rate_type,
          rate_value:   parseFloat(r.rate_value),
          currency:     r.currency,
          effective_on: r.effective_on,
          ...(r.expires_on ? { expires_on: r.expires_on } : {}),
        });
        saved++;
      } catch { /* skip invalid rows */ }
    }
    qc.invalidateQueries({ queryKey: ["contract-rates"] });
    toast.success("Rates saved", `${saved} of ${aiRates.length} rates added.`);
    setAiRates([]);
    setAiSaving(false);
  }

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zoiko-navy">Rate Control</h1>
          <p className="text-sm text-muted-foreground mt-1">Carrier contract rates — used to detect overcharges</p>
        </div>
        <div className="flex items-center gap-2">
          {/* AI import from contract PDF */}
          <button
            onClick={() => contractRef.current?.click()}
            disabled={aiLoading}
            className="flex items-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition-colors"
          >
            {aiLoading
              ? <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />Extracting…</>
              : <><Wand2 className="h-4 w-4" />Import from Contract</>
            }
          </button>
          <input ref={contractRef} type="file" accept=".pdf,.txt" className="hidden" onChange={handleContractUpload} />

          <button
            onClick={() => { setShowAdd(v => !v); setErr(""); }}
            className="flex items-center gap-1.5 px-4 py-2 bg-zoiko-navy hover:bg-zoiko-navy/90 text-white rounded-lg text-sm font-semibold transition-colors"
          >
            {showAdd ? <><X className="h-4 w-4" />Cancel</> : <><Plus className="h-4 w-4" />Add Rate</>}
          </button>
        </div>
      </div>

      {/* AI extracted rates preview */}
      {aiRates.length > 0 && (
        <div className="rounded-xl border border-purple-200 bg-purple-50 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-bold text-purple-800 flex items-center gap-1.5">
              <Wand2 className="h-4 w-4" /> AI extracted {aiRates.length} rate(s) — review before saving
            </p>
            <button onClick={() => setAiRates([])} className="text-purple-400 hover:text-purple-700"><X className="h-4 w-4" /></button>
          </div>
          <div className="space-y-1.5">
            {aiRates.map((r, i) => (
              <div key={i} className="flex items-center gap-3 bg-white rounded-lg border border-purple-100 px-3 py-2 text-xs">
                <span className="font-semibold text-slate-700 w-28 truncate">{r.carrier_id}</span>
                <span className="text-purple-700 bg-purple-100 px-2 py-0.5 rounded-full font-semibold">{r.rate_type}</span>
                <span className="font-mono font-bold text-slate-800">{r.currency} {parseFloat(r.rate_value).toLocaleString()}</span>
                <span className="text-slate-400 ml-auto">from {r.effective_on}</span>
                <button onClick={() => setAiRates(prev => prev.filter((_, j) => j !== i))} className="text-slate-300 hover:text-red-500">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
          <button
            onClick={saveAiRates}
            disabled={aiSaving}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition-colors"
          >
            {aiSaving
              ? <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />Saving…</>
              : <><CheckCircle2 className="h-4 w-4" />Save all {aiRates.length} rates to contract</>
            }
          </button>
        </div>
      )}

      {/* How it works callout */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 flex gap-3">
        <Info className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-blue-800 space-y-1">
          <p className="font-bold">How overcharge detection works</p>
          <p>The system <strong>sums all rate rows for a carrier</strong> to get the total contracted amount, then compares against the billed amount.</p>
          <p className="font-mono bg-blue-100 rounded px-2 py-1 text-blue-900 mt-1">
            fuel_charge ($6,000) + accessorial ($2,000) = contracted total ($8,000)
            <br />BlueDart bills $12,500 → overcharge = $4,500
          </p>
          <p>You need at least <strong>one rate row per carrier</strong>. Add more rows for each charge type in the contract.</p>
        </div>
      </div>

      {/* Add Rate Form */}
      {showAdd && (
        <div className="rounded-xl border border-zoiko-navy/20 bg-zoiko-navy/5 p-5 space-y-4">
          <p className="text-sm font-bold text-zoiko-navy">New Contract Rate</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Carrier</label>
              <select
                value={form.carrier_id}
                onChange={e => setForm(f => ({ ...f, carrier_id: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zoiko-navy"
              >
                <option value="">Select carrier…</option>
                {CARRIERS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Rate Type</label>
              <select
                value={form.rate_type}
                onChange={e => setForm(f => ({ ...f, rate_type: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zoiko-navy"
              >
                {Object.entries(RATE_TYPE_META).map(([k, v]) => (
                  <option key={k} value={k}>{v.label} — {v.desc}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Rate Value (agreed amount)</label>
              <input
                type="number"
                placeholder="e.g. 6000"
                value={form.rate_value}
                onChange={e => setForm(f => ({ ...f, rate_value: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zoiko-navy"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Currency</label>
              <select
                value={form.currency}
                onChange={e => setForm(f => ({ ...f, currency: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zoiko-navy"
              >
                {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Effective From</label>
              <input
                type="date"
                value={form.effective_on}
                onChange={e => setForm(f => ({ ...f, effective_on: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zoiko-navy"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Expires On (optional)</label>
              <input
                type="date"
                value={form.expires_on}
                onChange={e => setForm(f => ({ ...f, expires_on: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zoiko-navy"
              />
            </div>
          </div>

          {/* Preview */}
          {form.carrier_id && form.rate_value && (
            <div className="rounded-lg bg-white border border-slate-200 px-4 py-2.5 text-xs text-slate-600">
              Preview: <strong>{form.carrier_id}</strong> · {RATE_TYPE_META[form.rate_type]?.label} = <strong>{form.currency} {parseFloat(form.rate_value || "0").toLocaleString()}</strong>
              {byCarrier[form.carrier_id] && (
                <span className="ml-2 text-slate-400">
                  (existing total: {form.currency} {byCarrier[form.carrier_id].reduce((s, r) => s + r.rate_value, 0).toLocaleString()} → new total: {form.currency} {(byCarrier[form.carrier_id].reduce((s, r) => s + r.rate_value, 0) + (parseFloat(form.rate_value) || 0)).toLocaleString()})
                </span>
              )}
            </div>
          )}

          {err && <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{err}</p>}

          <button
            disabled={!canAdd || addM.isPending}
            onClick={() => addM.mutate()}
            className={cn(
              "w-full py-2.5 rounded-lg text-sm font-semibold transition-colors flex items-center justify-center gap-2",
              canAdd && !addM.isPending
                ? "bg-zoiko-navy text-white hover:bg-zoiko-navy/90"
                : "bg-slate-200 text-slate-400 cursor-not-allowed"
            )}
          >
            {addM.isPending
              ? <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />Saving…</>
              : <><Plus className="h-4 w-4" />Add Rate</>
            }
          </button>
        </div>
      )}

      {/* Rates grouped by carrier */}
      {isLoading ? (
        <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-16 bg-slate-100 rounded-xl animate-pulse" />)}</div>
      ) : rates.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center space-y-2">
          <p className="text-sm font-semibold text-slate-500">No contract rates yet</p>
          <p className="text-xs text-slate-400">Click "Add Rate" to enter your first carrier contract rate.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {Object.entries(byCarrier).map(([carrier, rows]) => {
            const total    = rows.reduce((s, r) => s + r.rate_value, 0);
            const currency = rows[0]?.currency ?? "INR";
            const open     = expandedCarrier === carrier;
            return (
              <div key={carrier} className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                {/* Carrier header */}
                <button
                  className="w-full flex items-center justify-between px-5 py-4 hover:bg-slate-50 transition-colors"
                  onClick={() => setExpanded(open ? null : carrier)}
                >
                  <div className="flex items-center gap-3">
                    <div className="h-9 w-9 rounded-lg bg-zoiko-navy/10 flex items-center justify-center text-sm font-bold text-zoiko-navy">
                      {carrier.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="text-left">
                      <p className="text-sm font-bold text-slate-800">{carrier}</p>
                      <p className="text-[11px] text-slate-400">{rows.length} rate component{rows.length !== 1 ? "s" : ""}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <p className="text-xs text-slate-400">Total contracted</p>
                      <p className="text-base font-bold text-zoiko-navy">{currency} {total.toLocaleString()}</p>
                    </div>
                    {open ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
                  </div>
                </button>

                {/* Rate rows */}
                {open && (
                  <div className="border-t border-slate-100 divide-y divide-slate-100">
                    {rows.map(r => {
                      const meta = RATE_TYPE_META[r.rate_type] ?? { label: r.rate_type, color: "bg-slate-100 text-slate-600", desc: "" };
                      const expired = r.expires_on ? new Date(r.expires_on) < new Date() : false;
                      return (
                        <div key={r.id} className="flex items-center gap-4 px-5 py-3">
                          <span className={cn("text-[10px] font-bold px-2.5 py-1 rounded-full w-28 text-center", meta.color)}>
                            {meta.label}
                          </span>
                          <p className="text-sm font-semibold text-slate-700 flex-1">
                            {r.currency} {r.rate_value.toLocaleString()}
                          </p>
                          <p className="text-xs text-slate-400">from {r.effective_on}</p>
                          {r.expires_on && (
                            <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full",
                              expired ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
                            )}>
                              {expired ? "expired" : `until ${r.expires_on}`}
                            </span>
                          )}
                          <button
                            onClick={() => delM.mutate(r.id)}
                            disabled={delM.isPending}
                            className="text-slate-300 hover:text-red-500 transition-colors ml-2"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      );
                    })}
                    <div className="flex items-center justify-end gap-2 px-5 py-2.5 bg-slate-50">
                      <span className="text-xs text-slate-500">Total contracted rate used for validation:</span>
                      <span className="text-sm font-bold text-zoiko-navy">{currency} {total.toLocaleString()}</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

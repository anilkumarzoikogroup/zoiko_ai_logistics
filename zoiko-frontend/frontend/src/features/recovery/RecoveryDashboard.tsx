import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { cn, formatCurrency } from "@/utils/cn";
import {
  Wallet, FileCheck, Link2, AlertTriangle, Plus, X,
  CheckCircle2, RefreshCw, Undo2,
} from "lucide-react";

const ALLOC_BADGE: Record<string, string> = {
  FULL:     "bg-emerald-100 text-emerald-700 border-emerald-200",
  PARTIAL:  "bg-amber-100 text-amber-700 border-amber-200",
  REVERSED: "bg-slate-100 text-slate-500 border-slate-200",
};

const STATUS_BADGE: Record<string, string> = {
  OPEN:      "bg-amber-100 text-amber-700 border-amber-200",
  MATCHED:   "bg-blue-100 text-blue-700 border-blue-200",
  PARTIAL:   "bg-amber-100 text-amber-700 border-amber-200",
  CLOSED:    "bg-emerald-100 text-emerald-700 border-emerald-200",
  AVAILABLE: "bg-blue-100 text-blue-700 border-blue-200",
  CONSUMED:  "bg-slate-100 text-slate-500 border-slate-200",
};

function Badge({ status }: { status: string }) {
  return (
    <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border", STATUS_BADGE[status] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
      {status}
    </span>
  );
}

export default function RecoveryDashboard() {
  const qc = useQueryClient();
  const [caseId, setCaseId] = useState("");
  const [activeCaseId, setActiveCaseId] = useState("");
  const [showExpectedForm, setShowExpectedForm] = useState(false);
  const [showInstrumentForm, setShowInstrumentForm] = useState(false);

  const [expectedForm, setExpectedForm] = useState({
    expected_amount: "",
    currency: "INR",
    expected_recovery_method: "carrier_credit_memo",
    counterparty_id: "",
    expected_external_invoice_ref: "",
  });

  const [instrumentForm, setInstrumentForm] = useState({
    instrument_type: "credit_memo",
    instrument_amount: "",
    currency: "INR",
    counterparty_id: "",
    external_reference: "",
    related_external_invoice_ref: "",
  });

  const enabled = !!activeCaseId;

  const expectedQ = useQuery({
    queryKey: ["recovery-expected", activeCaseId],
    queryFn: () => zoikoApi.listExpectedRecoveriesByCase(activeCaseId),
    enabled,
  });

  const instrumentsQ = useQuery({
    queryKey: ["recovery-instruments", activeCaseId],
    queryFn: () => zoikoApi.listRecoveryInstrumentsByCase(activeCaseId),
    enabled,
  });

  const matchesQ = useQuery({
    queryKey: ["recovery-matches", activeCaseId],
    queryFn: () => zoikoApi.listRecoveryMatchesByCase(activeCaseId),
    enabled,
  });

  const proofQ = useQuery({
    queryKey: ["recovery-proof", activeCaseId],
    queryFn: () => zoikoApi.getLatestRecoveryProof(activeCaseId),
    enabled,
  });

  const exceptionsQ = useQuery({
    queryKey: ["recovery-exceptions", activeCaseId],
    queryFn: () => zoikoApi.listRecoveryExceptions(activeCaseId),
    enabled,
  });

  function invalidateAll() {
    qc.invalidateQueries({ queryKey: ["recovery-expected", activeCaseId] });
    qc.invalidateQueries({ queryKey: ["recovery-instruments", activeCaseId] });
    qc.invalidateQueries({ queryKey: ["recovery-matches", activeCaseId] });
    qc.invalidateQueries({ queryKey: ["recovery-proof", activeCaseId] });
    qc.invalidateQueries({ queryKey: ["recovery-exceptions", activeCaseId] });
  }

  const createExpectedMut = useMutation({
    mutationFn: () => zoikoApi.createExpectedRecovery({
      case_id: activeCaseId,
      expected_amount: parseFloat(expectedForm.expected_amount),
      currency: expectedForm.currency,
      expected_recovery_method: expectedForm.expected_recovery_method,
      counterparty_id: expectedForm.counterparty_id || undefined,
      expected_external_invoice_ref: expectedForm.expected_external_invoice_ref || undefined,
    }),
    onSuccess: () => {
      setShowExpectedForm(false);
      setExpectedForm({ expected_amount: "", currency: "INR", expected_recovery_method: "carrier_credit_memo", counterparty_id: "", expected_external_invoice_ref: "" });
      invalidateAll();
    },
  });

  const createInstrumentMut = useMutation({
    mutationFn: () => zoikoApi.createRecoveryInstrument({
      instrument_type: instrumentForm.instrument_type,
      instrument_amount: parseFloat(instrumentForm.instrument_amount),
      currency: instrumentForm.currency,
      counterparty_id: instrumentForm.counterparty_id || undefined,
      related_case_id: activeCaseId,
      external_reference: instrumentForm.external_reference || undefined,
      related_external_invoice_ref: instrumentForm.related_external_invoice_ref || undefined,
    }),
    onSuccess: () => {
      setShowInstrumentForm(false);
      setInstrumentForm({ instrument_type: "credit_memo", instrument_amount: "", currency: "INR", counterparty_id: "", external_reference: "", related_external_invoice_ref: "" });
      invalidateAll();
    },
  });

  const matchMut = useMutation({
    mutationFn: (expectedRecoveryId: string) => zoikoApi.createRecoveryMatch(expectedRecoveryId),
    onSuccess: invalidateAll,
  });

  const reverseMatchMut = useMutation({
    mutationFn: (matchId: string) => zoikoApi.reverseRecoveryMatch(matchId, "Manual reversal from UI"),
    onSuccess: invalidateAll,
  });

  const proofMut = useMutation({
    mutationFn: () => zoikoApi.generateRecoveryProof(activeCaseId),
    onSuccess: invalidateAll,
  });

  const expected = expectedQ.data ?? [];
  const instruments = instrumentsQ.data ?? [];
  const matches = matchesQ.data ?? [];
  const proof = proofQ.data;
  const exceptions = exceptionsQ.data ?? [];

  const totalExpected = expected.reduce((s, e) => s + e.expected_amount, 0);
  const totalInstruments = instruments.reduce((s, i) => s + i.instrument_amount, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Recovery Pipeline</h1>
        <p className="text-sm text-slate-500 mt-0.5">Phase 6 — Expected recoveries → instruments → matches → proof → ACR</p>
      </div>

      {/* Case lookup */}
      <Card>
        <CardContent className="p-5">
          <h2 className="font-semibold text-slate-700 text-sm mb-3">Look up a case</h2>
          <div className="flex gap-2">
            <input
              value={caseId}
              onChange={e => setCaseId(e.target.value)}
              placeholder="Case ID (UUID)"
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
            />
            <button
              onClick={() => setActiveCaseId(caseId.trim())}
              disabled={!caseId.trim()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Load
            </button>
          </div>
        </CardContent>
      </Card>

      {!enabled ? (
        <p className="text-sm text-slate-400 text-center py-10">Enter a case ID above to view its recovery pipeline.</p>
      ) : (
        <>
          {/* Summary tiles */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-white rounded-xl border border-slate-200 border-l-4 border-l-blue-400 px-4 py-3 shadow-sm">
              <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Total Expected</p>
              <p className="text-xl font-bold mt-1 text-blue-700">{formatCurrency(totalExpected, expected[0]?.currency ?? "INR")}</p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 border-l-4 border-l-emerald-400 px-4 py-3 shadow-sm">
              <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Total Instruments</p>
              <p className="text-xl font-bold mt-1 text-emerald-700">{formatCurrency(totalInstruments, instruments[0]?.currency ?? "INR")}</p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 border-l-4 border-l-purple-400 px-4 py-3 shadow-sm">
              <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Matches</p>
              <p className="text-xl font-bold mt-1 text-purple-700">{matches.length}</p>
            </div>
            <div className={cn("bg-white rounded-xl border border-slate-200 border-l-4 px-4 py-3 shadow-sm", proof?.acr_ready ? "border-l-emerald-400" : "border-l-slate-300")}>
              <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">ACR Ready</p>
              <p className={cn("text-xl font-bold mt-1", proof?.acr_ready ? "text-emerald-700" : "text-slate-400")}>
                {proof ? (proof.acr_ready ? "Yes" : "No") : "—"}
              </p>
            </div>
          </div>

          {/* Expected Recoveries */}
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Wallet className="h-4 w-4 text-blue-500" />
                  <h2 className="font-semibold text-slate-700 text-sm">Expected Recoveries</h2>
                </div>
                <button
                  onClick={() => setShowExpectedForm(v => !v)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition-colors"
                >
                  {showExpectedForm ? <X className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
                  {showExpectedForm ? "Cancel" : "New"}
                </button>
              </div>

              {showExpectedForm && (
                <div className="mb-4 p-4 bg-slate-50 rounded-lg border border-slate-200">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Expected Amount *</label>
                      <input type="number" value={expectedForm.expected_amount}
                        onChange={e => setExpectedForm(f => ({ ...f, expected_amount: e.target.value }))}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Currency</label>
                      <input value={expectedForm.currency}
                        onChange={e => setExpectedForm(f => ({ ...f, currency: e.target.value }))}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Method</label>
                      <select value={expectedForm.expected_recovery_method}
                        onChange={e => setExpectedForm(f => ({ ...f, expected_recovery_method: e.target.value }))}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30">
                        {["carrier_credit_memo","carrier_refund","short_pay_next_invoice","bank_transfer"].map(m => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Counterparty ID</label>
                      <input value={expectedForm.counterparty_id}
                        onChange={e => setExpectedForm(f => ({ ...f, counterparty_id: e.target.value }))}
                        placeholder="carrier UUID (optional)"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-xs font-medium text-slate-600 mb-1">External Invoice Ref</label>
                      <input value={expectedForm.expected_external_invoice_ref}
                        onChange={e => setExpectedForm(f => ({ ...f, expected_external_invoice_ref: e.target.value }))}
                        placeholder="optional"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                    </div>
                  </div>
                  {createExpectedMut.error && <p className="text-xs text-red-600 mt-2">{String(createExpectedMut.error)}</p>}
                  <div className="mt-3 flex justify-end">
                    <button
                      onClick={() => createExpectedMut.mutate()}
                      disabled={!expectedForm.expected_amount || createExpectedMut.isPending}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                      {createExpectedMut.isPending ? "Creating…" : "Create"}
                    </button>
                  </div>
                </div>
              )}

              {expectedQ.isLoading ? (
                <p className="text-sm text-slate-400 text-center py-4">Loading…</p>
              ) : expected.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-4">No expected recoveries for this case yet.</p>
              ) : (
                <div className="divide-y divide-slate-50">
                  {expected.map(e => (
                    <div key={e.expected_recovery_id} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-slate-700">{formatCurrency(e.expected_amount, e.currency)}</span>
                          <Badge status={e.status} />
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          {e.expected_recovery_method} · {e.expected_recovery_id.slice(0, 8)}…
                        </p>
                      </div>
                      {e.status === "OPEN" && (
                        <button
                          onClick={() => matchMut.mutate(e.expected_recovery_id)}
                          disabled={matchMut.isPending}
                          className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition-colors flex-shrink-0 disabled:opacity-50"
                        >
                          <Link2 className="h-3 w-3" /> Match
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {matchMut.error && <p className="text-xs text-red-600 mt-2">{String(matchMut.error)}</p>}
            </CardContent>
          </Card>

          {/* Recovery Instruments */}
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <FileCheck className="h-4 w-4 text-emerald-500" />
                  <h2 className="font-semibold text-slate-700 text-sm">Recovery Instruments</h2>
                </div>
                <button
                  onClick={() => setShowInstrumentForm(v => !v)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition-colors"
                >
                  {showInstrumentForm ? <X className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
                  {showInstrumentForm ? "Cancel" : "New"}
                </button>
              </div>

              {showInstrumentForm && (
                <div className="mb-4 p-4 bg-slate-50 rounded-lg border border-slate-200">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Instrument Type</label>
                      <select value={instrumentForm.instrument_type}
                        onChange={e => setInstrumentForm(f => ({ ...f, instrument_type: e.target.value }))}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30">
                        {["credit_memo","refund","bank_credit","short_pay_offset"].map(t => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Amount *</label>
                      <input type="number" value={instrumentForm.instrument_amount}
                        onChange={e => setInstrumentForm(f => ({ ...f, instrument_amount: e.target.value }))}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Currency</label>
                      <input value={instrumentForm.currency}
                        onChange={e => setInstrumentForm(f => ({ ...f, currency: e.target.value }))}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Counterparty ID</label>
                      <input value={instrumentForm.counterparty_id}
                        onChange={e => setInstrumentForm(f => ({ ...f, counterparty_id: e.target.value }))}
                        placeholder="carrier UUID (optional)"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">External Reference</label>
                      <input value={instrumentForm.external_reference}
                        onChange={e => setInstrumentForm(f => ({ ...f, external_reference: e.target.value }))}
                        placeholder="e.g. credit memo number"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Related Invoice Ref</label>
                      <input value={instrumentForm.related_external_invoice_ref}
                        onChange={e => setInstrumentForm(f => ({ ...f, related_external_invoice_ref: e.target.value }))}
                        placeholder="optional"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                    </div>
                  </div>
                  {createInstrumentMut.error && <p className="text-xs text-red-600 mt-2">{String(createInstrumentMut.error)}</p>}
                  <div className="mt-3 flex justify-end">
                    <button
                      onClick={() => createInstrumentMut.mutate()}
                      disabled={!instrumentForm.instrument_amount || createInstrumentMut.isPending}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                      {createInstrumentMut.isPending ? "Creating…" : "Create"}
                    </button>
                  </div>
                </div>
              )}

              {instrumentsQ.isLoading ? (
                <p className="text-sm text-slate-400 text-center py-4">Loading…</p>
              ) : instruments.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-4">No recovery instruments for this case yet.</p>
              ) : (
                <div className="divide-y divide-slate-50">
                  {instruments.map(i => (
                    <div key={i.recovery_instrument_id} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-slate-700">{formatCurrency(i.instrument_amount, i.currency)}</span>
                          <Badge status={i.status} />
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          {i.instrument_type} · {i.recovery_instrument_id.slice(0, 8)}… · by {i.created_by}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Matches */}
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <Link2 className="h-4 w-4 text-purple-500" />
                <h2 className="font-semibold text-slate-700 text-sm">Recovery Matches</h2>
              </div>
              {matchesQ.isLoading ? (
                <p className="text-sm text-slate-400 text-center py-4">Loading…</p>
              ) : matches.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-4">No matches yet — click "Match" on an expected recovery above.</p>
              ) : (
                <div className="divide-y divide-slate-50">
                  {matches.map(m => (
                    <div key={m.match_id} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-slate-700">{formatCurrency(m.matched_amount, m.currency)}</span>
                          <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border", ALLOC_BADGE[m.allocation_status] ?? "bg-slate-100 text-slate-500 border-slate-200")}>
                            {m.allocation_status}
                          </span>
                          {m.match_tier != null && (
                            <span className="text-[10px] text-slate-400">Tier {m.match_tier}</span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          variance {formatCurrency(m.variance, m.currency)} · matched by {m.matched_by} · {new Date(m.matched_at).toLocaleString()}
                        </p>
                      </div>
                      {m.allocation_status !== "REVERSED" && (
                        <button
                          onClick={() => reverseMatchMut.mutate(m.match_id)}
                          disabled={reverseMatchMut.isPending}
                          className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition-colors flex-shrink-0 disabled:opacity-50"
                        >
                          <Undo2 className="h-3 w-3" /> Reverse
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {reverseMatchMut.error && <p className="text-xs text-red-600 mt-2">{String(reverseMatchMut.error)}</p>}
            </CardContent>
          </Card>

          {/* Recovery Proof / ACR readiness */}
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  <h2 className="font-semibold text-slate-700 text-sm">Recovery Proof</h2>
                </div>
                <button
                  onClick={() => proofMut.mutate()}
                  disabled={proofMut.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
                >
                  <RefreshCw className={cn("h-3 w-3", proofMut.isPending && "animate-spin")} />
                  Generate Proof
                </button>
              </div>
              {proofMut.error && <p className="text-xs text-red-600 mb-2">{String(proofMut.error)}</p>}
              {proofQ.isLoading ? (
                <p className="text-sm text-slate-400 text-center py-4">Loading…</p>
              ) : !proof ? (
                <p className="text-sm text-slate-400 text-center py-4">No recovery proof generated yet.</p>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div>
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Total Expected</p>
                    <p className="text-sm font-bold text-slate-700 mt-1">{formatCurrency(proof.total_expected, proof.currency)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Total Recovered</p>
                    <p className="text-sm font-bold text-emerald-700 mt-1">{formatCurrency(proof.total_recovered, proof.currency)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Unrecovered</p>
                    <p className="text-sm font-bold text-amber-700 mt-1">{formatCurrency(proof.total_unrecovered, proof.currency)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">ACR Ready</p>
                    <p className={cn("text-sm font-bold mt-1", proof.acr_ready ? "text-emerald-700" : "text-slate-400")}>
                      {proof.acr_ready ? "Yes" : "No"}
                    </p>
                  </div>
                  <div className="col-span-2 md:col-span-2">
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Recovery Status</p>
                    <p className="text-sm font-medium text-slate-600 mt-1">{proof.recovery_status}</p>
                  </div>
                  <div className="col-span-2 md:col-span-2">
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Ledger Status</p>
                    <p className="text-sm font-medium text-slate-600 mt-1">{proof.ledger_status}</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Exceptions */}
          {exceptions.length > 0 && (
            <Card>
              <CardContent className="p-5">
                <div className="flex items-center gap-2 mb-4">
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                  <h2 className="font-semibold text-slate-700 text-sm">Recovery Exceptions</h2>
                  <span className="ml-auto text-[10px] font-bold bg-amber-100 text-amber-600 px-2 py-0.5 rounded-full">
                    {exceptions.length}
                  </span>
                </div>
                <div className="divide-y divide-slate-50">
                  {exceptions.map(ex => (
                    <div key={`${ex.exception_type}-${ex.expected_recovery_id}`} className="py-2.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] font-bold bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full border border-amber-200">{ex.exception_type}</span>
                        <span className="text-sm font-semibold text-slate-700">{formatCurrency(ex.amount, ex.currency)}</span>
                        <span className="text-[11px] text-slate-400">{ex.age_days}d old</span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">{ex.detail}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

import { useState, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useToast } from "@/hooks/useToast";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ArrowRight, Info } from "lucide-react";
import axios from "axios";

// SC-002 — manual-entry claim submission. Mirrors NewCase.tsx's "manual" mode
// exactly (same mutation/toast/navigate pattern); no PDF upload/AI parsing —
// that's invoice-specific (parse-invoice endpoint doesn't apply to claims).

const CARRIERS = [
  "BlueDart", "DTDC", "Delhivery", "Ekart", "FedEx India", "FedEx",
  "UPS India", "UPS", "V Express", "Gati", "DHL", "Aramex",
  "Maersk", "MSC", "CMA CGM", "Other",
];
const CLAIM_TYPES = ["DAMAGE", "LOSS", "DELAY", "SHORTAGE", "MISDELIVERY", "OTHER"];
const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD", "JPY", "CNY", "SAR"];

interface FormState {
  carrier: string;
  claim_type: string;
  claimed_amount: string;
  currency: string;
  claim_reference: string;
  related_invoice_number: string;
  description: string;
}

function Combobox({ id, value, onChange, placeholder, suggestions }: {
  id: string; value: string; onChange: (v: string) => void; placeholder: string; suggestions: string[];
}) {
  return (
    <>
      <input
        id={id} list={`${id}-list`} value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder} autoComplete="off"
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <datalist id={`${id}-list`}>
        {suggestions.map(c => <option key={c} value={c} />)}
      </datalist>
    </>
  );
}

export default function NewClaim() {
  const nav   = useNavigate();
  const qc    = useQueryClient();
  const toast = useToast();
  const submitting = useRef(false);

  const [form, setForm] = useState<FormState>({
    carrier: "", claim_type: "DAMAGE", claimed_amount: "", currency: "INR",
    claim_reference: "", related_invoice_number: "", description: "",
  });

  const m = useMutation({
    mutationFn: () => zoikoApi.createClaim({
      carrier:                 form.carrier,
      claim_type:              form.claim_type,
      claimed_amount:          Number(form.claimed_amount),
      currency:                form.currency,
      claim_reference:         form.claim_reference,
      related_invoice_number:  form.related_invoice_number,
      description:             form.description,
    }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["claims"] });
      if (c.duplicate) {
        toast.error("Duplicate claim detected", `This claim was already submitted — showing the existing case (${c.deduplication_outcome ?? "DUPLICATE_OF"}).`);
      } else {
        toast.success("Claim submitted", `Carrier claim pipeline started for ${form.carrier}`);
      }
      nav(`/claims/${c.id}`, { replace: true });
    },
    onError: (err: unknown) => {
      submitting.current = false;
      if (axios.isAxiosError(err)) {
        if (!err.response) {
          toast.error("Request timed out", "The pipeline takes ~10-15s. Check the backend is running on port 8000, then try again.");
        } else if (err.response.status === 401) {
          toast.error("Session expired", "You have been logged out. Please sign in again.");
        } else {
          const detail = err.response.data?.detail || "Submission failed. Try again.";
          toast.error("Submission failed", typeof detail === "string" ? detail : JSON.stringify(detail));
        }
      } else {
        toast.error("Backend unreachable", "Lost connection to the server mid-request. Restart the backend on port 8000 and try again.");
      }
    },
  });

  const canSubmit = form.carrier && form.claim_type && Number(form.claimed_amount) > 0;

  return (
    <div className="max-w-lg mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zoiko-navy">Submit Carrier Claim</h1>
        <p className="text-sm text-muted-foreground mt-1">
          File a damage, loss, delay, or shortage claim against a carrier.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Claim Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => {
            e.preventDefault();
            if (!canSubmit || submitting.current || m.isPending) return;
            submitting.current = true;
            m.mutate();
          }} className="space-y-4">

            <div className="space-y-1.5">
              <Label htmlFor="carrier">Carrier / Logistics Provider</Label>
              <Combobox id="carrier" value={form.carrier} onChange={v => setForm(f => ({ ...f, carrier: v }))}
                placeholder="e.g. BlueDart, DHL, Maersk…" suggestions={CARRIERS} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="claim_type">Claim Type</Label>
                <select
                  id="claim_type" value={form.claim_type}
                  onChange={e => setForm(f => ({ ...f, claim_type: e.target.value }))}
                  className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {CLAIM_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="claim_reference">
                  Claim Reference
                  <span className="ml-1 text-[10px] font-normal text-muted-foreground">(optional)</span>
                </Label>
                <Input id="claim_reference" type="text" placeholder="auto-generated if blank"
                  value={form.claim_reference} onChange={e => setForm(f => ({ ...f, claim_reference: e.target.value }))} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="claimed_amount">Claimed Amount</Label>
                <Input id="claimed_amount" type="number" placeholder="e.g. 5000"
                  value={form.claimed_amount} onChange={e => setForm(f => ({ ...f, claimed_amount: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="currency">Currency</Label>
                <Combobox id="currency" value={form.currency}
                  onChange={v => setForm(f => ({ ...f, currency: v.toUpperCase() }))}
                  placeholder="INR, USD, EUR…" suggestions={CURRENCIES} />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="related_invoice_number">
                Related Invoice Number
                <span className="ml-1 text-[10px] font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Input id="related_invoice_number" type="text" placeholder="e.g. INV-2025-001"
                value={form.related_invoice_number} onChange={e => setForm(f => ({ ...f, related_invoice_number: e.target.value }))} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="description">Description</Label>
              <Textarea id="description" placeholder="Describe the damage, loss, or delay…" rows={3}
                value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
            </div>

            <div className="rounded-lg bg-blue-50 border border-blue-100 px-4 py-3 flex gap-2.5">
              <Info className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-blue-700 leading-relaxed">
                Zoiko opens a governed case for this claim — evidence is bundled, AI scores liability and policy-cap confidence, then it routes to analyst review and manager approval before settlement.
              </p>
            </div>

            <Button type="submit" disabled={m.isPending || submitting.current || !canSubmit} className="w-full gap-2" size="lg">
              {m.isPending ? (
                <><div className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> Submitting… please wait</>
              ) : (
                <><ArrowRight className="h-4 w-4" /> Submit Claim</>
              )}
            </Button>
            {m.isError && (
              <p className="text-sm text-destructive text-center mt-2">
                {axios.isAxiosError(m.error) && !m.error.response
                  ? "Request timed out — pipeline takes ~10-15s. Check the backend is running and try again."
                  : axios.isAxiosError(m.error) && m.error.response?.status === 401
                  ? "Session expired — please log in again."
                  : axios.isAxiosError(m.error) && m.error.response
                  ? `Submission failed — ${(m.error.response.data as any)?.detail || "check the backend terminal for details."}`
                  : "Backend unreachable — restart the backend on port 8000 and try again."}
              </p>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

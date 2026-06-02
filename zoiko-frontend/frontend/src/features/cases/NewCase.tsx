import { useState, useRef, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useToast } from "@/hooks/useToast";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { UploadCloud, FileText, CheckCircle2, X, Pencil, ArrowRight, Info, Lightbulb } from "lucide-react";
import { cn } from "@/utils/cn";
import { USE_MOCK, api } from "@/api/client";

type Mode = "choose" | "upload" | "manual";
type ParseState = "idle" | "parsing" | "done" | "error";

const CARRIERS = ["BlueDart", "DTDC", "Delhivery", "Ekart", "FedEx India", "UPS India", "V Express", "Other"];
const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED"];

const INDIAN_CITIES = [
  "Hyderabad", "Warangal", "Mumbai", "Delhi", "Bangalore",
  "Chennai", "Kolkata", "Pune", "Ahmedabad", "Jaipur",
  "Lucknow", "Surat", "Kochi", "Nagpur", "Vizag",
];

interface FormState {
  carrier: string;
  from_city: string;
  to_city: string;
  amount: string;
  currency: string;
}

async function realParseInvoice(file: File): Promise<{ carrier: string; route: string; amount: number; currency: string; parsed_by?: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post("/ingestion/parse-invoice", fd);
  return data;
}

function splitRoute(route: string): { from_city: string; to_city: string } {
  const parts = route.split(/\s*[-→–]\s*/);
  return { from_city: parts[0]?.trim() || "", to_city: parts[1]?.trim() || "" };
}

export default function NewCase() {
  const nav   = useNavigate();
  const qc    = useQueryClient();
  const toast = useToast();

  const [mode, setMode]             = useState<Mode>("choose");
  const [form, setForm]             = useState<FormState>({ carrier: "", from_city: "", to_city: "", amount: "", currency: "INR" });
  const [file, setFile]             = useState<File | null>(null);
  const [parseState, setParseState] = useState<ParseState>("idle");
  const [parsedBy,  setParsedBy]    = useState<string>("");
  const [dragOver, setDragOver]     = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const m = useMutation({
    mutationFn: () => zoikoApi.createCase({
      carrier:  form.carrier,
      route:    `${form.from_city} → ${form.to_city}`,
      amount:   Number(form.amount),
      currency: form.currency,
    }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["cases"] });
      toast.success("Case submitted", `Overcharge detection pipeline started for ${form.carrier}`);
      nav(`/cases/${c.id}`);
    },
    onError: (err: unknown) => {
      const e = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      const detail = e?.response?.data?.detail;
      const status = e?.response?.status;
      const msg = typeof detail === "string" ? detail
                : typeof detail === "object" ? JSON.stringify(detail)
                : e?.message ?? "Network error — backend may be down";
      toast.error(`Submission failed (${status ?? "no response"})`, msg);
    },
  });

  const processFile = useCallback(async (f: File) => {
    setFile(f);
    setMode("upload");
    if (USE_MOCK) {
      setParseState("done");
      return;
    }
    setParseState("parsing");
    try {
      const parsed = await realParseInvoice(f);
      const { from_city, to_city } = splitRoute(parsed.route);
      setForm({
        carrier:   parsed.carrier || "",
        from_city: from_city || "",
        to_city:   to_city   || "",
        amount:    parsed.amount > 0 ? String(parsed.amount) : "",
        currency:  parsed.currency || "INR",
      });
      setParsedBy(parsed.parsed_by || "regex");
      // If nothing was extracted, treat as a soft parse failure
      const gotData = parsed.carrier || parsed.amount > 0 || from_city;
      setParseState(gotData ? "done" : "error");
    } catch {
      setParseState("error");
    }
  }, []);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) processFile(f);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) processFile(f);
  }

  function clearFile() {
    setFile(null);
    setParseState("idle");
    setMode("choose");
    setForm({ carrier: "", from_city: "", to_city: "", amount: "", currency: "INR" });
    if (inputRef.current) inputRef.current.value = "";
  }

  const canSubmit = form.carrier && form.from_city && form.to_city && Number(form.amount) > 0;

  const formFields = (
    <div className="space-y-4">
      {/* Carrier */}
      <div className="space-y-1.5">
        <Label htmlFor="carrier">Carrier / Logistics Provider</Label>
        <select
          id="carrier"
          value={form.carrier}
          onChange={e => setForm(f => ({ ...f, carrier: e.target.value }))}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Select carrier…</option>
          {CARRIERS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {/* From → To */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="from_city">From (Origin)</Label>
          <select
            id="from_city"
            value={form.from_city}
            onChange={e => setForm(f => ({ ...f, from_city: e.target.value }))}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select city…</option>
            {INDIAN_CITIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="to_city">To (Destination)</Label>
          <select
            id="to_city"
            value={form.to_city}
            onChange={e => setForm(f => ({ ...f, to_city: e.target.value }))}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select city…</option>
            {INDIAN_CITIES.filter(c => c !== form.from_city).map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* Amount + Currency */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="amount">Invoice Amount</Label>
          <Input
            id="amount"
            type="number"
            placeholder="e.g. 12500"
            value={form.amount}
            onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="currency">Currency</Label>
          <select
            id="currency"
            value={form.currency}
            onChange={e => setForm(f => ({ ...f, currency: e.target.value }))}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* Route preview */}
      {form.from_city && form.to_city && (
        <div className="rounded-md bg-secondary/50 px-3 py-2 text-xs text-muted-foreground">
          Route: <span className="font-medium text-foreground">{form.from_city} → {form.to_city}</span>
        </div>
      )}

      {/* Info */}
      <div className="rounded-lg bg-blue-50 border border-blue-100 px-4 py-3 flex gap-2.5">
        <Info className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-blue-700 leading-relaxed">
          Zoiko validates this invoice against your contract rates, detects the overcharge, scores it with AI confidence, and opens a dispute case automatically.
        </p>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); if (canSubmit) m.mutate(); }}>
        <Button
          type="submit"
          disabled={m.isPending || !canSubmit}
          className="w-full gap-2"
          size="lg"
        >
          {m.isPending ? (
            <><div className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> Submitting…</>
          ) : (
            <><ArrowRight className="h-4 w-4" /> Submit for Audit</>
          )}
        </Button>
        {m.isError && (
          <p className="text-sm text-destructive text-center mt-2">
            Submission failed — make sure the backend is running on port 8000.
          </p>
        )}
      </form>
    </div>
  );

  return (
    <div className="max-w-lg mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zoiko-navy">Submit Invoice for Audit</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload a carrier invoice (PDF/image) or enter the details manually.
        </p>
      </div>

      {/* Mode chooser */}
      {mode === "choose" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* Upload card */}
            <button
              onClick={() => setMode("upload")}
              className="group rounded-xl border-2 border-dashed border-border hover:border-zoiko-blue hover:bg-blue-50/30 transition-all p-6 text-center flex flex-col items-center gap-3 cursor-pointer"
            >
              <div className="h-12 w-12 rounded-full bg-zoiko-blue/10 flex items-center justify-center group-hover:bg-zoiko-blue/20 transition-colors">
                <UploadCloud className="h-6 w-6 text-zoiko-blue" />
              </div>
              <div>
                <p className="font-semibold text-sm">Upload Invoice</p>
                <p className="text-xs text-muted-foreground mt-1">PDF, PNG or JPG</p>
              </div>
            </button>

            {/* Manual card */}
            <button
              onClick={() => setMode("manual")}
              className="group rounded-xl border-2 border-border hover:border-zoiko-navy hover:bg-secondary/40 transition-all p-6 text-center flex flex-col items-center gap-3 cursor-pointer"
            >
              <div className="h-12 w-12 rounded-full bg-zoiko-navy/10 flex items-center justify-center group-hover:bg-zoiko-navy/20 transition-colors">
                <Pencil className="h-6 w-6 text-zoiko-navy" />
              </div>
              <div>
                <p className="font-semibold text-sm">Enter Manually</p>
                <p className="text-xs text-muted-foreground mt-1">Fill invoice details</p>
              </div>
            </button>
          </div>

          {/* Demo tip */}
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 flex gap-2.5">
            <Lightbulb className="h-4 w-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="text-xs text-amber-800 space-y-1">
              <p className="font-semibold">Demo tip</p>
              <p>Name your PDF <code className="bg-amber-100 px-1 rounded">bluedart_invoice.pdf</code> for automatic field extraction. Otherwise enter details manually.</p>
            </div>
          </div>
        </div>
      )}

      {/* Upload drop zone */}
      {mode === "upload" && !file && (
        <Card>
          <CardContent className="pt-6 space-y-3">
            <div
              onClick={() => inputRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              className={cn(
                "flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed px-6 py-12 cursor-pointer transition-colors",
                dragOver ? "border-zoiko-blue bg-blue-50/40" : "border-border hover:border-zoiko-blue hover:bg-secondary/40"
              )}
            >
              <UploadCloud className="h-10 w-10 text-muted-foreground" />
              <div className="text-center">
                <p className="text-sm font-medium">Drop invoice here, or click to browse</p>
                <p className="text-xs text-muted-foreground mt-1">PDF or image (PNG, JPG) — max 10 MB</p>
              </div>
              <input ref={inputRef} type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden" onChange={handleFileChange} />
            </div>
            <div className="rounded-md bg-amber-50 border border-amber-100 px-3 py-2 text-xs text-amber-700">
              <strong>Auto-parse:</strong> Name your file <code>bluedart_invoice.pdf</code> to get fields filled automatically.
            </div>
            <button onClick={() => setMode("choose")} className="text-xs text-muted-foreground hover:text-foreground w-full text-center">
              ← Back
            </button>
          </CardContent>
        </Card>
      )}

      {/* After file selected */}
      {mode === "upload" && file && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 rounded-lg border px-4 py-3 bg-white shadow-sm">
            <FileText className="h-5 w-5 text-zoiko-blue flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{file.name}</p>
              <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
            {parseState === "parsing" && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <div className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
                Parsing…
              </div>
            )}
            {parseState === "done" && !USE_MOCK && form.carrier && (
              <span className={cn(
                "text-[10px] font-bold px-2 py-0.5 rounded-full",
                parsedBy === "groq_ai"
                  ? "bg-purple-100 text-purple-700"
                  : "bg-slate-100 text-slate-600"
              )}>
                {parsedBy === "groq_ai" ? "AI" : "regex"}
              </span>
            )}
            {parseState === "error" && <span className="text-xs text-amber-600">Could not extract data — fill the fields below</span>}
            <button onClick={clearFile} className="text-muted-foreground hover:text-foreground ml-1">
              <X className="h-4 w-4" />
            </button>
          </div>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {parseState === "done" && form.carrier ? "Parsed Invoice Details — Review & Submit" : "Enter Invoice Details"}
              </CardTitle>
            </CardHeader>
            <CardContent>{formFields}</CardContent>
          </Card>
        </div>
      )}

      {/* Manual entry */}
      {mode === "manual" && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Enter Invoice Details</CardTitle>
              <button onClick={() => setMode("choose")} className="text-xs text-muted-foreground hover:text-foreground">
                ← Back
              </button>
            </div>
          </CardHeader>
          <CardContent>{formFields}</CardContent>
        </Card>
      )}
    </div>
  );
}

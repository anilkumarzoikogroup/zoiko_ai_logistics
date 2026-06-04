import { useState, useRef, useCallback, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useToast } from "@/hooks/useToast";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { UploadCloud, FileText, X, Pencil, ArrowRight, Info, Lightbulb, ChevronDown, ChevronUp, Eye, Maximize2, Globe, MapPin } from "lucide-react";
import { cn } from "@/utils/cn";
import { USE_MOCK, api } from "@/api/client";
import axios from "axios";

type Mode = "choose" | "upload" | "manual";
type ParseState = "idle" | "parsing" | "done" | "error";

const CARRIERS = [
  "BlueDart", "DTDC", "Delhivery", "Ekart", "FedEx India", "FedEx",
  "UPS India", "UPS", "V Express", "Gati", "DHL", "Aramex",
  "Maersk", "MSC", "CMA CGM", "Other",
];
const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD", "JPY", "CNY", "SAR"];

const INDIAN_CITIES = [
  "Hyderabad", "Warangal", "Mumbai", "Delhi", "Bangalore", "Chennai",
  "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Surat",
  "Kochi", "Nagpur", "Vizag", "Gurgaon", "Noida", "Chandigarh",
  "Coimbatore", "Indore", "Bhopal", "Patna", "Vadodara", "Ludhiana",
  "Agra", "Nashik", "Thane", "Rajkot", "Amritsar", "Varanasi",
  "Bhubaneswar", "Guwahati", "Dehradun", "Mysore", "Mangalore",
  "Madurai", "Thiruvananthapuram", "Tirupati",
];

const INTERNATIONAL_CITIES = [
  "Dubai", "Abu Dhabi", "Singapore", "Hong Kong", "Kuala Lumpur",
  "Bangkok", "Tokyo", "Seoul", "Shanghai", "Beijing", "Sydney",
  "Melbourne", "London", "Paris", "Frankfurt", "Amsterdam",
  "New York", "Los Angeles", "Chicago", "Toronto", "Johannesburg",
  "Cairo", "Nairobi", "Istanbul", "Riyadh", "Doha", "Kuwait City",
];

const ALL_CITIES = [...INDIAN_CITIES, ...INTERNATIONAL_CITIES];

interface FormState {
  carrier: string;
  from_city: string;
  to_city: string;
  amount: string;
  currency: string;
  email: string;
}

interface ParseResult {
  carrier: string;
  route: string;
  origin: string;
  destination: string;
  amount: number;
  currency: string;
  route_type: "national" | "international" | "unknown";
  email?: string;
  parsed_by?: string;
}

async function realParseInvoice(file: File): Promise<ParseResult> {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post("/ingestion/parse-invoice", fd);
  return data;
}

function CityCombobox({
  id, value, onChange, placeholder, suggestions,
}: {
  id: string; value: string; onChange: (v: string) => void;
  placeholder: string; suggestions: string[];
}) {
  return (
    <>
      <input
        id={id}
        list={`${id}-list`}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <datalist id={`${id}-list`}>
        {suggestions.map(c => <option key={c} value={c} />)}
      </datalist>
    </>
  );
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
  const [form, setForm]             = useState<FormState>({ carrier: "", from_city: "", to_city: "", amount: "", currency: "INR", email: "" });
  const [file, setFile]             = useState<File | null>(null);
  const [parseState, setParseState] = useState<ParseState>("idle");
  const [parsedBy,  setParsedBy]    = useState<string>("");
  const [routeType, setRouteType]   = useState<"national" | "international" | "unknown" | "">("");
  const [dragOver, setDragOver]     = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);
  // Guard against double-submission: locked after first mutate() call, released on error
  const submitting = useRef(false);

  useEffect(() => {
    if (!file) { setPreviewUrl(null); return; }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

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
      // Navigate to the case detail page; use replace so Back doesn't return to this form
      nav(`/cases/${c.id}`, { replace: true });
    },
    onError: (err: unknown) => {
      submitting.current = false; // allow retry after failure
      if (axios.isAxiosError(err)) {
        if (!err.response) {
          toast.error("Request timed out", "The pipeline takes ~20s. Check the backend is running on port 8000, then try again.");
        } else if (err.response.status === 401) {
          toast.error("Session expired", "You have been logged out. Please sign in again.");
        } else if (err.response.status === 500 && !err.response.data?.detail) {
          toast.error("Backend unreachable", "The server returned an error. Check the backend is running on port 8000 and try again.");
        } else {
          const detail = err.response.data?.detail || "Submission failed. Try again.";
          toast.error("Submission failed", typeof detail === "string" ? detail : JSON.stringify(detail));
        }
      } else {
        // Non-Axios errors: typically a JSON parse failure when proxy returns HTML on backend crash
        toast.error("Backend unreachable", "Lost connection to the server mid-request. Restart the backend on port 8000 and try again.");
      }
    },
  });

  const processFile = useCallback(async (f: File) => {
    setFile(f);
    setMode("upload");
    setPreviewOpen(true);
    if (USE_MOCK) {
      setParseState("done");
      return;
    }
    // Client-side carrier hint from filename (e.g. "DHL_Invoice.pdf" → "DHL")
    // This pre-fills the form even if the backend parse fails.
    const FNAME_CARRIERS: Record<string, string> = {
      bluedart: "BlueDart", blue_dart: "BlueDart", delhivery: "Delhivery",
      fedex: "FedEx", dtdc: "DTDC", ekart: "Ekart", gati: "Gati",
      ups: "UPS", dhl: "DHL", aramex: "Aramex", maersk: "Maersk",
      msc: "MSC", vexpress: "V Express",
    };
    const fnameLower = f.name.toLowerCase();
    const carrierFromName = Object.entries(FNAME_CARRIERS).find(([k]) => fnameLower.includes(k))?.[1] ?? "";

    setParseState("parsing");
    try {
      const parsed = await realParseInvoice(f);
      const from_city = parsed.origin || splitRoute(parsed.route).from_city;
      const to_city   = parsed.destination || splitRoute(parsed.route).to_city;

      const resolvedCarrier = parsed.carrier && CARRIERS.includes(parsed.carrier)
        ? parsed.carrier
        : parsed.carrier || carrierFromName || "Other";

      const resolvedCurrency = parsed.currency && CURRENCIES.includes(parsed.currency)
        ? parsed.currency
        : parsed.currency || "INR";

      setForm({
        carrier:   resolvedCarrier,
        from_city: from_city || "",
        to_city:   to_city   || "",
        amount:    parsed.amount > 0 ? String(parsed.amount) : "",
        currency:  resolvedCurrency,
        email:     parsed.email || "",
      });
      setParsedBy(parsed.parsed_by || "regex");
      setRouteType(parsed.route_type || "unknown");
      const gotData = parsed.carrier || parsed.amount > 0 || from_city;
      setParseState(gotData ? "done" : "error");
    } catch (err) {
      // Pre-fill carrier from filename so the user doesn't start from scratch
      if (carrierFromName) {
        setForm(prev => ({ ...prev, carrier: carrierFromName }));
      }
      // Tell the user WHY it failed — network error vs. no data extracted
      const isNetworkErr = axios.isAxiosError(err) ? !err.response : true;
      if (isNetworkErr) {
        toast.error("Backend unreachable", "Start the backend (run: python start_phase2.py) then re-upload the file.");
      }
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
    setPreviewOpen(true);
    setRouteType("");
    setForm({ carrier: "", from_city: "", to_city: "", amount: "", currency: "INR", email: "" });
    if (inputRef.current) inputRef.current.value = "";
  }

  const canSubmit = form.carrier && form.from_city && form.to_city && Number(form.amount) > 0;

  const isParsingNow = parseState === "parsing";

  const formFields = (
    <div className="space-y-4">
      {/* Carrier */}
      <div className="space-y-1.5">
        <Label htmlFor="carrier">Carrier / Logistics Provider</Label>
        {isParsingNow ? (
          <div className="h-9 w-full rounded-md bg-muted animate-pulse" />
        ) : (
          <CityCombobox
            id="carrier"
            value={form.carrier}
            onChange={v => setForm(f => ({ ...f, carrier: v }))}
            placeholder="e.g. BlueDart, DHL, Maersk…"
            suggestions={CARRIERS}
          />
        )}
      </div>

      {/* From → To */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label>Origin &amp; Destination</Label>
          {routeType && routeType !== "unknown" && (
            <span className={cn(
              "inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full",
              routeType === "international"
                ? "bg-blue-100 text-blue-700"
                : "bg-green-100 text-green-700"
            )}>
              {routeType === "international"
                ? <><Globe className="h-3 w-3" /> International</>
                : <><MapPin className="h-3 w-3" /> National</>
              }
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <span className="text-[11px] text-muted-foreground">From (Origin)</span>
            {isParsingNow ? (
              <div className="h-9 w-full rounded-md bg-muted animate-pulse" />
            ) : (
              <CityCombobox
                id="from_city"
                value={form.from_city}
                onChange={v => setForm(f => ({ ...f, from_city: v }))}
                placeholder="e.g. Mumbai, Dubai, New York"
                suggestions={ALL_CITIES.filter(c => c !== form.to_city)}
              />
            )}
          </div>
          <div className="space-y-1">
            <span className="text-[11px] text-muted-foreground">To (Destination)</span>
            {isParsingNow ? (
              <div className="h-9 w-full rounded-md bg-muted animate-pulse" />
            ) : (
              <CityCombobox
                id="to_city"
                value={form.to_city}
                onChange={v => setForm(f => ({ ...f, to_city: v }))}
                placeholder="e.g. Delhi, London, Singapore"
                suggestions={ALL_CITIES.filter(c => c !== form.from_city)}
              />
            )}
          </div>
        </div>
      </div>

      {/* Amount + Currency */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="amount">Invoice Amount</Label>
          {isParsingNow ? (
            <div className="h-9 w-full rounded-md bg-muted animate-pulse" />
          ) : (
            <Input
              id="amount"
              type="number"
              placeholder="e.g. 12500"
              value={form.amount}
              onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
            />
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="currency">Currency</Label>
          <CityCombobox
            id="currency"
            value={form.currency}
            onChange={v => setForm(f => ({ ...f, currency: v.toUpperCase() }))}
            placeholder="INR, USD, EUR…"
            suggestions={CURRENCIES}
          />
        </div>
      </div>

      {/* Email */}
      <div className="space-y-1.5">
        <Label htmlFor="email">Contact / Billing Email</Label>
        {isParsingNow ? (
          <div className="h-9 w-full rounded-md bg-muted animate-pulse" />
        ) : (
          <Input
            id="email"
            type="email"
            placeholder="e.g. billing@dhl.com"
            value={form.email}
            onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
          />
        )}
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

      <form onSubmit={(e) => {
        e.preventDefault();
        if (!canSubmit || submitting.current || m.isPending) return;
        submitting.current = true;
        m.mutate();
      }}>
        <Button
          type="submit"
          disabled={m.isPending || submitting.current || !canSubmit}
          className="w-full gap-2"
          size="lg"
        >
          {m.isPending ? (
            <><div className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> Submitting… please wait</>
          ) : (
            <><ArrowRight className="h-4 w-4" /> Submit for Audit</>
          )}
        </Button>
        {m.isError && (
          <p className="text-sm text-destructive text-center mt-2">
            {axios.isAxiosError(m.error) && !m.error.response
              ? "Request timed out — pipeline takes ~20s. Check the backend is running and try again."
              : axios.isAxiosError(m.error) && m.error.response?.status === 401
              ? "Session expired — please log in again."
              : axios.isAxiosError(m.error) && m.error.response
              ? `Submission failed — ${(m.error.response.data as any)?.detail || "check the backend terminal for details."}`
              : "Backend unreachable — restart the backend on port 8000 and try again."}
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
                {file?.type?.startsWith("image/") ? "Reading image with AI…" : "Extracting from PDF…"}
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
            {parseState === "error" && <span className="text-xs text-amber-600">Could not extract — fill fields below or re-upload after starting backend</span>}
            <button onClick={clearFile} className="text-muted-foreground hover:text-foreground ml-1">
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* File preview */}
          {previewUrl && (
            <Card className="overflow-hidden border-zoiko-blue/20 shadow-sm">
              <div
                className="flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-zoiko-navy/5 to-zoiko-blue/5 border-b cursor-pointer select-none"
                onClick={() => setPreviewOpen(v => !v)}
              >
                <div className="flex items-center gap-2">
                  <Eye className="h-4 w-4 text-zoiko-blue" />
                  <span className="text-sm font-semibold text-zoiko-navy">Invoice Preview</span>
                  <span className="text-[10px] bg-zoiko-blue/10 text-zoiko-blue px-2 py-0.5 rounded-full font-medium uppercase tracking-wide">
                    {file?.type === "application/pdf" ? "PDF" : "Image"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href={previewUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={e => e.stopPropagation()}
                    className="text-muted-foreground hover:text-zoiko-blue transition-colors"
                    title="Open in new tab"
                  >
                    <Maximize2 className="h-3.5 w-3.5" />
                  </a>
                  {previewOpen
                    ? <ChevronUp className="h-4 w-4 text-muted-foreground" />
                    : <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  }
                </div>
              </div>

              {previewOpen && (
                <div className="bg-slate-50">
                  {file?.type === "application/pdf" ? (
                    <iframe
                      src={previewUrl}
                      title="Invoice PDF Preview"
                      className="w-full rounded-b-lg"
                      style={{ height: "480px", border: "none" }}
                    />
                  ) : (
                    <div className="flex items-center justify-center p-4">
                      <img
                        src={previewUrl}
                        alt="Invoice preview"
                        className="max-h-96 max-w-full rounded-lg shadow-md object-contain ring-1 ring-black/5"
                      />
                    </div>
                  )}
                </div>
              )}
            </Card>
          )}

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

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { cn } from "@/utils/cn";
import { FileText, Download, Shield, CheckCircle2, Hash, Calendar, BarChart2, Lock } from "lucide-react";

type ReportType = "full_audit" | "carrier_summary" | "crypto_proof" | "sod_log" | "acr_bundle";
type OutputFormat = "pdf" | "json" | "csv" | "bundle";

const REPORT_TYPES: { id: ReportType; label: string; desc: string }[] = [
  { id: "full_audit",      label: "Full Audit Trail",      desc: "All cases, decisions, hashes, signatures" },
  { id: "carrier_summary", label: "Carrier Summary",       desc: "Overcharge rates by carrier and route" },
  { id: "crypto_proof",    label: "Crypto Proof Bundle",   desc: "Merkle roots, Ed25519 sigs, ACR hashes" },
  { id: "sod_log",         label: "SoD Compliance Log",    desc: "Separation-of-duty enforcement records" },
  { id: "acr_bundle",      label: "ACR Export",            desc: "Action Certification Records (WORM-locked)" },
];

const INCLUDE_OPTIONS = [
  { id: "cases",       label: "Case events & state transitions" },
  { id: "hashes",      label: "SHA-256 hash chain" },
  { id: "signatures",  label: "Ed25519 signatures" },
  { id: "merkle",      label: "Merkle root proofs" },
  { id: "tokens",      label: "Governance tokens (issued/consumed)" },
  { id: "decisions",   label: "Manager decisions with SoD check" },
];

const MOCK_PREVIEW = {
  reportId:  "RPT-20250120-0047",
  generated: "2025-01-20T11:42:00Z",
  merkleRoot: "0x4a3f8e9c2b7d1f6a0e5c8b3a7d2f9e4c",
  signature:  "0xed25519::a3f7c2e9b8d4f1a6…[Ed25519 64-byte sig truncated for display]",
  keyId:     "amazon-india-signing-2025-01",
  cases:     47,
  approved:  28,
  recovered: "₹3,84,000",
  entries:   312,
};

export default function CryptoAudit() {
  const [reportType, setReportType]     = useState<ReportType>("full_audit");
  const [fromDate, setFromDate]         = useState("2025-01-01");
  const [toDate, setToDate]             = useState("2025-01-20");
  const [includes, setIncludes]         = useState<Set<string>>(new Set(["cases", "hashes", "signatures", "merkle"]));
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("pdf");
  const [generated, setGenerated]       = useState(false);
  const [generating, setGenerating]     = useState(false);

  function toggleInclude(id: string) {
    setIncludes(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function handleGenerate() {
    setGenerating(true);
    setTimeout(() => { setGenerating(false); setGenerated(true); }, 1800);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-zoiko-navy">Audit Report Builder</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Generate cryptographically signed audit reports. Every report is sealed with an Ed25519 signature and Merkle root proof.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

        {/* Left: Config Panel */}
        <div className="lg:col-span-2 space-y-4">

          {/* Report Type */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2"><FileText className="h-4 w-4" /> Report Type</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {REPORT_TYPES.map(rt => (
                <label key={rt.id} className={cn(
                  "flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors",
                  reportType === rt.id ? "border-zoiko-navy bg-zoiko-navy/5" : "border-border hover:bg-secondary/40"
                )}>
                  <input type="radio" name="reportType" value={rt.id} checked={reportType === rt.id}
                    onChange={() => setReportType(rt.id)} className="mt-0.5 accent-zoiko-navy flex-shrink-0" />
                  <div>
                    <p className={cn("text-sm font-medium", reportType === rt.id && "text-zoiko-navy")}>{rt.label}</p>
                    <p className="text-xs text-muted-foreground">{rt.desc}</p>
                  </div>
                </label>
              ))}
            </CardContent>
          </Card>

          {/* Date Range */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2"><Calendar className="h-4 w-4" /> Date Range</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium block mb-1">From</label>
                <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium block mb-1">To</label>
                <input type="date" value={toDate} onChange={e => setToDate(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
            </CardContent>
          </Card>

          {/* Include Options */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2"><BarChart2 className="h-4 w-4" /> Include</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {INCLUDE_OPTIONS.map(opt => (
                <label key={opt.id} className="flex items-center gap-2.5 cursor-pointer group">
                  <input type="checkbox" checked={includes.has(opt.id)} onChange={() => toggleInclude(opt.id)}
                    className="accent-zoiko-navy" />
                  <span className="text-sm text-foreground/80 group-hover:text-foreground">{opt.label}</span>
                </label>
              ))}
            </CardContent>
          </Card>

          {/* Output Format */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Output Format</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-4 gap-2">
                {(["pdf", "json", "csv", "bundle"] as OutputFormat[]).map(f => (
                  <button key={f} onClick={() => setOutputFormat(f)}
                    className={cn(
                      "py-2 rounded-lg border text-xs font-semibold uppercase transition-colors",
                      outputFormat === f ? "border-zoiko-navy bg-zoiko-navy text-white" : "border-border text-muted-foreground hover:border-zoiko-navy hover:text-zoiko-navy"
                    )}>
                    {f}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          <Button onClick={handleGenerate} disabled={generating} className="w-full gap-2" size="lg">
            {generating ? (
              <><div className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> Generating & Signing…</>
            ) : (
              <><Shield className="h-4 w-4" /> Generate &amp; Sign Report</>
            )}
          </Button>
        </div>

        {/* Right: Preview Panel */}
        <div className="lg:col-span-3">
          <Card className="h-full">
            <CardHeader className="pb-3 border-b">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  {generated ? "Signed Report Preview" : "Report Preview"}
                </CardTitle>
                {generated && (
                  <button className="flex items-center gap-1.5 text-xs text-zoiko-blue hover:underline font-medium">
                    <Download className="h-3.5 w-3.5" /> Download {outputFormat.toUpperCase()}
                  </button>
                )}
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              {!generated ? (
                <div className="flex flex-col items-center justify-center h-80 text-center text-muted-foreground space-y-3">
                  <div className="h-16 w-16 rounded-full bg-secondary flex items-center justify-center">
                    <FileText className="h-8 w-8 text-muted-foreground/50" />
                  </div>
                  <div>
                    <p className="font-medium">Configure and generate a report</p>
                    <p className="text-sm mt-1">Select report type, date range, and included data on the left, then click Generate.</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4 font-mono text-xs">

                  {/* Report header */}
                  <div className="rounded-lg bg-zoiko-navy/5 border border-zoiko-navy/20 p-4 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-zoiko-navy text-sm">ZOIKO AI AUDIT REPORT</span>
                      <span className="text-[10px] text-muted-foreground">{MOCK_PREVIEW.reportId}</span>
                    </div>
                    <div className="text-muted-foreground text-[10px]">Generated: {MOCK_PREVIEW.generated}</div>
                    <div className="text-muted-foreground text-[10px]">Period: {fromDate} → {toDate}</div>
                    <div className="text-muted-foreground text-[10px]">Tenant: amazon-india</div>
                  </div>

                  {/* Stats */}
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      ["Total Cases", MOCK_PREVIEW.cases],
                      ["Approved",    MOCK_PREVIEW.approved],
                      ["Recovered",   MOCK_PREVIEW.recovered],
                      ["Log Entries", MOCK_PREVIEW.entries],
                    ].map(([k, v]) => (
                      <div key={String(k)} className="rounded border bg-secondary/40 px-3 py-2">
                        <p className="text-[10px] text-muted-foreground uppercase">{k}</p>
                        <p className="font-bold text-foreground">{v}</p>
                      </div>
                    ))}
                  </div>

                  {/* Crypto proofs */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground uppercase tracking-wider font-semibold">
                      <Hash className="h-3 w-3" /> Cryptographic Proofs
                    </div>
                    <div className="rounded border bg-secondary/30 p-3 space-y-2 text-[10px]">
                      <div>
                        <span className="text-muted-foreground">Merkle Root:</span>
                        <code className="ml-2 text-purple-700 break-all">{MOCK_PREVIEW.merkleRoot}</code>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Algorithm:</span>
                        <code className="ml-2">Ed25519 · SHA-256 domain-tagged</code>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Key ID:</span>
                        <code className="ml-2 text-zoiko-blue">{MOCK_PREVIEW.keyId}</code>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Signature:</span>
                        <code className="ml-2 text-emerald-700 break-all">{MOCK_PREVIEW.signature}</code>
                      </div>
                    </div>
                  </div>

                  {/* Verified badge */}
                  <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 flex items-center gap-3">
                    <CheckCircle2 className="h-5 w-5 text-emerald-600 flex-shrink-0" />
                    <div>
                      <p className="font-semibold text-emerald-800 text-xs">Report integrity verified</p>
                      <p className="text-[10px] text-emerald-600">Ed25519 signature valid · Merkle root matches all {MOCK_PREVIEW.entries} log entries</p>
                    </div>
                    <Lock className="h-4 w-4 text-emerald-600 ml-auto flex-shrink-0" />
                  </div>

                  <p className="text-[10px] text-muted-foreground text-center">
                    This report is sealed. Any modification invalidates the signature.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

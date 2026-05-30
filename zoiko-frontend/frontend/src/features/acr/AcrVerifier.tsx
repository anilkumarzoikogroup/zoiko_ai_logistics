/**
 * ACR Verifier — offline client-side verification.
 *
 * Upload acr-verify-<case_id>.zip → browser extracts acr.json →
 * runs JCS + Merkle root computation + Ed25519 sig check via Web Crypto.
 * Zero API calls — works with no backend running.
 */
import { useState, useRef, useCallback } from "react";
import JSZip from "jszip";
import { verifyACRBundle, parseACRBundle } from "@/utils/acrVerifier";
import { cn } from "@/utils/cn";
import {
  UploadCloud, CheckCircle2, XCircle, AlertTriangle,
  Shield, Hash, FileText, ChevronDown, ChevronUp,
} from "lucide-react";

type Status = "idle" | "loading" | "pass" | "fail" | "error";

interface VerifyState {
  status:           Status;
  acr_id?:          string;
  case_id?:         string;
  merkle_root?:     string;
  computed_root?:   string;
  artifact_count?:  number;
  errors:           string[];
  warnings:         string[];
  raw_text?:        string;
}

const INIT: VerifyState = { status: "idle", errors: [], warnings: [] };

export default function AcrVerifier() {
  const [state, setState] = useState<VerifyState>(INIT);
  const [dragOver, setDragOver] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const processFile = useCallback(async (file: File) => {
    setState({ ...INIT, status: "loading" });
    try {
      // ── Extract ZIP ────────────────────────────────────────────────────
      const arrayBuf = await file.arrayBuffer();
      const zip      = await JSZip.loadAsync(arrayBuf);

      // Look for acr.json at root or inside a subdirectory
      let acrEntry = zip.file("acr.json");
      if (!acrEntry) {
        const found = Object.keys(zip.files).find(name => name.endsWith("acr.json"));
        if (found) acrEntry = zip.file(found);
      }

      if (!acrEntry) {
        setState({
          ...INIT,
          status: "error",
          errors: ["acr.json not found in ZIP. Make sure you uploaded the correct ACR verify package."],
        });
        return;
      }

      const acrText = await acrEntry.async("string");

      // ── Inject public keys from public_keys/ folder if present ────────
      let acrObj = JSON.parse(acrText);
      const pubKeyFiles = Object.keys(zip.files).filter(n => n.includes("public_keys/") && !zip.files[n].dir);
      if (pubKeyFiles.length > 0 && !acrObj.public_keys) {
        acrObj.public_keys = {};
        for (const pkFile of pubKeyFiles) {
          const kid = pkFile.split("/").pop()?.replace(".pub", "") ?? pkFile;
          const pkContent = await zip.file(pkFile)!.async("string");
          acrObj.public_keys[kid] = pkContent.trim();
        }
      }

      // ── Parse + verify ─────────────────────────────────────────────────
      const bundle = parseACRBundle(acrObj);
      const result = await verifyACRBundle(bundle);

      setState({
        status:          result.passed ? "pass" : "fail",
        acr_id:          bundle.acr_id,
        case_id:         bundle.case_id,
        merkle_root:     bundle.merkle_root,
        computed_root:   result.computed_root,
        artifact_count:  result.artifact_count,
        errors:          result.errors,
        warnings:        result.warnings,
        raw_text:        acrText,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setState({
        ...INIT,
        status: "error",
        errors: [`Verification failed: ${msg}`],
      });
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) processFile(f);
  }, [processFile]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) processFile(f);
  };

  const reset = () => {
    setState(INIT);
    setShowDetail(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-zoiko-navy">ACR Offline Verifier</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Verify an Action Certification Record offline — no backend required.
          Upload the <code className="bg-slate-100 rounded px-1">acr-verify-*.zip</code> downloaded from a case.
        </p>
      </div>

      {/* How it works */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 space-y-1">
        <p className="text-xs font-bold text-blue-800 flex items-center gap-1.5">
          <Shield className="h-3.5 w-3.5" /> What this verifier checks
        </p>
        <ul className="text-xs text-blue-700 space-y-0.5 ml-5 list-disc">
          <li>Recomputes the Merkle root over all 8 artifact SHA-256 hashes</li>
          <li>Compares against the claimed merkle_root in the ACR</li>
          <li>Attempts Ed25519 signature verification via Web Crypto API</li>
          <li>Any tampered artifact changes the Merkle root → FAIL</li>
        </ul>
      </div>

      {/* Drop zone */}
      {state.status === "idle" && (
        <div
          onClick={() => inputRef.current?.click()}
          onDrop={handleDrop}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          className={cn(
            "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-16 cursor-pointer transition-colors",
            dragOver
              ? "border-zoiko-blue bg-blue-50/60"
              : "border-slate-300 hover:border-zoiko-blue hover:bg-slate-50"
          )}
        >
          <UploadCloud className="h-12 w-12 text-slate-400" />
          <div className="text-center">
            <p className="text-sm font-semibold text-slate-700">Drop ACR verify package here</p>
            <p className="text-xs text-muted-foreground mt-1">
              acr-verify-*.zip — or click to browse
            </p>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={handleChange}
          />
        </div>
      )}

      {/* Loading */}
      {state.status === "loading" && (
        <div className="flex flex-col items-center gap-3 py-16">
          <div className="h-10 w-10 rounded-full border-4 border-zoiko-blue border-t-transparent animate-spin" />
          <p className="text-sm text-muted-foreground">Verifying…</p>
        </div>
      )}

      {/* Result */}
      {(state.status === "pass" || state.status === "fail" || state.status === "error") && (
        <div className="space-y-4">

          {/* Pass / Fail banner */}
          <div className={cn(
            "rounded-xl border-2 px-6 py-5 flex items-start gap-4",
            state.status === "pass"
              ? "border-emerald-400 bg-emerald-50"
              : "border-red-400 bg-red-50"
          )}>
            {state.status === "pass"
              ? <CheckCircle2 className="h-8 w-8 text-emerald-600 flex-shrink-0 mt-0.5" />
              : <XCircle className="h-8 w-8 text-red-600 flex-shrink-0 mt-0.5" />
            }
            <div>
              <p className={cn("text-lg font-bold", state.status === "pass" ? "text-emerald-700" : "text-red-700")}>
                {state.status === "pass" ? "VERIFICATION PASSED" : "VERIFICATION FAILED"}
              </p>
              <p className={cn("text-sm mt-0.5", state.status === "pass" ? "text-emerald-600" : "text-red-600")}>
                {state.status === "pass"
                  ? "Merkle root matches — ACR has not been tampered with."
                  : "ACR may have been tampered with. Do not rely on this record."}
              </p>
            </div>
          </div>

          {/* Metadata */}
          {state.acr_id && (
            <div className="rounded-xl border border-slate-200 bg-white divide-y divide-slate-100">
              {[
                { icon: FileText, label: "ACR ID",        value: state.acr_id },
                { icon: Hash,     label: "Case ID",        value: state.case_id },
                { icon: Hash,     label: "Merkle Root (claimed)",  value: state.merkle_root?.slice(0, 32) + "…" },
                { icon: Hash,     label: "Merkle Root (computed)", value: state.computed_root?.slice(0, 32) + "…" },
                { icon: Shield,   label: "Artifacts verified", value: `${state.artifact_count} of 8` },
              ].map(({ icon: Icon, label, value }) => (
                <div key={label} className="flex items-center gap-3 px-4 py-2.5">
                  <Icon className="h-4 w-4 text-slate-400 flex-shrink-0" />
                  <span className="text-xs text-slate-500 w-44 flex-shrink-0">{label}</span>
                  <span className="text-xs font-mono text-slate-700 truncate">{value}</span>
                </div>
              ))}
            </div>
          )}

          {/* Warnings */}
          {state.warnings.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 space-y-1">
              {state.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-amber-800">
                  <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5 text-amber-600" />
                  {w}
                </div>
              ))}
            </div>
          )}

          {/* Errors */}
          {state.errors.length > 0 && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 space-y-1">
              {state.errors.map((e, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-red-800">
                  <XCircle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5 text-red-600" />
                  {e}
                </div>
              ))}
            </div>
          )}

          {/* Raw JSON toggle */}
          {state.raw_text && (
            <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
              <button
                onClick={() => setShowDetail(v => !v)}
                className="w-full flex items-center justify-between px-4 py-3 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
              >
                View raw acr.json
                {showDetail ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>
              {showDetail && (
                <pre className="text-[10px] font-mono text-slate-700 bg-slate-50 p-4 overflow-auto max-h-64 border-t border-slate-200">
                  {JSON.stringify(JSON.parse(state.raw_text), null, 2)}
                </pre>
              )}
            </div>
          )}

          {/* Verify another */}
          <button
            onClick={reset}
            className="w-full py-2.5 rounded-xl border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 transition-colors font-medium"
          >
            Verify another package
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * GlobalSearch — live search across cases, carriers and invoices.
 * Shows a dropdown of results. Keyboard navigable. Theme-aware.
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { formatCurrency } from "@/utils/cn";
import { Search, FileText, Truck, X, ArrowRight } from "lucide-react";
import type { Case } from "@/types";

const STATE_LABEL: Record<string, string> = {
  NEW: "Submitted", EVIDENCE_PENDING: "In Review", FINDING_GENERATED: "AI Analyzed",
  APPROVAL_PENDING: "Pending Approval", EXECUTION_READY: "Approved",
  DISPATCHED: "Recovery Initiated", OUTCOME_RECORDED: "Recovered",
  CLOSED: "Closed", ABORTED: "Rejected",
};
const STATE_COLOR: Record<string, string> = {
  FINDING_GENERATED: "#7c3aed", APPROVAL_PENDING: "#d97706",
  EXECUTION_READY: "#2563eb",   DISPATCHED: "#059669",
  OUTCOME_RECORDED: "#059669",  CLOSED: "#059669",
  ABORTED: "#dc2626",
};

interface Props { isDark: boolean; }

export default function GlobalSearch({ isDark }: Props) {
  const nav = useNavigate();
  const [query, setQuery]         = useState("");
  const [open, setOpen]           = useState(false);
  const [cursor, setCursor]       = useState(-1);
  const inputRef                  = useRef<HTMLInputElement>(null);
  const containerRef              = useRef<HTMLDivElement>(null);

  const { data: cases = [] } = useQuery({
    queryKey: ["cases"],
    queryFn: () => zoikoApi.listCases(),
    staleTime: 30_000,
  });

  const q = query.trim().toLowerCase();
  const results: Case[] = q.length < 2 ? [] : (cases as Case[]).filter(c =>
    c.id.toLowerCase().includes(q)       ||
    (c.carrier  || "").toLowerCase().includes(q) ||
    (c.shipment_ref || "").toLowerCase().includes(q) ||
    String(c.amount || "").includes(q)   ||
    (STATE_LABEL[c.state] || "").toLowerCase().includes(q)
  ).slice(0, 7);

  // Unique carriers from results (for header grouping)
  const topCarriers = q.length >= 2
    ? [...new Set((cases as Case[]).map(c => c.carrier).filter(Boolean))]
        .filter(car => car!.toLowerCase().includes(q)).slice(0, 3)
    : [];

  const totalHits = results.length + topCarriers.length;

  // Close when clicking outside
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false); setCursor(-1);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  // Keyboard navigation
  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown")  { e.preventDefault(); setCursor(c => Math.min(c + 1, totalHits - 1)); }
    if (e.key === "ArrowUp")    { e.preventDefault(); setCursor(c => Math.max(c - 1, -1)); }
    if (e.key === "Escape")     { setOpen(false); setQuery(""); setCursor(-1); inputRef.current?.blur(); }
    if (e.key === "Enter" && cursor >= 0) {
      if (cursor < results.length) navigate(results[cursor]);
      else {
        const car = topCarriers[cursor - results.length];
        if (car) { nav("/cases"); setOpen(false); setQuery(""); }
      }
    }
  }

  // Ctrl+K / ⌘K global shortcut
  useEffect(() => {
    function handle(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault(); inputRef.current?.focus(); setOpen(true);
      }
    }
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, []);

  function navigate(c: Case) {
    nav(`/cases/${c.id}`); setOpen(false); setQuery(""); setCursor(-1);
  }

  // Theme colours
  const bg     = isDark ? "#0d1424" : "#ffffff";
  const border = isDark ? "#1e293b" : "#e2e8f0";
  const text   = isDark ? "#e2e8f0" : "#1e293b";
  const muted  = isDark ? "#64748b" : "#94a3b8";
  const hover  = isDark ? "#0d1a2e" : "#f8fafc";
  const inputBg= isDark ? "#1e293b" : "#f8fafc";
  const inputTx= isDark ? "#e2e8f0" : "#374151";
  const hdrBg  = isDark ? "#0a0f1e" : "#f1f5f9";

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      {/* Input */}
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        <Search style={{ position: "absolute", left: 10, width: 14, height: 14, color: muted, pointerEvents: "none" }} />
        <input
          ref={inputRef}
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true); setCursor(-1); }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKey}
          placeholder="Search invoices, cases, carriers…"
          style={{
            paddingLeft: 32, paddingRight: query ? 28 : 40, paddingTop: 6, paddingBottom: 6,
            background: inputBg, border: `1px solid ${border}`, borderRadius: 8,
            fontSize: 13, color: inputTx, outline: "none", width: 260,
            transition: "width 0.2s, box-shadow 0.15s",
          }}
          onFocusCapture={e => {
            (e.target as HTMLInputElement).style.width = "320px";
            (e.target as HTMLInputElement).style.boxShadow = "0 0 0 2px rgba(59,130,246,0.25)";
          }}
          onBlurCapture={e => {
            (e.target as HTMLInputElement).style.width = "260px";
            (e.target as HTMLInputElement).style.boxShadow = "none";
          }}
        />
        {query ? (
          <button onClick={() => { setQuery(""); setOpen(false); setCursor(-1); }}
            style={{ position: "absolute", right: 8, background: "none", border: "none", cursor: "pointer", color: muted, display: "flex" }}>
            <X style={{ width: 13, height: 13 }} />
          </button>
        ) : (
          <span style={{ position: "absolute", right: 10, fontSize: 10, color: muted, fontFamily: "monospace", background: isDark ? "#1e293b" : "#e2e8f0", padding: "1px 5px", borderRadius: 4 }}>
            ⌘K
          </span>
        )}
      </div>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 9999,
          background: bg, border: `1px solid ${border}`, borderRadius: 10,
          boxShadow: isDark ? "0 8px 32px rgba(0,0,0,0.6)" : "0 8px 32px rgba(0,0,0,0.12)",
          width: 380, maxHeight: 440, overflowY: "auto",
        }}>
          {q.length < 2 ? (
            <div style={{ padding: "16px 16px", color: muted, fontSize: 12, textAlign: "center" }}>
              Type at least 2 characters to search…
            </div>
          ) : totalHits === 0 ? (
            <div style={{ padding: 20, textAlign: "center" }}>
              <Search style={{ width: 24, height: 24, color: muted, margin: "0 auto 8px" }} />
              <p style={{ fontSize: 13, color: text, margin: 0 }}>No results for "{query}"</p>
              <p style={{ fontSize: 11, color: muted, margin: "4px 0 0" }}>Try case ID, carrier name or status</p>
            </div>
          ) : (
            <>
              {/* Cases section */}
              {results.length > 0 && (
                <>
                  <div style={{ padding: "8px 14px 5px", fontSize: 10, fontWeight: 700, color: muted, textTransform: "uppercase", letterSpacing: "0.08em", background: hdrBg, borderBottom: `1px solid ${border}` }}>
                    Cases ({results.length})
                  </div>
                  {results.map((c, i) => (
                    <div
                      key={c.id}
                      onClick={() => navigate(c)}
                      style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
                        cursor: "pointer", borderBottom: `1px solid ${border}`,
                        background: cursor === i ? hover : "transparent",
                        transition: "background 0.1s",
                      }}
                      onMouseEnter={() => setCursor(i)}
                    >
                      <div style={{ width: 32, height: 32, borderRadius: 7, background: isDark ? "#1e293b" : "#f1f5f9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        <FileText style={{ width: 14, height: 14, color: "#3b82f6" }} />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                          <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3b82f6" }}>{c.id.slice(0, 8)}…</span>
                          <span style={{ fontSize: 10, fontWeight: 700, color: STATE_COLOR[c.state] || muted,
                            background: (STATE_COLOR[c.state] || muted) + "18", padding: "1px 6px", borderRadius: 99 }}>
                            {STATE_LABEL[c.state] || c.state}
                          </span>
                        </div>
                        <p style={{ fontSize: 12, color: text, margin: 0, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {c.carrier || "Unknown Carrier"}
                        </p>
                        <p style={{ fontSize: 11, color: muted, margin: 0 }}>{formatCurrency(c.amount)}</p>
                      </div>
                      <ArrowRight style={{ width: 13, height: 13, color: muted, flexShrink: 0 }} />
                    </div>
                  ))}
                </>
              )}

              {/* Carriers section */}
              {topCarriers.length > 0 && (
                <>
                  <div style={{ padding: "8px 14px 5px", fontSize: 10, fontWeight: 700, color: muted, textTransform: "uppercase", letterSpacing: "0.08em", background: hdrBg, borderBottom: `1px solid ${border}` }}>
                    Carriers
                  </div>
                  {topCarriers.map((car, i) => (
                    <div
                      key={car}
                      onClick={() => { nav("/cases"); setOpen(false); setQuery(""); }}
                      style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", cursor: "pointer",
                        background: cursor === results.length + i ? hover : "transparent",
                        transition: "background 0.1s",
                      }}
                      onMouseEnter={() => setCursor(results.length + i)}
                    >
                      <div style={{ width: 32, height: 32, borderRadius: 7, background: isDark ? "#1e293b" : "#f1f5f9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        <Truck style={{ width: 14, height: 14, color: "#10b981" }} />
                      </div>
                      <div style={{ flex: 1 }}>
                        <p style={{ fontSize: 13, fontWeight: 600, color: text, margin: 0 }}>{car}</p>
                        <p style={{ fontSize: 11, color: muted, margin: 0 }}>
                          {(cases as Case[]).filter(c => c.carrier === car).length} cases
                        </p>
                      </div>
                      <ArrowRight style={{ width: 13, height: 13, color: muted }} />
                    </div>
                  ))}
                </>
              )}

              {/* Footer hint */}
              <div style={{ padding: "8px 14px", fontSize: 10, color: muted, display: "flex", gap: 12, background: hdrBg, borderTop: `1px solid ${border}` }}>
                <span>↑↓ navigate</span><span>↵ open</span><span>Esc close</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

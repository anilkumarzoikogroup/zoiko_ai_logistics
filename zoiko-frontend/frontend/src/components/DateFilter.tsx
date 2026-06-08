/**
 * DateFilter — Month/year picker that sets a global date context
 * used to filter dashboard data. Stores selection in localStorage.
 */
import { useState, useRef, useEffect } from "react";
import { Calendar, ChevronDown, ChevronLeft, ChevronRight, X } from "lucide-react";

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

export interface DateRange {
  year:  number;
  month: number; // 1-12
  label: string;
}

/** Read stored filter or default to current month */
export function getStoredDateFilter(): DateRange {
  try {
    const raw = localStorage.getItem("zoiko-date-filter");
    if (raw) return JSON.parse(raw);
  } catch {}
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1, label: `${MONTHS[now.getMonth()]} ${now.getFullYear()}` };
}

export function setStoredDateFilter(d: DateRange) {
  localStorage.setItem("zoiko-date-filter", JSON.stringify(d));
}

/** Returns true if a case's opened_at falls in the given month/year */
export function caseInRange(openedAt: string, filter: DateRange): boolean {
  const d = new Date(openedAt);
  return d.getFullYear() === filter.year && (d.getMonth() + 1) === filter.month;
}

interface Props {
  isDark:    boolean;
  value:     DateRange;
  onChange:  (d: DateRange) => void;
}

export default function DateFilter({ isDark, value, onChange }: Props) {
  const [open, setOpen]     = useState(false);
  const [viewYear, setViewYear] = useState(value.year);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  function select(year: number, month: number) {
    const d: DateRange = { year, month, label: `${MONTHS[month - 1]} ${year}` };
    onChange(d);
    setStoredDateFilter(d);
    setOpen(false);
  }

  function clearFilter() {
    const now = new Date();
    select(now.getFullYear(), now.getMonth() + 1);
  }

  // Theme
  const bg     = isDark ? "#0d1424" : "#ffffff";
  const border = isDark ? "#1e293b" : "#e2e8f0";
  const text   = isDark ? "#e2e8f0" : "#1e293b";
  const muted  = isDark ? "#475569" : "#94a3b8";
  const hover  = isDark ? "#1e293b" : "#f1f5f9";
  const btnBg  = isDark ? "#1e293b" : "#f8fafc";
  const btnBrd = isDark ? "#334155" : "#e2e8f0";
  const selBg  = "#2563eb";

  const now = new Date();
  const isCurrentMonth = value.year === now.getFullYear() && value.month === (now.getMonth() + 1);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      {/* Trigger button */}
      <button
        onClick={() => { setOpen(o => !o); setViewYear(value.year); }}
        style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: "6px 12px", background: btnBg,
          border: `1px solid ${btnBrd}`, borderRadius: 8,
          fontSize: 12, color: text, cursor: "pointer",
          transition: "background 0.15s",
        }}
      >
        <Calendar style={{ width: 13, height: 13, color: muted }} />
        <span style={{ fontWeight: 600 }}>{value.label}</span>
        {!isCurrentMonth && (
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#3b82f6", display: "inline-block" }} />
        )}
        <ChevronDown style={{ width: 12, height: 12, color: muted }} />
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 9999,
          background: bg, border: `1px solid ${border}`, borderRadius: 10,
          boxShadow: isDark ? "0 8px 32px rgba(0,0,0,0.6)" : "0 8px 32px rgba(0,0,0,0.12)",
          width: 240, overflow: "hidden",
        }}>
          {/* Year navigation */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", borderBottom: `1px solid ${border}` }}>
            <button
              onClick={() => setViewYear(y => y - 1)}
              style={{ background: "none", border: "none", cursor: "pointer", color: muted, display: "flex", padding: 2 }}
            >
              <ChevronLeft style={{ width: 16, height: 16 }} />
            </button>
            <span style={{ fontSize: 13, fontWeight: 700, color: text }}>{viewYear}</span>
            <button
              onClick={() => setViewYear(y => Math.min(y + 1, now.getFullYear()))}
              style={{ background: "none", border: "none", cursor: "pointer", color: viewYear >= now.getFullYear() ? border : muted, display: "flex", padding: 2 }}
              disabled={viewYear >= now.getFullYear()}
            >
              <ChevronRight style={{ width: 16, height: 16 }} />
            </button>
          </div>

          {/* Month grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, padding: 10 }}>
            {MONTHS.map((m, i) => {
              const mon      = i + 1;
              const isSel    = value.year === viewYear && value.month === mon;
              const isFuture = viewYear === now.getFullYear() && mon > now.getMonth() + 1;
              return (
                <button
                  key={m}
                  onClick={() => !isFuture && select(viewYear, mon)}
                  disabled={isFuture}
                  style={{
                    padding: "7px 4px", borderRadius: 7, fontSize: 12, fontWeight: isSel ? 700 : 500,
                    cursor: isFuture ? "default" : "pointer", border: "none",
                    background: isSel ? selBg : "transparent",
                    color: isSel ? "#fff" : isFuture ? muted : text,
                    opacity: isFuture ? 0.35 : 1,
                    transition: "background 0.12s",
                  }}
                  onMouseEnter={e => { if (!isSel && !isFuture) (e.currentTarget as HTMLButtonElement).style.background = hover; }}
                  onMouseLeave={e => { if (!isSel) (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
                >
                  {m}
                </button>
              );
            })}
          </div>

          {/* Footer — reset / today */}
          <div style={{ borderTop: `1px solid ${border}`, padding: "8px 12px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <button
              onClick={clearFilter}
              style={{ fontSize: 11, color: "#3b82f6", background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}
            >
              This month
            </button>
            <button
              onClick={() => setOpen(false)}
              style={{ fontSize: 11, color: muted, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 3 }}
            >
              <X style={{ width: 11, height: 11 }} /> Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

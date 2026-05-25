import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import { Trash2 } from "lucide-react";

const MODE_CLS: Record<string, string> = {
  FUEL_CHARGE:   "bg-blue-100 text-blue-700",
  BASE_RATE:     "bg-purple-100 text-purple-700",
  ACCESSORIAL:   "bg-orange-100 text-orange-700",
  SURCHARGE:     "bg-cyan-100 text-cyan-700",
};

const STATUS_CLS: Record<string, string> = {
  active:  "bg-emerald-100 text-emerald-700",
  expired: "bg-red-100 text-red-700",
};

type TabKey = "contract" | "rates" | "bid";

const RATE_SCHEDULE = [
  { lane: "HYD → WGL", mode: "FTL",    band: "0–500 kg",    contract: "₹6,000",  ask: "₹6,000",  delta: "₹0",     flag: "OK"   },
  { lane: "HYD → WGL", mode: "FTL",    band: "500–1000 kg", contract: "₹8,000",  ask: "₹12,500", delta: "₹4,500", flag: "OVER" },
  { lane: "HYD → CHN", mode: "LTL",    band: "0–200 kg",    contract: "₹3,200",  ask: "₹3,200",  delta: "₹0",     flag: "OK"   },
  { lane: "HYD → MUM", mode: "FTL",    band: "0–1000 kg",   contract: "₹14,000", ask: "₹14,000", delta: "₹0",     flag: "OK"   },
  { lane: "BLR → DEL", mode: "AIR",    band: "0–100 kg",    contract: "₹8,500",  ask: "₹9,200",  delta: "₹700",   flag: "OVER" },
  { lane: "MUM → KOL", mode: "LTL",    band: "0–300 kg",    contract: "₹4,100",  ask: "₹4,100",  delta: "₹0",     flag: "OK"   },
];

const TIMELINE = [
  { date: "2026-05-20", event: "Rate Set Created",      actor: "Ravi (Analyst)",  color: "bg-blue-500",   detail: "BD-HYD-WGL-FTL-Q3 submitted for approval"            },
  { date: "2026-05-21", event: "OPA Policy Check",      actor: "System",          color: "bg-purple-500", detail: "OPA approved: budget within 5% of Q2 benchmark"      },
  { date: "2026-05-22", event: "Manager Review",        actor: "Ramu (Manager)",  color: "bg-amber-500",  detail: "Awaiting dual approval — SoD enforced"                },
  { date: "2026-05-23", event: "Carrier Counter-Offer", actor: "BlueDart Portal", color: "bg-cyan-500",   detail: "BlueDart accepted revised rate: ₹7,800 (was ₹8,000)" },
  { date: "2026-05-24", event: "Final Approval",        actor: "Ramu (Manager)",  color: "bg-emerald-500",detail: "APPROVED — effective 2026-06-01, ACR generated"       },
];

export default function RateControl() {
  const [tab, setTab] = useState<TabKey>("contract");
  const qc = useQueryClient();

  const { data: rates = [], isLoading } = useQuery({
    queryKey: ["contract-rates"],
    queryFn: zoikoApi.listContractRates,
  });

  const deleteMutation = useMutation({
    mutationFn: zoikoApi.deleteContractRate,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contract-rates"] }),
  });

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zoiko-navy">Rate Control</h1>
          <p className="text-sm text-muted-foreground mt-1">Contract rate sets · active &amp; pending approval</p>
        </div>
        <span className="text-[10px] font-bold px-3 py-1.5 rounded-full bg-zoiko-navy text-white">
          {rates.length} Rate{rates.length !== 1 ? "s" : ""} Active
        </span>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b">
        {(["contract", "rates", "bid"] as TabKey[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-5 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t
                ? "border-zoiko-navy text-zoiko-navy"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {t === "contract" ? "Contract Rates" : t === "rates" ? "Rate Sets" : "Bid Rates"}
          </button>
        ))}
      </div>

      {/* ── Contract Rates tab (live API) ─────────────────────────────────── */}
      {tab === "contract" && (
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
                Loading contract rates…
              </div>
            ) : rates.length === 0 ? (
              <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
                No contract rates yet — add a rate to get started.
              </div>
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="bg-zoiko-navy">
                    {["ID","Carrier","Rate Type","Rate Value","Currency","Effective On","Expires On",""].map(h => (
                      <th key={h} className="text-white text-[11px] font-semibold px-4 py-3 text-left whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rates.map((r, i) => {
                    const isExpired = r.expires_on ? new Date(r.expires_on) < new Date() : false;
                    return (
                      <tr key={r.id} className={cn("border-b hover:bg-secondary/30", i % 2 !== 0 && "bg-gray-50/50")}>
                        <td className="px-4 py-3 font-semibold text-blue-700 text-xs font-mono">{r.id.slice(0, 8)}…</td>
                        <td className="px-4 py-3 font-semibold text-zoiko-navy">{r.carrier}</td>
                        <td className="px-4 py-3">
                          <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded", MODE_CLS[r.rate_type] ?? "bg-gray-100 text-gray-700")}>
                            {r.rate_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-medium">{r.rate_value.toLocaleString()}</td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{r.currency}</td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{r.effective_on}</td>
                        <td className="px-4 py-3">
                          {r.expires_on ? (
                            <span className={cn("text-[10px] font-bold px-2.5 py-1 rounded-full", isExpired ? STATUS_CLS.expired : STATUS_CLS.active)}>
                              {r.expires_on}
                            </span>
                          ) : (
                            <span className="text-[10px] text-muted-foreground">No expiry</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => deleteMutation.mutate(r.id)}
                            disabled={deleteMutation.isPending}
                            className="text-muted-foreground hover:text-red-600 transition-colors"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Rate Sets tab ─────────────────────────────────────────────────── */}
      {tab === "rates" && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Current Rate Schedule — SC-001 Reference</CardTitle>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-zoiko-navy">
                  {["Lane","Mode","Weight Band","Contract Rate","Carrier Ask","Delta","Flag"].map(h => (
                    <th key={h} className="text-white text-[11px] font-semibold px-4 py-3 text-left whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {RATE_SCHEDULE.map((r, i) => (
                  <tr key={i} className={cn("border-b hover:bg-secondary/30", i % 2 !== 0 && "bg-gray-50/50")}>
                    <td className="px-4 py-3 font-semibold text-zoiko-navy">{r.lane}</td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded", MODE_CLS[r.mode] ?? "bg-gray-100 text-gray-700")}>
                        {r.mode}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{r.band}</td>
                    <td className="px-4 py-3 font-medium">{r.contract}</td>
                    <td className="px-4 py-3 font-medium">{r.ask}</td>
                    <td className={cn("px-4 py-3 font-bold", r.flag === "OVER" ? "text-red-600" : "text-emerald-600")}>
                      {r.delta}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "text-[10px] font-bold px-2.5 py-1 rounded-full",
                        r.flag === "OVER" ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
                      )}>
                        {r.flag}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* ── Bid Rates / Approval Timeline tab ────────────────────────────── */}
      {tab === "bid" && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Rate Negotiation — Approval Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-0">
              {TIMELINE.map(({ date, event, actor, color, detail }, idx) => (
                <div key={idx} className="flex gap-4 items-start">
                  <div className="w-24 text-xs text-muted-foreground pt-3 flex-shrink-0 text-right">{date}</div>
                  <div className="flex flex-col items-center flex-shrink-0">
                    <div className={cn("w-3 h-3 rounded-full mt-3 flex-shrink-0", color)} />
                    {idx < TIMELINE.length - 1 && <div className="w-0.5 flex-1 bg-border min-h-[28px]" />}
                  </div>
                  <div className="flex-1 pb-4">
                    <div className="bg-white border rounded-lg px-4 py-3">
                      <div className="font-semibold text-sm text-zoiko-navy">{event}</div>
                      <div className={cn("text-xs font-semibold mt-0.5", color.replace("bg-","text-").replace("-500","-700"))}>
                        {actor}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">{detail}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

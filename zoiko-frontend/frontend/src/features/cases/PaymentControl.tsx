import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency } from "@/utils/cn";
import { cn } from "@/utils/cn";
import { FileCheck2, Send, Clock, AlertTriangle } from "lucide-react";
import type { GovernanceToken, Case } from "@/types";

const STATUS_META: Record<string, { label: string; cls: string }> = {
  ACTIVE:   { label: "Active",   cls: "bg-blue-100 text-blue-700"       },
  CONSUMED: { label: "Consumed", cls: "bg-emerald-100 text-emerald-700" },
  EXPIRED:  { label: "Expired",  cls: "bg-red-100 text-red-700"         },
  REVOKED:  { label: "Revoked",  cls: "bg-amber-100 text-amber-700"     },
};

export default function PaymentControl() {
  const { data: cases = [] } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });
  const { data: tokens = [] } = useQuery({ queryKey: ["tokens"], queryFn: () => zoikoApi.listTokens() });

  const tokenList = tokens as GovernanceToken[];
  const caseList  = cases  as Case[];

  const totalRecovered = caseList.reduce((s, c) =>
    ["DISPATCHED","OUTCOME_RECORDED","CLOSED"].includes(c.state) ? s + (c.diff || 0) : s, 0
  );
  const pendingApproval = caseList.filter(c => c.state === "APPROVAL_PENDING").length;
  const activeTokens    = tokenList.filter(t => t.status === "ACTIVE").length;
  const expiredTokens   = tokenList.filter(t => t.status === "EXPIRED").length;
  const consumedTokens  = tokenList.filter(t => t.status === "CONSUMED").length;

  const kpis = [
    { label: "Governance Tokens",    value: String(tokenList.length), icon: FileCheck2,    color: "border-l-blue-500",    text: "text-blue-700"    },
    { label: "Consumed (Executed)",  value: String(consumedTokens),   icon: Send,          color: "border-l-emerald-500", text: "text-emerald-700" },
    { label: "Awaiting Approval",    value: String(pendingApproval),  icon: Clock,         color: "border-l-amber-500",   text: "text-amber-700"   },
    { label: "Expired Tokens",       value: String(expiredTokens),    icon: AlertTriangle, color: "border-l-red-500",     text: "text-red-700"     },
  ];

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zoiko-navy">Payment Control</h1>
          <p className="text-sm text-muted-foreground mt-1">Approved recoveries · governance token status</p>
        </div>
        <div className="flex gap-2">
          {totalRecovered > 0 && (
            <span className="text-[10px] font-bold px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-700">
              {formatCurrency(totalRecovered)} Recovered
            </span>
          )}
          {activeTokens > 0 && (
            <span className="text-[10px] font-bold px-3 py-1.5 rounded-full bg-amber-100 text-amber-700">
              {activeTokens} Active Token{activeTokens > 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map(({ label, value, icon: Icon, color, text }) => (
          <Card key={label} className={`border-l-4 ${color}`}>
            <CardContent className="pt-5">
              <div className="flex items-start justify-between">
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">{label}</p>
                <Icon className="h-4 w-4 text-muted-foreground/50" />
              </div>
              <p className={`mt-2 text-3xl font-bold ${text}`}>{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Governance Token register */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Governance Token Register</CardTitle>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          {tokenList.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
              No governance tokens yet — approve a recovery proposal to issue a token.
            </div>
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-zoiko-navy">
                  {["Token ID","Case","Action","Currency","Amount","Issued At","Expires","Status"].map(h => (
                    <th key={h} className="text-white text-[11px] font-semibold px-4 py-3 text-left whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tokenList.map((tok, i) => {
                  const sm = STATUS_META[tok.status] ?? { label: tok.status, cls: "bg-secondary text-foreground" };
                  return (
                    <tr key={tok.id} className={cn("border-b hover:bg-secondary/30", i % 2 !== 0 && "bg-gray-50/50")}>
                      <td className="px-4 py-3 font-semibold text-blue-700 text-xs font-mono">{tok.id.slice(0, 8)}…</td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{tok.case_id.slice(0, 8)}…</td>
                      <td className="px-4 py-3 text-xs font-semibold text-zoiko-navy">{tok.action.replace("EXECUTE_","")}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{tok.currency}</td>
                      <td className="px-4 py-3 font-bold text-emerald-700">{formatCurrency(tok.amount)}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {new Date(tok.issued_at).toLocaleString("en-IN",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"})}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {new Date(tok.exp).toLocaleString("en-IN",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"})}
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn("text-[10px] font-bold px-2.5 py-1 rounded-full", sm.cls)}>
                          {sm.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Cryptographic payment proof */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Cryptographic Payment Proof</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Every payment instruction is backed by an <strong>Action Certification Record (ACR)</strong> —
            8 artifacts hashed into a Merkle tree and signed with Ed25519.
            Carriers receive a credit memo with the ACR Merkle root; any auditor can verify it offline.
          </p>
          {tokenList.filter(t => t.status === "CONSUMED").length === 0 ? (
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
              No consumed tokens yet — ACR records appear after token redemption.
            </div>
          ) : (
            <div className="space-y-2">
              {tokenList.filter(t => t.status === "CONSUMED").map(tok => (
                <div key={tok.id} className="flex items-start gap-3 p-3 rounded-lg bg-blue-50 border border-blue-100">
                  <div className="h-2 w-2 rounded-full bg-blue-500 mt-1.5 flex-shrink-0" />
                  <div className="text-xs">
                    <span className="font-semibold text-blue-800">Token {tok.id.slice(0, 8)}</span>
                    {" · "}Case: <code className="bg-blue-100 px-1 rounded">{tok.case_id.slice(0,8)}</code>
                    {" · "}Amount: <strong>{formatCurrency(tok.amount)}</strong>
                    {" · "}Key: <code className="bg-blue-100 px-1 rounded">{tok.key_id}</code>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

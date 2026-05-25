import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import { Database, Lock, Shield, RefreshCw } from "lucide-react";

const TABLE_META: Record<string, { group: string; append: boolean; rls: boolean }> = {
  tenants:                      { group: "Tenant",         append: false, rls: true  },
  tenant_keys:                  { group: "Tenant",         append: false, rls: true  },
  source_records:               { group: "Ingestion",      append: false, rls: true  },
  lineage_records:              { group: "Ingestion",      append: true,  rls: true  },
  validation_results:           { group: "Validation",     append: false, rls: true  },
  canonical_invoices:           { group: "Canonical",      append: false, rls: true  },
  canonical_shipments:          { group: "Canonical",      append: false, rls: true  },
  contract_rates:               { group: "Canonical",      append: false, rls: true  },
  cases:                        { group: "Case",           append: false, rls: true  },
  case_events:                  { group: "Case",           append: true,  rls: true  },
  evidence_bundles:             { group: "Evidence",       append: false, rls: true  },
  evidence_items:               { group: "Evidence",       append: true,  rls: true  },
  findings:                     { group: "Reasoning",      append: false, rls: true  },
  decision_proposals:           { group: "Reasoning",      append: false, rls: true  },
  policy_bundles:               { group: "Governance",     append: false, rls: false },
  governance_decisions:         { group: "Governance",     append: false, rls: true  },
  approval_tasks:               { group: "Governance",     append: false, rls: true  },
  governance_tokens:            { group: "Token",          append: false, rls: true  },
  idempotency_keys:             { group: "Infrastructure", append: false, rls: true  },
  execution_envelopes:          { group: "Execution",      append: false, rls: true  },
  connector_responses:          { group: "Execution",      append: false, rls: true  },
  reconciliations:              { group: "Reconciliation", append: false, rls: true  },
  outcomes:                     { group: "Reconciliation", append: false, rls: true  },
  action_certification_records: { group: "Audit",          append: false, rls: true  },
  outbox:                       { group: "Infrastructure", append: false, rls: false },
  audit_worm_index:             { group: "Audit",          append: true,  rls: false },
};

const GROUP_COLORS: Record<string, string> = {
  "Tenant":          "bg-slate-100 text-slate-700",
  "Ingestion":       "bg-blue-100 text-blue-700",
  "Validation":      "bg-indigo-100 text-indigo-700",
  "Canonical":       "bg-violet-100 text-violet-700",
  "Case":            "bg-amber-100 text-amber-700",
  "Evidence":        "bg-orange-100 text-orange-700",
  "Reasoning":       "bg-purple-100 text-purple-700",
  "Governance":      "bg-pink-100 text-pink-700",
  "Token":           "bg-emerald-100 text-emerald-700",
  "Infrastructure":  "bg-gray-100 text-gray-600",
  "Execution":       "bg-green-100 text-green-700",
  "Reconciliation":  "bg-teal-100 text-teal-700",
  "Audit":           "bg-rose-100 text-rose-700",
};

export default function DatabasePage() {
  const { data: dbStats = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ["db-stats"],
    queryFn: zoikoApi.getDbStats,
    refetchInterval: 60_000,
  });

  const rowMap: Record<string, number> = {};
  for (const s of dbStats) rowMap[s.table] = s.rows;

  const tables = Object.entries(TABLE_META).map(([name, meta]) => ({
    name,
    ...meta,
    rows: rowMap[name] ?? 0,
  }));

  const groups = [...new Set(tables.map(t => t.group))];
  const totalRows  = tables.reduce((s, t) => s + t.rows, 0);
  const appendOnly = tables.filter(t => t.append).length;
  const rlsEnabled = tables.filter(t => t.rls).length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zoiko-navy">Database Schema</h1>
          <p className="text-sm text-muted-foreground mt-1">
            PostgreSQL · {tables.length} tables · Row-Level Security · Append-only audit tables · Live row counts
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground border rounded-lg px-3 py-1.5 bg-white transition-colors"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="border-l-4 border-l-zoiko-navy">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Total Rows (Live)</p>
            <p className="text-2xl font-bold mt-1">
              {isLoading ? <span className="text-muted-foreground text-base">Loading…</span> : totalRows.toLocaleString()}
            </p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium flex items-center gap-1">
              <Lock className="h-3 w-3" />Append-Only
            </p>
            <p className="text-2xl font-bold mt-1">{appendOnly} tables</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium flex items-center gap-1">
              <Shield className="h-3 w-3" />RLS Enabled
            </p>
            <p className="text-2xl font-bold mt-1">{rlsEnabled} tables</p>
          </CardContent>
        </Card>
      </div>

      {/* Tables by group */}
      <div className="space-y-4">
        {groups.map(group => {
          const groupTables = tables.filter(t => t.group === group);
          const chipClass = GROUP_COLORS[group] ?? "bg-gray-100 text-gray-600";
          return (
            <Card key={group}>
              <CardHeader className="pb-2 pt-4">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  <span className={cn("px-2 py-0.5 rounded text-xs font-bold", chipClass)}>{group}</span>
                  <span className="text-muted-foreground font-normal text-xs">
                    ({groupTables.length} table{groupTables.length > 1 ? "s" : ""})
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-[10px] uppercase tracking-wide text-muted-foreground">
                      <th className="text-left py-2 font-medium">Table</th>
                      <th className="text-center py-2 font-medium">RLS</th>
                      <th className="text-center py-2 font-medium">Mode</th>
                      <th className="text-right py-2 font-medium">Live Rows</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {groupTables.map(t => (
                      <tr key={t.name} className="hover:bg-secondary/30">
                        <td className="py-2">
                          <code className="text-xs font-mono">{t.name}</code>
                        </td>
                        <td className="py-2 text-center">
                          {t.rls
                            ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">RLS</span>
                            : <span className="text-[10px] text-muted-foreground">—</span>
                          }
                        </td>
                        <td className="py-2 text-center">
                          {t.append
                            ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 flex items-center gap-1 justify-center w-fit mx-auto"><Lock className="h-2.5 w-2.5" />Append-only</span>
                            : <span className="text-[10px] text-muted-foreground">mutable</span>
                          }
                        </td>
                        <td className="py-2 text-right font-mono text-xs">
                          {isLoading ? (
                            <span className="text-muted-foreground">…</span>
                          ) : (
                            <span className={t.rows === 0 ? "text-muted-foreground" : "text-foreground font-medium"}>
                              {t.rows.toLocaleString()}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

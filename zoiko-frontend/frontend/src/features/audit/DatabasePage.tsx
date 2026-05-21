import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/utils/cn";
import { Database, Lock, Shield } from "lucide-react";

const TABLES = [
  { name: "tenants",                      group: "Tenant",          append: false, rls: true,  rows: 3   },
  { name: "tenant_keys",                  group: "Tenant",          append: false, rls: true,  rows: 9   },
  { name: "source_records",               group: "Ingestion",       append: false, rls: true,  rows: 47  },
  { name: "lineage_records",              group: "Ingestion",       append: true,  rls: true,  rows: 184 },
  { name: "validation_results",           group: "Validation",      append: false, rls: true,  rows: 47  },
  { name: "canonical_invoices",           group: "Canonical",       append: false, rls: true,  rows: 47  },
  { name: "canonical_shipments",          group: "Canonical",       append: false, rls: true,  rows: 47  },
  { name: "contract_rates",               group: "Canonical",       append: false, rls: true,  rows: 25  },
  { name: "cases",                        group: "Case",            append: false, rls: true,  rows: 47  },
  { name: "case_events",                  group: "Case",            append: true,  rls: true,  rows: 312 },
  { name: "evidence_bundles",             group: "Evidence",        append: false, rls: true,  rows: 31  },
  { name: "evidence_items",               group: "Evidence",        append: true,  rls: true,  rows: 94  },
  { name: "findings",                     group: "Reasoning",       append: false, rls: true,  rows: 28  },
  { name: "decision_proposals",           group: "Reasoning",       append: false, rls: true,  rows: 28  },
  { name: "policy_bundles",               group: "Governance",      append: false, rls: false, rows: 4   },
  { name: "governance_decisions",         group: "Governance",      append: false, rls: true,  rows: 26  },
  { name: "approval_tasks",               group: "Governance",      append: false, rls: true,  rows: 28  },
  { name: "governance_tokens",            group: "Token",           append: false, rls: true,  rows: 26  },
  { name: "idempotency_keys",             group: "Infrastructure",  append: false, rls: true,  rows: 412 },
  { name: "execution_envelopes",          group: "Execution",       append: false, rls: true,  rows: 0   },
  { name: "connector_responses",          group: "Execution",       append: false, rls: true,  rows: 0   },
  { name: "reconciliations",              group: "Reconciliation",  append: false, rls: true,  rows: 0   },
  { name: "outcomes",                     group: "Reconciliation",  append: false, rls: true,  rows: 0   },
  { name: "action_certification_records", group: "Audit",           append: false, rls: true,  rows: 0   },
  { name: "outbox",                       group: "Infrastructure",  append: false, rls: false, rows: 528 },
  { name: "audit_worm_index",             group: "Audit",           append: true,  rls: false, rows: 0   },
];

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

const groups = [...new Set(TABLES.map(t => t.group))];

export default function DatabasePage() {
  const totalRows = TABLES.reduce((s, t) => s + t.rows, 0);
  const appendOnly = TABLES.filter(t => t.append).length;
  const rlsEnabled = TABLES.filter(t => t.rls).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-zoiko-navy">Database Schema</h1>
        <p className="text-sm text-muted-foreground mt-1">
          PostgreSQL · 26 tables · Row-Level Security · Append-only audit tables.
        </p>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="border-l-4 border-l-zoiko-navy">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Total Rows</p>
            <p className="text-2xl font-bold mt-1">{totalRows.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium flex items-center gap-1"><Lock className="h-3 w-3" />Append-Only</p>
            <p className="text-2xl font-bold mt-1">{appendOnly} tables</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-4 pb-4">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium flex items-center gap-1"><Shield className="h-3 w-3" />RLS Enabled</p>
            <p className="text-2xl font-bold mt-1">{rlsEnabled} tables</p>
          </CardContent>
        </Card>
      </div>

      {/* Tables by group */}
      <div className="space-y-4">
        {groups.map(group => {
          const groupTables = TABLES.filter(t => t.group === group);
          const chipClass = GROUP_COLORS[group] ?? "bg-gray-100 text-gray-600";
          return (
            <Card key={group}>
              <CardHeader className="pb-2 pt-4">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  <span className={cn("px-2 py-0.5 rounded text-xs font-bold", chipClass)}>{group}</span>
                  <span className="text-muted-foreground font-normal text-xs">({groupTables.length} table{groupTables.length > 1 ? "s" : ""})</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-[10px] uppercase tracking-wide text-muted-foreground">
                      <th className="text-left py-2 font-medium">Table</th>
                      <th className="text-center py-2 font-medium">RLS</th>
                      <th className="text-center py-2 font-medium">Mode</th>
                      <th className="text-right py-2 font-medium">Rows</th>
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
                          <span className={t.rows === 0 ? "text-muted-foreground" : "text-foreground font-medium"}>
                            {t.rows.toLocaleString()}
                          </span>
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

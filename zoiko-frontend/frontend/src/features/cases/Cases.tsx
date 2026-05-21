import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { StateBadge, LoadingSpinner, EmptyState } from "@/components/shared";
import { formatCurrency, formatDate } from "@/utils/cn";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import type { CaseState } from "@/types";

const STATES: (CaseState | "ALL")[] = [
  "ALL",
  "NEW", "EVIDENCE_PENDING", "FINDING_GENERATED",
  "APPROVAL_PENDING", "EXECUTION_READY",
  "DISPATCHED", "OUTCOME_RECORDED", "CLOSED", "ABORTED",
];

export default function Cases() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<CaseState | "ALL">("ALL");
  const { data: cases, isLoading } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });

  const filtered = (cases || [])
    .filter(c => filter === "ALL" || c.state === filter)
    .filter(c => !search || c.id.includes(search) || c.carrier.toLowerCase().includes(search.toLowerCase()) || c.shipment_ref.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zoiko-navy">All Cases</h1>
          <p className="text-sm text-muted-foreground mt-1">{cases?.length ?? 0} cases total</p>
        </div>
        <Link to="/cases/new"><Button>+ New case</Button></Link>
      </div>

      <Card>
        <CardContent className="pt-6 space-y-4">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search by ID, carrier, or shipment ref…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <div className="flex gap-1 flex-wrap">
              {STATES.map(s => (
                <Button
                  key={s}
                  size="sm"
                  variant={filter === s ? "default" : "outline"}
                  onClick={() => setFilter(s)}
                >
                  {s === "ALL" ? "All" : s.replace(/_/g, " ")}
                </Button>
              ))}
            </div>
          </div>

          {isLoading ? <LoadingSpinner /> : filtered.length === 0 ? (
            <EmptyState title="No cases match your filters" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Case ID</TableHead>
                  <TableHead>Carrier</TableHead>
                  <TableHead>Shipment</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead className="text-right">Overcharge</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map(c => (
                  <TableRow key={c.id} className="cursor-pointer">
                    <TableCell>
                      <Link to={`/cases/${c.id}`} className="font-mono text-xs text-zoiko-blue hover:underline">
                        {c.id}
                      </Link>
                    </TableCell>
                    <TableCell>{c.carrier}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{c.shipment_ref}</TableCell>
                    <TableCell className="text-right">{formatCurrency(c.amount, c.currency)}</TableCell>
                    <TableCell className="text-right text-destructive">{formatCurrency(c.diff, c.currency)}</TableCell>
                    <TableCell>
                      {c.confidence ? (
                        <span className={c.confidence >= 0.9 ? "text-emerald-600 font-medium" : "text-amber-700"}>
                          {(c.confidence * 100).toFixed(0)}%
                        </span>
                      ) : "—"}
                    </TableCell>
                    <TableCell><StateBadge state={c.state} /></TableCell>
                    <TableCell className="text-xs text-muted-foreground">{formatDate(c.updated_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

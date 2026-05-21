import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StateBadge, LoadingSpinner, PipelineBanner } from "@/components/shared";
import { formatCurrency } from "@/utils/cn";
import { Link } from "react-router-dom";
import { ArrowRight, ThumbsUp, CheckCircle2 } from "lucide-react";
import { useState } from "react";

export default function AnalystReview() {
  const qc = useQueryClient();
  const { pathname } = useLocation();
  const { data: cases, isLoading } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });
  const [proposed, setProposed] = useState<Set<string>>(new Set());

  const queue = (cases || [])
    .filter(c => ["NEW", "EVIDENCE_PENDING", "FINDING_GENERATED"].includes(c.state))
    .sort((a, b) => (b.confidence || 0) - (a.confidence || 0));

  const propose = useMutation({
    mutationFn: (c: { id: string; diff: number; currency: string }) =>
      zoikoApi.proposeRecovery(c.id, {
        action:   "EXECUTE_CREDIT_MEMO",
        amount:   c.diff,
        currency: c.currency || "INR",
      }),
    onSuccess: (_d, vars) => {
      setProposed(prev => new Set(prev).add(vars.id));
      qc.invalidateQueries({ queryKey: ["cases"] });
    },
  });

  const user = localStorage.getItem("zoiko_user") || "Analyst";

  return (
    <div className="space-y-6">
      <PipelineBanner currentRoute={pathname} />

      <div>
        <h1 className="text-2xl font-semibold text-zoiko-navy">Analyst Review</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Signed in as <span className="font-medium text-foreground">{user}</span> ·
          Review flagged invoices and propose recovery. Sorted by AI confidence (highest first).
        </p>
      </div>

      {isLoading ? <LoadingSpinner /> : queue.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center py-12">
            <CheckCircle2 className="h-10 w-10 text-emerald-600 mx-auto mb-3" />
            <p className="font-medium">All clear — no cases waiting for review.</p>
            <p className="text-sm text-muted-foreground mt-1">New invoices will appear here once validation detects an overcharge.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {queue.map(c => {
            const isDone = proposed.has(c.id);
            return (
              <Card key={c.id} className={isDone ? "opacity-60" : ""}>
                <CardContent className="pt-6">
                  <div className="flex items-start gap-4">
                    {/* Confidence ring */}
                    <div className="text-center flex-shrink-0 w-16">
                      <div className={`text-2xl font-bold ${(c.confidence || 0) >= 0.9 ? "text-emerald-600" : "text-amber-600"}`}>
                        {((c.confidence || 0) * 100).toFixed(0)}%
                      </div>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground leading-tight">AI confidence</p>
                    </div>

                    {/* Details */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <code className="text-xs text-muted-foreground">{c.id}</code>
                        <StateBadge state={c.state} />
                      </div>
                      <p className="font-semibold mt-1 text-zoiko-navy">{c.carrier}</p>
                      <p className="text-sm text-muted-foreground">{c.shipment_ref}</p>
                      <div className="flex items-center gap-4 mt-2 text-sm">
                        <span>Invoice <strong>{formatCurrency(c.amount, c.currency)}</strong></span>
                        <span className="text-destructive font-medium">Overcharge {formatCurrency(c.diff, c.currency)}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col gap-2 flex-shrink-0">
                      <Link to={`/cases/${c.id}`}>
                        <Button variant="outline" size="sm" className="w-full">
                          Case detail <ArrowRight className="ml-1 h-3 w-3" />
                        </Button>
                      </Link>
                      {isDone ? (
                        <div className="flex items-center gap-1.5 text-sm text-emerald-600 font-medium justify-center">
                          <CheckCircle2 className="h-4 w-4" /> Proposed
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => propose.mutate({ id: c.id, diff: c.diff, currency: c.currency })}
                          disabled={propose.isPending}
                        >
                          <ThumbsUp className="mr-1.5 h-3.5 w-3.5" />
                          Propose {formatCurrency(c.diff, c.currency)}
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

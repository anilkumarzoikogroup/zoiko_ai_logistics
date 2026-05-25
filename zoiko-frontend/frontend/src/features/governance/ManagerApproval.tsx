import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StateBadge, SkeletonCard } from "@/components/shared";
import { formatCurrency, formatDate } from "@/utils/cn";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, XCircle, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useToast } from "@/hooks/useToast";

export default function ManagerApproval() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: cases, isLoading } = useQuery({ queryKey: ["cases"], queryFn: () => zoikoApi.listCases() });
  const [decided, setDecided] = useState<Record<string, "EXECUTION_READY" | "ABORTED">>({});

  const queue = (cases || []).filter(c => c.state === "APPROVAL_PENDING");

  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "EXECUTION_READY" | "ABORTED" }) =>
      zoikoApi.approveDecision(id, { decision }),
    onSuccess: (_d, vars) => {
      setDecided(prev => ({ ...prev, [vars.id]: vars.decision }));
      qc.invalidateQueries({ queryKey: ["cases"] });
      if (vars.decision === "EXECUTION_READY") {
        toast.success("Case approved", "Governance token issued — 15-min execution window open");
      } else {
        toast.info("Case rejected", "Case has been marked ABORTED");
      }
    },
    onError: () => {
      toast.error("Decision failed", "Check SoD rule — you cannot approve your own proposal");
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zoiko-navy">Manager Approval</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Cases proposed by analysts, awaiting your decision.
        </p>
      </div>

      <Card className="border-amber-200 bg-amber-50/40">
        <CardContent className="pt-6">
          <div className="flex items-start gap-3">
            <ShieldAlert className="h-5 w-5 text-amber-700 mt-0.5 flex-shrink-0" />
            <div className="text-sm">
              <p className="font-semibold text-amber-900">Separation of Duties enforced</p>
              <p className="text-amber-800 mt-1">
                You cannot approve a case you proposed yourself. If your sub matches the proposer_sub, the API rejects the request before any database write.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <div className="space-y-3">{[0,1,2].map(i => <SkeletonCard key={i} />)}</div>
      ) : queue.length === 0 ? (
        <Card><CardContent className="pt-6 text-sm text-muted-foreground">No cases waiting for approval.</CardContent></Card>
      ) : (
        <div className="space-y-3">
          {queue.map(c => (
            <Card key={c.id}>
              <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <code className="text-xs text-muted-foreground">{c.id}</code>
                      <StateBadge state={c.state} />
                    </div>
                    <p className="font-medium mt-1">{c.carrier} · {c.shipment_ref}</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      Invoice {formatCurrency(c.amount, c.currency)} ·
                      Recovery proposed: <span className="text-destructive font-medium">{formatCurrency(c.diff, c.currency)}</span> ·
                      Confidence {((c.confidence || 0) * 100).toFixed(0)}%
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">Updated {formatDate(c.updated_at)}</p>
                  </div>
                  <div className="flex flex-col gap-2 ml-4">
                    <Link to={`/cases/${c.id}`}><Button variant="outline" size="sm" className="w-full">Review <ArrowRight className="ml-1 h-3 w-3" /></Button></Link>
                    {decided[c.id] ? (
                      <span className={decided[c.id] === "EXECUTION_READY" ? "text-emerald-600 text-sm font-medium" : "text-destructive text-sm font-medium"}>
                        {decided[c.id]}
                      </span>
                    ) : (
                      <div className="flex gap-2">
                        <Button size="sm" variant="success" onClick={() => decide.mutate({ id: c.id, decision: "EXECUTION_READY" })} disabled={decide.isPending}>
                          <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Approve
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => decide.mutate({ id: c.id, decision: "ABORTED" })} disabled={decide.isPending}>
                          <XCircle className="mr-1.5 h-3.5 w-3.5" /> Reject
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

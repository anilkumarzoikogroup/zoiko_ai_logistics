import { useQuery } from "@tanstack/react-query";
import { zoikoApi } from "@/api/zoiko";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/shared";
import { formatDate } from "@/utils/cn";
import { cn } from "@/utils/cn";
import { Activity, Radio } from "lucide-react";

const ALL_TOPICS = [
  { topic: "invoice.received",    group: "Ingestion",    color: "bg-blue-100 text-blue-700"      },
  { topic: "invoice.validated",   group: "Ingestion",    color: "bg-blue-100 text-blue-700"      },
  { topic: "invoice.canonical",   group: "Ingestion",    color: "bg-blue-100 text-blue-700"      },
  { topic: "case.opened",         group: "Cases",        color: "bg-amber-100 text-amber-700"    },
  { topic: "case.updated",        group: "Cases",        color: "bg-amber-100 text-amber-700"    },
  { topic: "case.closed",         group: "Cases",        color: "bg-amber-100 text-amber-700"    },
  { topic: "evidence.bundled",    group: "Evidence",     color: "bg-purple-100 text-purple-700"  },
  { topic: "finding.created",     group: "Reasoning",    color: "bg-violet-100 text-violet-700"  },
  { topic: "proposal.created",    group: "Governance",   color: "bg-indigo-100 text-indigo-700"  },
  { topic: "decision.made",       group: "Governance",   color: "bg-indigo-100 text-indigo-700"  },
  { topic: "token.issued",        group: "Token",        color: "bg-emerald-100 text-emerald-700"},
  { topic: "token.consumed",      group: "Token",        color: "bg-emerald-100 text-emerald-700"},
  { topic: "execution.started",   group: "Execution",    color: "bg-green-100 text-green-700"    },
  { topic: "execution.completed", group: "Execution",    color: "bg-green-100 text-green-700"    },
  { topic: "reconciliation.done", group: "Reconciliation", color: "bg-teal-100 text-teal-700"   },
  { topic: "acr.issued",          group: "Audit",        color: "bg-slate-100 text-slate-700"    },
  { topic: "audit.locked",        group: "Audit",        color: "bg-slate-100 text-slate-700"    },
];

const TOPIC_COLOR: Record<string, string> = Object.fromEntries(ALL_TOPICS.map(t => [t.topic, t.color]));

export default function KafkaEvents() {
  const { data: events, isLoading } = useQuery({ queryKey: ["kafka-events"], queryFn: zoikoApi.listKafkaEvents });

  const groups = [...new Set(ALL_TOPICS.map(t => t.group))];

  return (
    <div className="space-y-6">

      <div className="flex items-center gap-3">
        <div>
          <h1 className="text-2xl font-bold text-zoiko-navy">Event Log</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Every state change in the system publishes to one of 17 Kafka topics. Full audit trail.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-700 text-xs font-bold">
          <Radio className="h-3.5 w-3.5 animate-pulse" />
          Live stream
        </div>
      </div>

      {/* Topic registry */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Activity className="h-4 w-4" />
            17 Registered Topics
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {groups.map(group => (
              <div key={group}>
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1.5">{group}</p>
                <div className="flex flex-wrap gap-1.5">
                  {ALL_TOPICS.filter(t => t.group === group).map(t => (
                    <span key={t.topic} className={cn("text-[11px] font-mono font-medium px-2 py-0.5 rounded", t.color)}>
                      {t.topic}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Event stream */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">SC-001 — Event Stream</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <LoadingSpinner /> : !events || events.length === 0 ? (
            <p className="text-sm text-muted-foreground">No events yet — submit an invoice to start the pipeline.</p>
          ) : (
            <div className="relative">
              <div className="absolute left-3 top-0 bottom-0 w-px bg-border" />
              <ol className="space-y-3">
                {events.map((e, i) => {
                  const topicColor = TOPIC_COLOR[e.topic] ?? "bg-gray-100 text-gray-700";
                  return (
                    <li key={i} className="pl-8 relative">
                      <div className="absolute left-1.5 top-1 h-3 w-3 rounded-full bg-white border-2 border-zoiko-navy" />
                      <div className="flex items-start gap-3 flex-wrap">
                        <span className={cn("text-[11px] font-mono font-semibold px-2 py-0.5 rounded flex-shrink-0", topicColor)}>
                          {e.topic}
                        </span>
                        <code className="text-[10px] text-muted-foreground">key={e.key}</code>
                        <span className="text-[10px] text-muted-foreground">{formatDate(e.published_at)}</span>
                      </div>
                      <div className="mt-1 ml-0">
                        <code className="text-[10px] bg-secondary/50 px-2 py-0.5 rounded text-muted-foreground">
                          {JSON.stringify(e.payload)}
                        </code>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

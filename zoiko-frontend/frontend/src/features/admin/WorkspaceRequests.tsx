import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useToast } from "@/hooks/useToast";
import { useAppSelector } from "@/store";
import { cn } from "@/utils/cn";
import { CheckCircle2, XCircle, Clock, Building2, Mail, Users, Briefcase } from "lucide-react";

interface WorkspaceRequest {
  id: string;
  full_name: string;
  work_email: string;
  company_name: string;
  country: string;
  role: string;
  use_case: string;
  team_size: string;
  status: string;
  created_at: string;
}

const STATUS_STYLE: Record<string, string> = {
  PENDING:  "bg-amber-50 text-amber-700 border border-amber-200",
  APPROVED: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  REJECTED: "bg-red-50 text-red-700 border border-red-200",
};

export default function WorkspaceRequests() {
  const qc    = useQueryClient();
  const toast = useToast();
  const role  = useAppSelector(s => s.auth.role);
  const [approving, setApproving] = useState<string | null>(null);
  const [password, setPassword]   = useState("");
  const [pwError, setPwError]     = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["workspace-requests"],
    queryFn:  () => api.get("/v1/admin/workspace-requests").then(r => r.data),
    enabled:  role === "admin",
  });

  const approveMut = useMutation({
    mutationFn: ({ id, pw }: { id: string; pw: string }) =>
      api.post(`/v1/admin/workspace-requests/${id}/approve`, { password: pw }),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["workspace-requests"] });
      toast.success("Approved", "Tenant and admin user created. Welcome email sent.");
      setApproving(null); setPassword(""); setPwError("");
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPwError(typeof msg === "string" ? msg : "Approval failed.");
    },
  });

  const rejectMut = useMutation({
    mutationFn: (id: string) => api.post(`/v1/admin/workspace-requests/${id}/reject`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workspace-requests"] });
      toast.success("Rejected", "Request has been rejected.");
    },
  });

  if (role !== "admin") {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="text-sm font-semibold text-red-700">Admin access required</p>
      </div>
    );
  }

  const requests: WorkspaceRequest[] = data?.requests ?? [];
  const pending  = requests.filter(r => r.status === "PENDING");
  const others   = requests.filter(r => r.status !== "PENDING");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-slate-600" />
          <h2 className="text-lg font-bold text-slate-800">Workspace Requests</h2>
          {pending.length > 0 && (
            <span className="text-xs font-bold bg-red-100 text-red-700 px-2 py-0.5 rounded-full">
              {pending.length} pending
            </span>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1,2].map(i => <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />)}
        </div>
      )}

      {/* Pending */}
      {pending.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">Pending Approval</p>
          {pending.map(req => (
            <div key={req.id} className="rounded-xl border border-amber-200 bg-amber-50/40 p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-slate-500" />
                    <span className="font-bold text-slate-800">{req.company_name}</span>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-slate-600">
                    <span className="flex items-center gap-1"><Users className="h-3.5 w-3.5" />{req.full_name}</span>
                    <span className="flex items-center gap-1"><Mail className="h-3.5 w-3.5" />{req.work_email}</span>
                    {req.team_size && <span className="flex items-center gap-1"><Briefcase className="h-3.5 w-3.5" />{req.team_size} people</span>}
                  </div>
                  {req.use_case && <p className="text-xs text-slate-500 mt-1">Use case: {req.use_case}</p>}
                  <p className="text-xs text-slate-400">{new Date(req.created_at).toLocaleString("en-IN",{timeZone:"Asia/Kolkata",hour12:true})}</p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => { setApproving(req.id); setPwError(""); setPassword(""); }}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition-colors"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                  </button>
                  <button
                    onClick={() => rejectMut.mutate(req.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-100 hover:bg-red-200 text-red-700 rounded-lg text-xs font-bold transition-colors"
                  >
                    <XCircle className="h-3.5 w-3.5" /> Reject
                  </button>
                </div>
              </div>

              {/* Approve form */}
              {approving === req.id && (
                <div className="mt-4 pt-4 border-t border-amber-200 space-y-3">
                  <p className="text-xs font-semibold text-slate-700">
                    Set a temporary password for <strong>{req.full_name}</strong> ({req.work_email}):
                  </p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Temporary password (min 8 chars)"
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                    <button
                      onClick={() => {
                        if (password.length < 8) { setPwError("Min 8 characters"); return; }
                        approveMut.mutate({ id: req.id, pw: password });
                      }}
                      disabled={approveMut.isPending}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold"
                    >
                      {approveMut.isPending ? "Creating…" : "Confirm Approve"}
                    </button>
                    <button onClick={() => setApproving(null)} className="px-3 py-2 text-xs text-slate-500 hover:text-slate-700">Cancel</button>
                  </div>
                  {pwError && <p className="text-xs text-red-600">{pwError}</p>}
                  <p className="text-xs text-slate-400">This will create a new tenant for <strong>{req.company_name}</strong> and send a welcome email to the customer.</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {pending.length === 0 && !isLoading && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-8 text-center">
          <Clock className="h-8 w-8 text-slate-300 mx-auto mb-2" />
          <p className="text-sm text-slate-500">No pending requests</p>
        </div>
      )}

      {/* History */}
      {others.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">History</p>
          {others.map(req => (
            <div key={req.id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3">
              <div>
                <p className="text-sm font-semibold text-slate-800">{req.company_name}</p>
                <p className="text-xs text-slate-400">{req.full_name} · {req.work_email}</p>
              </div>
              <span className={cn("text-xs font-bold px-2.5 py-1 rounded-full", STATUS_STYLE[req.status] ?? "bg-slate-100 text-slate-600")}>
                {req.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { zoikoApi, RegisterRequest } from "@/api/zoiko";
import { useToast } from "@/hooks/useToast";
import { useAppSelector } from "@/store";
import { Users, Plus, ShieldCheck, Brain, Settings, X, CheckCircle2, KeyRound } from "lucide-react";
import { cn } from "@/utils/cn";
import { api } from "@/api/client";

const ROLE_META = {
  admin:   { label: "Admin",   color: "bg-slate-100 text-slate-700",  icon: Settings    },
  analyst: { label: "Analyst", color: "bg-blue-100 text-blue-700",    icon: Brain       },
  manager: { label: "Manager", color: "bg-violet-100 text-violet-700",icon: ShieldCheck },
};

export default function UserManagement() {
  const qc    = useQueryClient();
  const toast = useToast();
  const role  = useAppSelector(s => s.auth.role);

  const [showForm, setShowForm]   = useState(false);
  const [form, setForm]           = useState<RegisterRequest>({ email: "", full_name: "", role: "analyst" });
  const [formErr, setFormErr]     = useState("");

  // Change-password state (own account)
  const [showPwForm, setShowPwForm]     = useState(false);
  const [currentPw,  setCurrentPw]      = useState("");
  const [newPw,      setNewPw]          = useState("");
  const [pwErr,      setPwErr]          = useState("");
  const [pwOk,       setPwOk]           = useState(false);

  const usersQ = useQuery({
    queryKey: ["users"],
    queryFn:  () => zoikoApi.listUsers(),
    enabled:  role === "admin",
  });

  const createM = useMutation({
    mutationFn: (req: RegisterRequest) => zoikoApi.registerUser(req),
    onSuccess: (u) => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("User created", `${u.full_name} (${u.role}) will receive an email with OTP to set their password.`);
      setForm({ email: "", full_name: "", role: "analyst" });
      setShowForm(false);
      setFormErr("");
    },
    onError: (e: any) => {
      const msg = e?.response?.data?.detail;
      setFormErr(typeof msg === "string" ? msg : "Failed to create user.");
    },
  });

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwErr(""); setPwOk(false);
    if (newPw.length < 8) { setPwErr("New password must be at least 8 characters."); return; }
    try {
      await api.post("/auth/change-password", { current_password: currentPw, new_password: newPw });
      setPwOk(true);
      setCurrentPw(""); setNewPw("");
      toast.success("Password changed", "Your password has been updated.");
    } catch (e: any) {
      const msg = e?.response?.data?.detail;
      setPwErr(typeof msg === "string" ? msg : "Failed to change password.");
    }
  }

  if (role !== "admin") {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="text-sm font-semibold text-red-700">Admin access required</p>
        <p className="text-xs text-red-600 mt-1">Only admins can manage users.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-slate-600" />
          <h2 className="text-lg font-bold text-slate-800">User Management</h2>
          {usersQ.data && (
            <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full font-medium">
              {usersQ.data.length} users
            </span>
          )}
        </div>
        <button
          onClick={() => { setShowForm(v => !v); setFormErr(""); }}
          className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold transition-colors"
        >
          {showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {showForm ? "Cancel" : "Add User"}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-5 space-y-3">
          <p className="text-sm font-bold text-slate-700">New User</p>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Full Name</label>
              <input
                type="text"
                placeholder="Ravi Kumar"
                value={form.full_name}
                onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Work Email</label>
              <input
                type="email"
                placeholder="ravi@company.com"
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-600">Role</label>
              <select
                value={form.role}
                onChange={e => setForm(f => ({ ...f, role: e.target.value as RegisterRequest["role"] }))}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="analyst">Analyst — proposes recoveries</option>
                <option value="manager">Manager — approves recoveries</option>
              </select>
            </div>
          </div>

          <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3">
            <p className="text-xs font-medium text-amber-800">
              An email with a one-time password (OTP) will be sent to the user to set their password.
            </p>
          </div>

          {formErr && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{formErr}</p>
          )}

          <button
            disabled={createM.isPending || !form.email || !form.full_name}
            onClick={() => createM.mutate(form)}
            className={cn(
              "w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-colors",
              !createM.isPending && form.email && form.full_name
                ? "bg-blue-600 hover:bg-blue-700 text-white"
                : "bg-slate-200 text-slate-400 cursor-not-allowed"
            )}
          >
            {createM.isPending ? (
              <><div className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" /> Creating…</>
            ) : (
              <><Plus className="h-4 w-4" /> Create User</>
            )}
          </button>
        </div>
      )}

      {/* Users list */}
      {usersQ.isLoading ? (
        <div className="space-y-2">
          {[1,2,3].map(i => <div key={i} className="h-14 bg-slate-100 rounded-xl animate-pulse" />)}
        </div>
      ) : usersQ.data && usersQ.data.length > 0 ? (
        <div className="space-y-2">
          {usersQ.data.map(u => {
            const meta = ROLE_META[u.role as keyof typeof ROLE_META] ?? ROLE_META.analyst;
            const Icon = meta.icon;
            return (
              <div key={u.user_id} className="flex items-center gap-3 bg-white rounded-xl border border-slate-200 px-4 py-3 shadow-sm">
                <div className="h-9 w-9 rounded-full bg-slate-100 flex items-center justify-center font-bold text-slate-600 text-sm flex-shrink-0">
                  {u.full_name.split(" ").map((w: string) => w[0]).join("").slice(0,2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-800 truncate">{u.full_name}</p>
                  <p className="text-xs text-slate-400 truncate">{u.email}</p>
                </div>
                <span className={cn("text-xs font-semibold px-2.5 py-1 rounded-full flex items-center gap-1", meta.color)}>
                  <Icon className="h-3 w-3" />{meta.label}
                </span>
                {u.is_active ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                ) : (
                  <X className="h-4 w-4 text-red-400 flex-shrink-0" />
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-slate-400 text-center py-8">No users yet. Add the first user above.</p>
      )}

      {/* ── Change Own Password ─────────────────────────────────────────── */}
      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <button
          onClick={() => { setShowPwForm(v => !v); setPwErr(""); setPwOk(false); }}
          className="w-full flex items-center justify-between px-5 py-4 hover:bg-slate-50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-slate-500" />
            <span className="text-sm font-semibold text-slate-700">Change My Password</span>
          </div>
          {showPwForm ? <X className="h-4 w-4 text-slate-400" /> : <Plus className="h-4 w-4 text-slate-400" />}
        </button>

        {showPwForm && (
          <form onSubmit={handleChangePassword} className="border-t border-slate-100 px-5 py-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-600">Current password</label>
                <input
                  type="password"
                  value={currentPw}
                  onChange={e => setCurrentPw(e.target.value)}
                  required
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zoiko-navy"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-600">New password (min 8 chars)</label>
                <input
                  type="password"
                  value={newPw}
                  onChange={e => setNewPw(e.target.value)}
                  required
                  minLength={8}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zoiko-navy"
                />
              </div>
            </div>
            {pwErr && <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{pwErr}</p>}
            {pwOk  && <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">Password changed successfully.</p>}
            <button
              type="submit"
              disabled={!currentPw || newPw.length < 8}
              className={cn(
                "w-full py-2.5 rounded-lg text-sm font-semibold transition-colors",
                currentPw && newPw.length >= 8
                  ? "bg-zoiko-navy text-white hover:bg-zoiko-navy/90"
                  : "bg-slate-200 text-slate-400 cursor-not-allowed"
              )}
            >
              Update Password
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

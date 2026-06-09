import { Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useRef } from "react";
import AppLayout from "./layouts/AppLayout";
import { Toaster } from "@/components/ui/toast";
import { useAppSelector, useAppDispatch } from "@/store";
import { login as loginAction } from "@/store/authSlice";
import axios from "axios";

// auth
import Login          from "./auth/Login";
import GoogleCallback from "./auth/GoogleCallback";
import ForgotPassword from "./auth/ForgotPassword";

// features/dashboard
import Home        from "./features/dashboard/Home";
import Analytics   from "./features/dashboard/Analytics";
import Performance from "./features/dashboard/Performance";

// features/cases
import Cases          from "./features/cases/Cases";
import NewCase        from "./features/cases/NewCase";
import CaseDetail     from "./features/cases/CaseDetail";
import ExecuteRecovery from "./features/cases/ExecuteRecovery";
import PaymentControl from "./features/cases/PaymentControl";
import CarriersPage   from "./features/carriers/CarriersPage";
import RateControl    from "./features/cases/RateControl";

// features/governance
import AnalystReview  from "./features/governance/AnalystReview";
import ManagerApproval from "./features/governance/ManagerApproval";

// features/acr
import CryptoAudit   from "./features/acr/CryptoAudit";
import AcrVerifier   from "./features/acr/AcrVerifier";

// features/audit
import Alerts          from "./features/audit/Alerts";
import DatabasePage    from "./features/audit/DatabasePage";
import KafkaEvents     from "./features/audit/KafkaEvents";
import AuditConditions from "./features/audit/AuditConditions";

// features/settings
import Settings        from "./features/settings/Settings";
import UserManagement  from "./features/settings/UserManagement";

// features/admin
import TenantManagement    from "./features/admin/TenantManagement";
import WorkspaceRequests   from "./features/admin/WorkspaceRequests";

// features/stubs
import StubViewer from "./features/stubs/StubViewer";

// new domain pages
import ConnectorsPage    from "./features/connectors/ConnectorsPage";
import ReportsPage       from "./features/reports/ReportsPage";
import EvidencePage      from "./features/evidence/EvidencePage";
import DecisionProposals from "./features/reasoning/DecisionProposals";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const role = useAppSelector(state => state.auth.role);
  return role ? <>{children}</> : <Navigate to="/login" replace />;
}

function RequireRole({ allowed, children }: { allowed: string[]; children: React.ReactNode }) {
  const role = useAppSelector(state => state.auth.role) ?? "";
  return allowed.includes(role) ? <>{children}</> : <Navigate to="/" replace />;
}

const API_BASE = (import.meta.env.VITE_API_BASE || "/api") + "/v1";

export default function App() {
  const dispatch  = useAppDispatch();
  const role      = useAppSelector(state => state.auth.role);
  const meCalled  = useRef(false);

  // On page reload, localStorage has tenant/role/user/sub but not the JWT (it's in an HttpOnly
  // cookie). If localStorage was cleared but the cookie is still valid, this restores the session.
  useEffect(() => {
    if (meCalled.current || role) return;
    meCalled.current = true;
    axios
      .get(`${API_BASE}/auth/me`, { withCredentials: true })
      .then(({ data }) => {
        dispatch(loginAction({
          token:    "__cookie__",
          tenantId: data.tenant_id,
          role:     data.role,
          user:     data.full_name,
          sub:      data.email,
        }));
      })
      .catch(() => { /* not logged in — stay on login page */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
    <Toaster />
    <Routes>
      <Route path="/login"                    element={<Login />} />
      <Route path="/auth/google/callback"     element={<GoogleCallback />} />
      <Route path="/forgot-password"          element={<ForgotPassword />} />
      <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
        {/* Dashboard */}
        <Route path="/"                  element={<Home />} />
        <Route path="/analytics"         element={<Analytics />} />
        <Route path="/performance"       element={<Performance />} />

        {/* Audit */}
        <Route path="/audit-conditions"  element={<AuditConditions />} />

        {/* Payment & Rate */}
        <Route path="/payment-control"   element={<PaymentControl />} />
        <Route path="/rate-control"      element={<RateControl />} />
        <Route path="/carriers"          element={<CarriersPage />} />

        {/* Cases */}
        <Route path="/cases"     element={<Cases />} />
        <Route path="/cases/new" element={<NewCase />} />
        <Route path="/cases/:id" element={<CaseDetail />} />

        {/* Governance — role-gated */}
        <Route path="/analyst" element={
          <RequireRole allowed={["analyst","admin"]}>
            <AnalystReview />
          </RequireRole>
        } />
        <Route path="/manager" element={
          <RequireRole allowed={["manager","admin"]}>
            <ManagerApproval />
          </RequireRole>
        } />
        <Route path="/execute" element={
          <RequireRole allowed={["manager","admin"]}>
            <ExecuteRecovery />
          </RequireRole>
        } />

        {/* ACR */}
        <Route path="/crypto"    element={<CryptoAudit />} />
        <Route path="/verifier"  element={<AcrVerifier />} />

        {/* Audit */}
        <Route path="/alerts"    element={<Alerts />} />
        <Route path="/database"  element={
          <RequireRole allowed={["admin"]}>
            <DatabasePage />
          </RequireRole>
        } />
        <Route path="/kafka"     element={<KafkaEvents />} />

        {/* Settings */}
        <Route path="/settings"  element={<Settings />} />
        <Route path="/users"     element={
          <RequireRole allowed={["admin"]}>
            <UserManagement />
          </RequireRole>
        } />
        <Route path="/tenants"   element={
          <RequireRole allowed={["admin"]}>
            <TenantManagement />
          </RequireRole>
        } />
        <Route path="/workspace-requests" element={
          <RequireRole allowed={["admin"]}>
            <WorkspaceRequests />
          </RequireRole>
        } />

        {/* Connectors */}
        <Route path="/connectors" element={<ConnectorsPage />} />

        {/* Reports */}
        <Route path="/reports" element={<ReportsPage />} />

        {/* Evidence & Reasoning (case sub-pages) */}
        <Route path="/cases/:id/evidence"  element={<EvidencePage />} />
        <Route path="/cases/:id/reasoning" element={<DecisionProposals />} />

        {/* Dev/test stubs — admin only */}
        <Route path="/stubs"     element={
          <RequireRole allowed={["admin"]}>
            <StubViewer />
          </RequireRole>
        } />
      </Route>

      {/* Catch-all → login page */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
    </>
  );
}

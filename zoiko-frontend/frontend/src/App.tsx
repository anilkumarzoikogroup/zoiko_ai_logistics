import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import { Toaster } from "@/components/ui/toast";
import { useAppSelector } from "@/store";

// auth
import Login from "./auth/Login";

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
import TenantManagement from "./features/admin/TenantManagement";

// features/stubs
import StubViewer from "./features/stubs/StubViewer";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const role = useAppSelector(state => state.auth.role);
  return role ? <>{children}</> : <Navigate to="/login" replace />;
}

// Redirect root / → /login (not logged in) or /dashboard (logged in)
function RootRedirect() {
  const role = useAppSelector(state => state.auth.role);
  return role ? <Navigate to="/" replace /> : <Navigate to="/login" replace />;
}

function RequireRole({ allowed, children }: { allowed: string[]; children: React.ReactNode }) {
  const role = useAppSelector(state => state.auth.role) ?? "";
  return allowed.includes(role) ? <>{children}</> : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <>
    <Toaster />
    <Routes>
      <Route path="/login" element={<Login />} />
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

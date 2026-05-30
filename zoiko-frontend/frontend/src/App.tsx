import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import { Toaster } from "@/components/ui/toast";

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

function RequireAuth({ children }: { children: React.ReactNode }) {
  const role = localStorage.getItem("zoiko_role");
  return role ? <>{children}</> : <Navigate to="/login" replace />;
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
        <Route path="/execute"   element={<ExecuteRecovery />} />

        {/* Governance */}
        <Route path="/analyst"   element={<AnalystReview />} />
        <Route path="/manager"   element={<ManagerApproval />} />

        {/* ACR */}
        <Route path="/crypto"    element={<CryptoAudit />} />
        <Route path="/verifier"  element={<AcrVerifier />} />

        {/* Audit */}
        <Route path="/alerts"    element={<Alerts />} />
        <Route path="/database"  element={<DatabasePage />} />
        <Route path="/kafka"     element={<KafkaEvents />} />

        {/* Settings */}
        <Route path="/settings"       element={<Settings />} />
        <Route path="/users"          element={<UserManagement />} />
      </Route>
    </Routes>
    </>
  );
}

import { Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useRef, Suspense, lazy } from "react";
import AppLayout from "./layouts/AppLayout";
import { Toaster } from "@/components/ui/toast";
import { useAppSelector, useAppDispatch } from "@/store";
import { login as loginAction } from "@/store/authSlice";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import axios from "axios";

// auth — kept eager (needed immediately on every load)
import Login          from "./auth/Login";
import GoogleCallback from "./auth/GoogleCallback";
import ForgotPassword from "./auth/ForgotPassword";

// All feature pages — lazy loaded to reduce initial bundle
const Home           = lazy(() => import("./features/dashboard/Home"));
const Analytics      = lazy(() => import("./features/dashboard/Analytics"));
const Performance    = lazy(() => import("./features/dashboard/Performance"));
const Cases          = lazy(() => import("./features/cases/Cases"));
const NewCase        = lazy(() => import("./features/cases/NewCase"));
const CaseDetail     = lazy(() => import("./features/cases/CaseDetail"));
const Claims         = lazy(() => import("./features/claims/Claims"));
const NewClaim       = lazy(() => import("./features/claims/NewClaim"));
const ClaimDetail    = lazy(() => import("./features/claims/ClaimDetail"));
const ExecuteRecovery= lazy(() => import("./features/cases/ExecuteRecovery"));
const PaymentControl = lazy(() => import("./features/cases/PaymentControl"));
const CarriersPage   = lazy(() => import("./features/carriers/CarriersPage"));
const ConnectorsPage = lazy(() => import("./features/connectors/ConnectorsPage"));
const RateControl    = lazy(() => import("./features/cases/RateControl"));
const AnalystReview  = lazy(() => import("./features/governance/AnalystReview"));
const ManagerApproval= lazy(() => import("./features/governance/ManagerApproval"));
const CryptoAudit    = lazy(() => import("./features/acr/CryptoAudit"));
const AcrVerifier    = lazy(() => import("./features/acr/AcrVerifier"));
const Alerts         = lazy(() => import("./features/audit/Alerts"));
const DatabasePage   = lazy(() => import("./features/audit/DatabasePage"));
const KafkaEvents    = lazy(() => import("./features/audit/KafkaEvents"));
const AuditConditions= lazy(() => import("./features/audit/AuditConditions"));
const Settings       = lazy(() => import("./features/settings/Settings"));
const UserManagement = lazy(() => import("./features/settings/UserManagement"));
const TenantManagement   = lazy(() => import("./features/admin/TenantManagement"));
const WorkspaceRequests  = lazy(() => import("./features/admin/WorkspaceRequests"));
const StubViewer         = lazy(() => import("./features/stubs/StubViewer"));
const DataGovernance = lazy(() => import("./features/compliance/DataGovernance"));
const LegalHolds     = lazy(() => import("./features/compliance/LegalHolds"));
const DataRetention  = lazy(() => import("./features/compliance/DataRetention"));
const CryptoShred    = lazy(() => import("./features/compliance/CryptoShred"));
const RestoreJobs    = lazy(() => import("./features/compliance/RestoreJobs"));
const ArchiveJobs    = lazy(() => import("./features/compliance/ArchiveJobs"));
const PurgeJobs      = lazy(() => import("./features/compliance/PurgeJobs"));
const RecoveryDashboard = lazy(() => import("./features/recovery/RecoveryDashboard"));
const ReconciliationPage= lazy(() => import("./features/reconciliation/ReconciliationPage"));
const Exceptions        = lazy(() => import("./features/exceptions/Exceptions"));
const NewException      = lazy(() => import("./features/exceptions/NewException"));
const ExceptionDetail   = lazy(() => import("./features/exceptions/ExceptionDetail"));
const ScorecardList     = lazy(() => import("./features/scorecards/ScorecardList"));
const ComputeScorecard  = lazy(() => import("./features/scorecards/ComputeScorecard"));
const ScorecardDetail   = lazy(() => import("./features/scorecards/ScorecardDetail"));
const AccessorialList   = lazy(() => import("./features/accessorial/AccessorialList"));
const NewAccessorial    = lazy(() => import("./features/accessorial/NewAccessorial"));
const AccessorialDetail = lazy(() => import("./features/accessorial/AccessorialDetail"));

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[320px]">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
        <p className="text-xs text-slate-400">Loading…</p>
      </div>
    </div>
  );
}

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
    <ErrorBoundary>
    <Suspense fallback={<PageLoader />}>
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
        <Route path="/connectors"        element={<ConnectorsPage />} />

        {/* Cases */}
        <Route path="/cases"     element={<Cases />} />
        <Route path="/cases/new" element={<NewCase />} />
        <Route path="/cases/:id" element={<CaseDetail />} />

        {/* Claims (SC-002) */}
        <Route path="/claims"     element={<Claims />} />
        <Route path="/claims/new" element={<NewClaim />} />
        <Route path="/claims/:id" element={<ClaimDetail />} />

        {/* Shipment Exceptions (SC-003) */}
        <Route path="/exceptions"     element={<Exceptions />} />
        <Route path="/exceptions/new" element={<NewException />} />
        <Route path="/exceptions/:id" element={<ExceptionDetail />} />

        {/* SC-004 Supplier Performance Scorecards */}
        <Route path="/scorecards"     element={<ScorecardList />} />
        <Route path="/scorecards/new" element={<ComputeScorecard />} />
        <Route path="/scorecards/:id" element={<ScorecardDetail />} />

        {/* SC-005 Accessorial Charges */}
        <Route path="/accessorial"      element={<Suspense fallback={<PageLoader/>}><AccessorialList/></Suspense>} />
        <Route path="/accessorial/new"  element={<Suspense fallback={<PageLoader/>}><NewAccessorial/></Suspense>} />
        <Route path="/accessorial/:id"  element={<Suspense fallback={<PageLoader/>}><AccessorialDetail/></Suspense>} />

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

        {/* Phase 6 — Recovery pipeline */}
        <Route path="/recovery"        element={<RecoveryDashboard />} />
        <Route path="/reconciliation"  element={
          <RequireRole allowed={["manager","admin"]}>
            <ReconciliationPage />
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

        {/* Dev/test stubs — admin only */}
        <Route path="/stubs"     element={
          <RequireRole allowed={["admin"]}>
            <StubViewer />
          </RequireRole>
        } />

        {/* C07 — Data Governance (admin only) */}
        <Route path="/governance/data"    element={<DataGovernance />} />
        <Route path="/governance/holds"   element={<LegalHolds />} />
        <Route path="/governance/retention" element={<DataRetention />} />
        <Route path="/governance/crypto-shred" element={<CryptoShred />} />
        <Route path="/governance/restore" element={<RestoreJobs />} />
        <Route path="/governance/archive" element={<ArchiveJobs />} />
        <Route path="/governance/purge"   element={<PurgeJobs />} />
      </Route>

      {/* Catch-all → login page */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
    </Suspense>
    </ErrorBoundary>
    </>
  );
}

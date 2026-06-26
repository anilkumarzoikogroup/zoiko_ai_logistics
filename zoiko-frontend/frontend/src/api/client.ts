import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { generateIdempotencyKey } from "@/utils/cn";
import { store } from "@/store";
import { logout } from "@/store/authSlice";
import { queryClient } from "@/lib/queryClient";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

// Bare axios instance used ONLY for session verification — no interceptors attached,
// so a 401 from /auth/me never recurses back into the error handler below.
const _sessionVerifier = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE || "/api") + "/v1",
  withCredentials: true,
  timeout: 5000,
});

// Dedup: if 10 parallel queries all return 401 at once we only run one check.
let _verifyInFlight = false;

function _handleUnauthorized(): void {
  if (_verifyInFlight) return;
  _verifyInFlight = true;
  // Build auth headers the same way the normal instances do.
  const devJwt = import.meta.env.VITE_DEV_JWT;
  const tenant  = store.getState().auth.tenantId
    || localStorage.getItem("zoiko_tenant")
    || import.meta.env.VITE_DEV_TENANT
    || "";
  const verifyHeaders: Record<string, string> = {};
  if (devJwt)  verifyHeaders["Authorization"] = `Bearer ${devJwt}`;
  if (tenant)  verifyHeaders["X-Tenant-ID"]   = tenant;

  _sessionVerifier.get("/auth/me", { headers: verifyHeaders })
    .then(() => {
      // /auth/me succeeded → the session is still valid.
      // The original 401 was from a supplementary data endpoint whose data
      // doesn't exist yet for this case state — not a session expiry. Don't logout.
    })
    .catch((verifyErr: AxiosError) => {
      if (verifyErr.response?.status === 401) {
        // /auth/me also returned 401 → session is truly expired.
        store.dispatch(logout());
        queryClient.clear();
        window.location.href = "/login";
      }
      // Any other error (network, 5xx) → assume session is still valid, do nothing.
    })
    .finally(() => { _verifyInFlight = false; });
}

// Log mode clearly so it's always visible in DevTools console
if (USE_MOCK) {
  console.warn("[Zoiko] MOCK MODE — data is not real. Set VITE_USE_MOCK=false and restart npm run dev.");
} else {
  console.info("[Zoiko] LIVE MODE — connected to real backend.");
}

// Spec §9.2: all routes are under /v1/. Proxy in vite.config.ts rewrites /api → ""
// so /api/v1/cases becomes /v1/cases at the backend.
const API_BASE  = (import.meta.env.VITE_API_BASE  || "/api")  + "/v1";
const API3_BASE = (import.meta.env.VITE_API3_BASE || "/api3") + "/v1"; // Phase 3 port 8002
const API4_BASE = (import.meta.env.VITE_API4_BASE || "/api4") + "/v1"; // Phase 4 port 8001

// SC-002 (carrier claim) spine — a fully separate gateway/execution/governance
// backend (backend/slices/sc-002-carrier-claim/spine/), not a route on the
// SC-001 backend above. Claims must go through these, not api/api3/api4.
const API_CLAIM_BASE  = (import.meta.env.VITE_API_CLAIM_BASE  || "/claimapi")  + "/v1"; // SC-002 gateway port 8010
const API_CLAIM3_BASE = (import.meta.env.VITE_API_CLAIM3_BASE || "/claimapi3") + "/v1"; // SC-002 governance port 8012
const API_CLAIM4_BASE = (import.meta.env.VITE_API_CLAIM4_BASE || "/claimapi4") + "/v1"; // SC-002 execution port 8011

// JWT lives in an HttpOnly cookie — the browser sends it automatically on every request.
// We only need to attach X-Tenant-ID (non-sensitive) and, in dev-only, VITE_DEV_JWT.
function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  // Dev override: allow VITE_DEV_JWT to bypass cookie auth (local testing without a browser cookie)
  const devJwt = import.meta.env.VITE_DEV_JWT;
  if (devJwt) headers["Authorization"] = `Bearer ${devJwt}`;
  // Tenant ID is not secret — safe to keep in localStorage for X-Tenant-ID header
  const tenant = store.getState().auth.tenantId
    || localStorage.getItem("zoiko_tenant")
    || import.meta.env.VITE_DEV_TENANT
    || "";
  if (tenant) headers["X-Tenant-ID"] = tenant;
  return headers;
}

function attachInterceptors(instance: AxiosInstance): AxiosInstance {
  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const authHeaders = getAuthHeaders();
    Object.entries(authHeaders).forEach(([k, v]) => { config.headers.set(k, v); });
    const method = config.method?.toUpperCase();
    if (method && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      if (!config.headers.get("Idempotency-Key")) {
        config.headers.set("Idempotency-Key", generateIdempotencyKey());
      }
    }
    return config;
  });

  instance.interceptors.response.use(
    (r) => r,
    (error: AxiosError) => {
      const status = error.response?.status;
      if (status === 401) {
        // Don't logout immediately — verify the session first.
        // CaseDetail fires ~10 parallel queries; some endpoints legitimately
        // return 401 when the case hasn't reached that pipeline stage yet
        // (e.g. no token issued, no variances). Logging out on those is wrong.
        // _handleUnauthorized() calls /auth/me on a bare axios instance:
        //   • In DEV_MODE the backend bypasses JWT → /auth/me succeeds → no logout.
        //   • In production an expired token fails /auth/me too → logout correctly.
        _handleUnauthorized();
      }
      if (status === 503) console.warn("503 — OPA unreachable (fail-closed)");
      return Promise.reject(error);
    }
  );

  return instance;
}

// withCredentials=true is required for the browser to send the HttpOnly auth cookie cross-origin
// (dev: frontend :5173 → backend :8000 via Vite proxy; production: same origin, always works)
const api  = attachInterceptors(axios.create({ baseURL: API_BASE,  timeout: 60000, withCredentials: true }));
const api3 = attachInterceptors(axios.create({ baseURL: API3_BASE, timeout: 60000, withCredentials: true }));
const api4 = attachInterceptors(axios.create({ baseURL: API4_BASE, timeout: 60000, withCredentials: true }));

const apiClaim  = attachInterceptors(axios.create({ baseURL: API_CLAIM_BASE,  timeout: 60000, withCredentials: true }));
const apiClaim3 = attachInterceptors(axios.create({ baseURL: API_CLAIM3_BASE, timeout: 60000, withCredentials: true }));
const apiClaim4 = attachInterceptors(axios.create({ baseURL: API_CLAIM4_BASE, timeout: 60000, withCredentials: true }));

// SC-003 (shipment exception) spine — gateway port 8020, execution port 8021
const API_EXC_BASE  = (import.meta.env.VITE_API_EXC_BASE  || "/excapi")  + "/v1"; // SC-003 gateway port 8020
const API_EXC4_BASE = (import.meta.env.VITE_API_EXC4_BASE || "/excapi4") + "/v1"; // SC-003 execution port 8021

const apiException  = attachInterceptors(axios.create({ baseURL: API_EXC_BASE,  timeout: 90000, withCredentials: true }));
const apiException4 = attachInterceptors(axios.create({ baseURL: API_EXC4_BASE, timeout: 60000, withCredentials: true }));

// SC-004 (supplier scorecard) spine — gateway port 8030
const API_SCORE_BASE = (import.meta.env.VITE_API_SCORE_BASE || "/scoreapi") + "/v1";
const apiScore = attachInterceptors(axios.create({ baseURL: API_SCORE_BASE, timeout: 90000, withCredentials: true }));

export { api, api3, api4, apiClaim, apiClaim3, apiClaim4, apiException, apiException4, apiScore, USE_MOCK };

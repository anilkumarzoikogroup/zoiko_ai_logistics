import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { generateIdempotencyKey } from "@/utils/cn";
import { store } from "@/store";
import { logout } from "@/store/authSlice";
import { queryClient } from "@/lib/queryClient";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

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
        store.dispatch(logout());
        queryClient.clear();
        window.location.href = "/login";
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

export { api, api3, api4, apiClaim, apiClaim3, apiClaim4, USE_MOCK };

import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { generateIdempotencyKey } from "@/utils/cn";

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

// JWT + tenant come from auth store (set on login)
function getAuthHeaders(): Record<string, string> {
  const token  = localStorage.getItem("zoiko_jwt")    || import.meta.env.VITE_DEV_JWT    || "";
  const tenant = localStorage.getItem("zoiko_tenant") || import.meta.env.VITE_DEV_TENANT || "";
  const headers: Record<string, string> = {};
  if (token)  headers["Authorization"] = `Bearer ${token}`;
  if (tenant) headers["X-Tenant-ID"]   = tenant;
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
      if (status === 401) console.warn("401 — JWT invalid or expired");
      if (status === 503) console.warn("503 — OPA unreachable (fail-closed)");
      return Promise.reject(error);
    }
  );

  return instance;
}

const api  = attachInterceptors(axios.create({ baseURL: API_BASE,  timeout: 60000 }));  // 60s for Neon cold starts
const api3 = attachInterceptors(axios.create({ baseURL: API3_BASE, timeout: 60000 }));
const api4 = attachInterceptors(axios.create({ baseURL: API4_BASE, timeout: 60000 }));

export { api, api3, api4, USE_MOCK };

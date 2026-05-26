import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { generateIdempotencyKey } from "@/utils/cn";

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";
// Spec §9.2: all routes are under /v1/. Proxy in vite.config.ts rewrites /api → ""
// so /api/v1/cases becomes /v1/cases at the backend.
const API_BASE = (import.meta.env.VITE_API_BASE || "/api") + "/v1";

// JWT + tenant come from auth store (or env for dev)
function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("zoiko_jwt") || import.meta.env.VITE_DEV_JWT || "";
  const tenant = localStorage.getItem("zoiko_tenant") || import.meta.env.VITE_DEV_TENANT || "amazon-india";
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (tenant) headers["X-Tenant-ID"] = tenant;
  return headers;
}

const api: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
});

// Request interceptor — adds auth, tenant, idempotency
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const authHeaders = getAuthHeaders();
  Object.entries(authHeaders).forEach(([k, v]) => {
    config.headers.set(k, v);
  });
  // Idempotency key for mutating verbs
  const method = config.method?.toUpperCase();
  if (method && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    if (!config.headers.get("Idempotency-Key")) {
      config.headers.set("Idempotency-Key", generateIdempotencyKey());
    }
  }
  return config;
});

// Response interceptor — normalize errors
api.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    const status = error.response?.status;
    if (status === 401) {
      // optional: redirect to login
      console.warn("401 — JWT invalid or expired");
    }
    if (status === 503) {
      console.warn("503 — OPA unreachable (fail-closed)");
    }
    return Promise.reject(error);
  }
);

export { api, USE_MOCK };

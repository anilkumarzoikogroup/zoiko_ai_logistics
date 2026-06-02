import { createSlice, PayloadAction } from "@reduxjs/toolkit";

interface AuthState {
  token:    string | null;
  tenantId: string | null;
  role:     string | null;
  user:     string | null;
  sub:      string | null;
}

// Decode a base64url string (JWT format) safely — handles missing padding and URL-safe chars
function _decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    // base64url → base64: replace URL-safe chars + add missing padding
    const b64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - b64.length % 4) % 4);
    return JSON.parse(atob(padded));
  } catch {
    return null;
  }
}

// Hydrate from localStorage — validate the token is not obviously expired
function _loadStoredAuth(): AuthState {
  const token = localStorage.getItem("zoiko_jwt");
  if (token) {
    const payload = _decodeJwtPayload(token);
    if (!payload) {
      // Malformed token — clear stored auth
      ["zoiko_jwt","zoiko_tenant","zoiko_role","zoiko_user","zoiko_sub"]
        .forEach(k => localStorage.removeItem(k));
      return { token: null, tenantId: null, role: null, user: null, sub: null };
    }
    if (payload.exp && typeof payload.exp === "number" && payload.exp * 1000 < Date.now()) {
      // Token expired — clear stored auth
      ["zoiko_jwt","zoiko_tenant","zoiko_role","zoiko_user","zoiko_sub"]
        .forEach(k => localStorage.removeItem(k));
      return { token: null, tenantId: null, role: null, user: null, sub: null };
    }
  }
  return {
    token,
    tenantId: localStorage.getItem("zoiko_tenant"),
    role:     localStorage.getItem("zoiko_role"),
    user:     localStorage.getItem("zoiko_user"),
    sub:      localStorage.getItem("zoiko_sub"),
  };
}

const stored: AuthState = _loadStoredAuth();

const authSlice = createSlice({
  name: "auth",
  initialState: stored,
  reducers: {
    login(state, action: PayloadAction<{
      token: string; tenantId: string; role: string; user: string; sub: string;
    }>) {
      const { token, tenantId, role, user, sub } = action.payload;
      state.token    = token;
      state.tenantId = tenantId;
      state.role     = role;
      state.user     = user;
      state.sub      = sub;
      // Persist to localStorage for page reloads
      localStorage.setItem("zoiko_jwt",    token);
      localStorage.setItem("zoiko_tenant", tenantId);
      localStorage.setItem("zoiko_role",   role);
      localStorage.setItem("zoiko_user",   user);
      localStorage.setItem("zoiko_sub",    sub);
    },
    logout(state) {
      state.token    = null;
      state.tenantId = null;
      state.role     = null;
      state.user     = null;
      state.sub      = null;
      localStorage.removeItem("zoiko_jwt");
      localStorage.removeItem("zoiko_tenant");
      localStorage.removeItem("zoiko_role");
      localStorage.removeItem("zoiko_user");
      localStorage.removeItem("zoiko_sub");
    },
    refreshToken(state, action: PayloadAction<string>) {
      state.token = action.payload;
      localStorage.setItem("zoiko_jwt", action.payload);
    },
  },
});

export const { login, logout, refreshToken } = authSlice.actions;
export default authSlice.reducer;

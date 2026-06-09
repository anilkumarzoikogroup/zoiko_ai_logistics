import { createSlice, PayloadAction } from "@reduxjs/toolkit";

interface AuthState {
  token:    string | null;
  tenantId: string | null;
  role:     string | null;
  user:     string | null;
  sub:      string | null;
}

// Hydrate non-sensitive fields from localStorage.
// The JWT is stored only in an HttpOnly cookie — JS cannot read it.
// On page reload token is null; API calls succeed via cookie automatically.
// If the cookie is expired, the first protected API call returns 401 and the
// interceptor in client.ts dispatches logout() → clears localStorage → /login.
function _loadStoredAuth(): AuthState {
  return {
    token:    null,  // never persisted to localStorage — lives in HttpOnly cookie
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
      // JWT goes only into HttpOnly cookie (set by backend) — never touch localStorage for it.
      // Non-sensitive display fields are persisted for page-reload hydration.
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
      // Cookie is cleared by calling POST /auth/signout (backend deletes it).
      // Clear the non-sensitive display fields from localStorage.
      localStorage.removeItem("zoiko_tenant");
      localStorage.removeItem("zoiko_role");
      localStorage.removeItem("zoiko_user");
      localStorage.removeItem("zoiko_sub");
    },
    refreshToken(state, action: PayloadAction<string>) {
      // Token is refreshed via cookie by the backend — just update in-memory state.
      state.token = action.payload;
    },
  },
});

export const { login, logout, refreshToken } = authSlice.actions;
export default authSlice.reducer;

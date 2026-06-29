import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Proxy targets are read from process.env at dev-server startup time (not baked
// into the client bundle).  Set BACKEND_* vars in docker-compose so the Vite
// dev server inside a container can reach sibling containers by service name.
// Defaults fall back to localhost for normal non-Docker development.
const BE = {
  gateway:    process.env.BACKEND_GATEWAY_URL    ?? "http://localhost:8000",
  exec:       process.env.BACKEND_EXEC_URL       ?? "http://localhost:8001",
  gov:        process.env.BACKEND_GOV_URL        ?? "http://localhost:8002",
  sc002gw:    process.env.BACKEND_SC002_GW_URL   ?? "http://localhost:8010",
  sc002exec:  process.env.BACKEND_SC002_EXEC_URL ?? "http://localhost:8011",
  sc002gov:   process.env.BACKEND_SC002_GOV_URL  ?? "http://localhost:8012",
  sc003gw:    process.env.BACKEND_SC003_GW_URL   ?? "http://localhost:8020",
  sc003exec:  process.env.BACKEND_SC003_EXEC_URL ?? "http://localhost:8021",
  sc004gw:    process.env.BACKEND_SC004_GW_URL   ?? "http://localhost:8030",
  sc004exec:  process.env.BACKEND_SC004_EXEC_URL ?? "http://localhost:8031",
  sc005gw:    process.env.BACKEND_SC005_GW_URL   ?? "http://localhost:8040",
  sc005exec:  process.env.BACKEND_SC005_EXEC_URL ?? "http://localhost:8041",
};

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    // Vite matches proxy contexts in object-key order using plain `url.startsWith(context)`
    // and stops at the first hit (see doesProxyContextMatchUrl in vite/dist/node — it's a
    // for-loop with an early return, not longest-prefix-match). That means longer/more
    // specific prefixes MUST be listed before their shorter stems, or they're unreachable
    // dead code (e.g. "/api3" would otherwise always be caught by "/api" first).
    proxy: {
      // SC-001 — main gateway / governance / execution
      "/api3": {
        target: BE.gov,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api3/, ""),
      },
      "/api4": {
        target: BE.exec,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api4/, ""),
      },
      "/api": {
        target: BE.gateway,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
        proxyTimeout: 90000,  // 90s — covers the ~22s cloud-DB pipeline
        timeout: 90000,
      },
      // SC-002 (carrier claim) spine — independent gateway/execution/governance
      // processes on their own ports, per backend/slices/sc-002-carrier-claim/spine/.
      // Longer prefixes ("/claimapi3", "/claimapi4") must precede the shorter
      // "/claimapi" stem for the same reason as above.
      "/claimapi3": {
        target: BE.sc002gov,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/claimapi3/, ""),
      },
      "/claimapi4": {
        target: BE.sc002exec,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/claimapi4/, ""),
      },
      "/claimapi": {
        target: BE.sc002gw,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/claimapi/, ""),
        proxyTimeout: 90000,
        timeout: 90000,
      },
      // SC-003 (shipment exception) spine — gateway port 8020, execution port 8021.
      // Longer prefix "/excapi4" must precede "/excapi" stem.
      "/excapi4": {
        target: BE.sc003exec,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/excapi4/, ""),
      },
      "/excapi": {
        target: BE.sc003gw,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/excapi/, ""),
        proxyTimeout: 90000,
        timeout: 90000,
      },
      // SC-004 (supplier scorecard) spine — gateway port 8030, execution port 8031.
      // Longer prefix "/scoreapi4" must precede "/scoreapi" stem.
      "/scoreapi4": {
        target: BE.sc004exec,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/scoreapi4/, ""),
      },
      "/scoreapi": {
        target: BE.sc004gw,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/scoreapi/, ""),
        proxyTimeout: 90000,
        timeout: 90000,
      },
      // SC-005 (accessorial charge dispute) spine — gateway port 8040, execution port 8041.
      // Longer prefix "/accapi4" must precede "/accapi" stem.
      "/accapi4": {
        target: BE.sc005exec,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/accapi4/, ""),
      },
      "/accapi": {
        target: BE.sc005gw,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/accapi/, ""),
        proxyTimeout: 90000,
        timeout: 90000,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react":   ["react", "react-dom", "react-router-dom"],
          "vendor-query":   ["@tanstack/react-query"],
          "vendor-charts":  ["recharts"],
          "vendor-ui":      ["lucide-react", "clsx", "tailwind-merge", "class-variance-authority"],
          "vendor-zustand": ["zustand"],
          "vendor-axios":   ["axios"],
        },
      },
    },
  },
});

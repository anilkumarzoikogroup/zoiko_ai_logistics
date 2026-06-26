import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

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
      "/api3": {
        target: "http://localhost:8002",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api3/, ""),
      },
      "/api4": {
        target: "http://localhost:8001",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api4/, ""),
      },
      "/api": {
        target: "http://localhost:8000",
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
        target: "http://localhost:8012",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/claimapi3/, ""),
      },
      "/claimapi4": {
        target: "http://localhost:8011",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/claimapi4/, ""),
      },
      "/claimapi": {
        target: "http://localhost:8010",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/claimapi/, ""),
        proxyTimeout: 90000,
        timeout: 90000,
      },
      // SC-003 (shipment exception) spine — gateway port 8020, execution port 8021.
      // Longer prefix "/excapi4" must precede "/excapi" stem.
      "/excapi4": {
        target: "http://localhost:8021",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/excapi4/, ""),
      },
      "/excapi": {
        target: "http://localhost:8020",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/excapi/, ""),
        proxyTimeout: 90000,
        timeout: 90000,
      },
      // SC-004 (supplier scorecard) spine — gateway port 8030.
      "/scoreapi": {
        target: "http://localhost:8030",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/scoreapi/, ""),
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

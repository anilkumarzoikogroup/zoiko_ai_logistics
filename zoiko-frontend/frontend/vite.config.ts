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
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
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

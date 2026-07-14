import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Integration Phase 2 — two backends, two explicit, non-overlapping proxy
// prefixes (no ambiguous shared `/api`):
//   /executive-api/*  -> executive-ui/api/server.py  (port 8000, read-only dashboard)
//   /copilot-api/*    -> copilot-backend/server.py   (port 8010, conversational)
// Both dev-time ports are overridable via EXECUTIVE_API_PORT/COPILOT_API_PORT
// so this matches whatever `python3 executive-ui/api/server.py --port …` /
// `python3 copilot-backend/server.py` are actually bound to locally. In
// production the frontend instead uses absolute base URLs configured via
// VITE_EXECUTIVE_API_BASE_URL / VITE_COPILOT_API_BASE_URL (see lib/api.ts,
// lib/copilotApi.ts) — this proxy is dev-server-only.
const EXECUTIVE_API_PORT = process.env.EXECUTIVE_API_PORT || "8000";
const COPILOT_API_PORT = process.env.COPILOT_API_PORT || "8010";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/executive-api": {
        target: `http://127.0.0.1:${EXECUTIVE_API_PORT}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/executive-api/, "/api"),
      },
      "/copilot-api": {
        target: `http://127.0.0.1:${COPILOT_API_PORT}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/copilot-api/, "/api"),
      },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});

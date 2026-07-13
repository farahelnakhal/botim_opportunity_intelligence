import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the read-only Python engine API so the
// front-end and back-end can run on separate ports during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});

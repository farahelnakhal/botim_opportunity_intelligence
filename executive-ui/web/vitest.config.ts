import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Separate from vite.config.ts (dev server) so `npm run build`/`npm run dev`
// never pull in test-only deps; `npm test` uses this config explicitly.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    css: false,
  },
});

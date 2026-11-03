/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.KWELI_API_PROXY ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  // AG Grid core is ~210 kB gzipped and only loads with the ledger, after sign-in.
  build: { chunkSizeWarningLimit: 800 },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/v1": { target: api, changeOrigin: false } },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});

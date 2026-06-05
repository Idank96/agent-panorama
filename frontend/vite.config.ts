/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Ship the dashboard inside the Python package so `agent-panorama serve`
  // can serve it without Node installed.
  build: {
    outDir: "../src/agent_panorama/static",
    emptyOutDir: true,
  },
  // In dev, proxy API calls to a locally running `agent-panorama serve`.
  server: {
    proxy: {
      "/api": "http://localhost:8321",
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});

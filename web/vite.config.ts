import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Where the API server runs during development (override when it's elsewhere).
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/v1": apiTarget,
      "/healthz": apiTarget,
    },
  },
  preview: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/v1": apiTarget,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});

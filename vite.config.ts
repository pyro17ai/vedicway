/// <reference types="vitest/config" />

import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8005",
          changeOrigin: true,
        },
        "/media": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8005",
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      include: ["src/**/*.{test,spec}.{ts,tsx}"],
      setupFiles: "./src/test/setup.ts",
      restoreMocks: true,
    },
  };
});

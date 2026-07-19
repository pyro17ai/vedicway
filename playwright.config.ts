import { defineConfig, devices } from "playwright/test";
import { join } from "node:path";
import { tmpdir } from "node:os";

const backendPort = 8015;
const frontendPort = 5183;
const frontendOrigin = `http://127.0.0.1:${frontendPort}`;
const python = process.env.VEDICWAY_E2E_PYTHON ?? "python";
const dataDir = join(tmpdir(), `vedicway-yookassa-e2e-${process.pid}`);

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 45_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  // Локальный BFF ограничивает bursts по IP; эти сценарии намеренно делят один стенд.
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "artifacts/playwright-report" }]],
  webServer: [
    {
      command: `"${python}" -m uvicorn vedicway_backend.main:app --app-dir backend/src --host 127.0.0.1 --port ${backendPort}`,
      url: `http://127.0.0.1:${backendPort}/api/v1/health/ready`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        VEDICWAY_DATA_DIR: dataDir,
        VEDICWAY_ENV: "development",
        VEDICWAY_TEST_PAYMENTS: "1",
        VEDICWAY_PUBLIC_BASE_URL: frontendOrigin,
        VEDICWAY_OFFER_VERSION: "development",
        VEDICWAY_OFFER_URL: `${frontendOrigin}/legal/user-agreement`,
        VEDICWAY_PRIVACY_URL: `${frontendOrigin}/legal/privacy-policy`,
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      url: frontendOrigin,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { ...process.env, VITE_API_PROXY_TARGET: `http://127.0.0.1:${backendPort}` },
    },
  ],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? frontendOrigin,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

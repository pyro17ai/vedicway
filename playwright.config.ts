import { defineConfig, devices } from "playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 45_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  // Локальный BFF ограничивает bursts по IP; эти сценарии намеренно делят один стенд.
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "artifacts/playwright-report" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

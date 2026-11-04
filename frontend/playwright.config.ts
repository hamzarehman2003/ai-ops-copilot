import { defineConfig, devices } from "@playwright/test";

// Smoke tests against a running dev server (npm run dev -> :3002) and the live API (:8001).
// Set PW_NO_SERVER=1 if you already have the dev server running.
export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3002",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.PW_NO_SERVER
    ? undefined
    : {
        command: "npm run dev",
        url: "http://localhost:3002",
        reuseExistingServer: true,
        timeout: 120_000,
      },
});

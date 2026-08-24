import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: ".playwright-artifacts/test-results",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [["html", { outputFolder: ".playwright-artifacts/report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  webServer: {
    command: "node node_modules/next/dist/bin/next dev --hostname 0.0.0.0",
    url: "http://127.0.0.1:3000/login",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ATLASMIND_NEXT_DIST_DIR: ".next-playwright",
      ATLASMIND_AUTH_MODE: "local",
      ATLASMIND_SESSION_SECRET: "playwright-local-session-secret-at-least-32-characters",
      ATLASMIND_API_URL: "http://127.0.0.1:8000",
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

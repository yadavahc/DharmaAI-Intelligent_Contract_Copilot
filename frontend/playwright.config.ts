import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the end-to-end journey.
 *
 * The web server is started by Playwright itself with `DHARMA_DEMO_MODE=true`
 * inherited from the environment, so the run needs no OpenAI key and cannot
 * flake on a rate limit. The backend must already be running — the README
 * documents both commands, and `e2e/dharma.spec.ts` fails with a clear message
 * if it is not reachable.
 */
export default defineConfig({
  testDir: "./e2e",
  // The journey test walks a real multi-agent pipeline; give it room.
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  // One worker: the test mutates shared backend state (it resets the database).
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],

  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],

  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "npm run start",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        stdout: "pipe",
        stderr: "pipe",
      },
});

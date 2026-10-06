import { defineConfig, devices } from "@playwright/test";

// Minimal smoke-E2E against an already-running `next dev` server (started
// separately with NEXT_PUBLIC_API_BASE_URL pointing at a local backend) -
// no webServer block, so it never tries to manage the Python API itself.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: "line",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-390", use: { viewport: { width: 390, height: 844 } } },
  ],
});

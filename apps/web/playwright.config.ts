import { defineConfig, devices } from "@playwright/test";

const PY = process.env.PYTHON ?? (process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python"); // relative to repo root (cwd below)
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 180_000,
  expect: { timeout: 120_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: { baseURL: "http://127.0.0.1:8000", trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" },
  projects: [
    { name: "desktop", testIgnore: /demo\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 5"] }, grep: /@mobile/ },
    { name: "demo", testMatch: /demo\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: `${PY} -m uvicorn apps.api.main:app --port 8000 --host 127.0.0.1`,
    cwd: "../..",
    url: "http://127.0.0.1:8000/health",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { GIGSIM_INPROCESS: "1", GIGSIM_ERROR_RATE: "0", MODEL_PROFILE: "offline", APP_DB: ":memory:", MEMORY_DB: ":memory:",
           CHECKPOINT_DB: "data/processed/e2e_checkpoints.sqlite", REVIEWER_PASSWORD: "reviewer-pass-123", REVIEWER_PERSONA: "fullstack_web_dev" },
  },
});

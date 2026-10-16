import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";
import { loadEnv } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
process.env.EAT_WHAT_BROWSER_RUN ??= "browser-" + Date.now().toString(36);
const execution = process.env.EAT_WHAT_BROWSER_RUN;
const frontend = loadEnv("test", here, "VITE_");
for (const name of ["VITE_AMAP_JS_KEY", "VITE_AMAP_SECURITY_CODE"]) {
  if (!frontend[name] || frontend[name].startsWith("replace-")) {
    throw new Error(
      "Configure real " +
        name +
        " in src/frontend/.env before live browser tests.",
    );
  }
}
process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve(
  here,
  "node_modules/.cache/ms-playwright",
);

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.live.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 10_000 },
  outputDir: "test-results/" + execution,
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results/" + execution + ".json" }],
  ],
  use: {
    baseURL: "http://localhost:15173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 900 },
      },
    },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], browserName: "chromium" },
    },
  ],
  webServer: [
    {
      command: ".venv/bin/python -B -m tests.serve",
      cwd: resolve(here, "../backend"),
      url: "http://localhost:18000/health/ready",
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
      timeout: 60_000,
      env: { PYTHONDONTWRITEBYTECODE: "1" },
    },
    {
      command:
        "node node_modules/vite/bin/vite.js --host localhost --port 15173 --strictPort --mode test",
      cwd: here,
      url: "http://localhost:15173/login",
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_API_BASE_URL: "http://localhost:18000" },
    },
  ],
});

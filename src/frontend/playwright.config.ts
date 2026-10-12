import { defineConfig, devices } from "@playwright/test";
const port = Number(process.env.E2E_PORT ?? "5173");
const mockedServiceEnv: Record<string, string> | undefined = process.env.FOOD_LIVE_TESTS === "1" ? undefined : {
  VITE_API_BASE_URL: process.env.VITE_API_BASE_URL ?? "http://localhost:8000",
  VITE_AMAP_JS_KEY: process.env.VITE_AMAP_JS_KEY ?? "playwright-test-key",
  VITE_AMAP_SECURITY_CODE: process.env.VITE_AMAP_SECURITY_CODE ?? "playwright-test-code",
};
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  use: { baseURL: `http://localhost:${port}`, trace: "retain-on-failure" },
  webServer: {
    command: `corepack pnpm dev --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: !process.env.CI,
    env: mockedServiceEnv,
  },
  projects: [
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
  ],
});

import { mergeConfig } from "vite";
import { defineConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      include: ["tests/**/*.test.{ts,tsx}"],
      setupFiles: ["./tests/setup.ts"],
      restoreMocks: true,
      clearMocks: true,
      reporters: ["default", "junit"],
      outputFile: { junit: "test-results/unit.xml" },
      env: {
        VITE_API_BASE_URL: "https://localhost:18000",
        VITE_AMAP_JS_KEY: "test-map-key",
        VITE_AMAP_SECURITY_CODE: "test-security-code",
      },
    },
  }),
);

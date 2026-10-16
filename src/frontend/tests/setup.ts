import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { setCsrfToken, setUnauthorizedHandler } from "../src/lib/api";
import { useDraft } from "../src/lib/store";

beforeEach(() => {
  sessionStorage.clear();
  useDraft.getState().reset();
  setCsrfToken(null);
  setUnauthorizedHandler(null);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

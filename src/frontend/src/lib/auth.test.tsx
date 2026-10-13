import { createElement, type ReactNode } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./auth";
import { request, setCsrfToken } from "./api";
import { useDraft } from "./store";

vi.mock("./api", () => ({
  configError: null,
  endpoint: (path: string) => path,
  request: vi.fn(),
  setCsrfToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.resetAllMocks();
  sessionStorage.clear();
  useDraft.getState().reset();
});

async function signedIn() {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    success: true,
    data: {
      user: { id: "alice", username: "alice", displayName: "Alice", createdAt: "2026-01-01" },
      csrfToken: "old-csrf",
    },
  }))));
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => createElement(
    QueryClientProvider, { client }, createElement(AuthProvider, null, children),
  );
  const hook = renderHook(() => useAuth(), { wrapper });
  await waitFor(() => expect(hook.result.current.state).toBe("authenticated"));
  client.setQueryData(["private-data"], { owner: "alice" });
  sessionStorage.setItem("food-start", "private-draft");
  useDraft.getState().setRunId("private-run");
  return { ...hook, client };
}

it("clears the session and private state after changing the password", async () => {
  const { result, client } = await signedIn();
  vi.mocked(request).mockResolvedValue({ loggedOut: true });

  await act(() => result.current.changePassword("old-password", "new-password"));

  expect(request).toHaveBeenCalledWith("/auth/change-password", {
    currentPassword: "old-password", newPassword: "new-password",
  });
  expect(result.current.state).toBe("anonymous");
  expect(result.current.user).toBeNull();
  expect(setCsrfToken).toHaveBeenLastCalledWith(null);
  expect(client.getQueryData(["private-data"])).toBeUndefined();
  expect(sessionStorage.getItem("food-start")).toBeNull();
  expect(useDraft.getState().runId).toBeNull();
});

it.each(["INVALID_CREDENTIALS", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE"])(
  "keeps the current session when the password change fails with %s", async (code) => {
    const { result, client } = await signedIn();
    vi.mocked(request).mockRejectedValue(new Error(code));

    await act(async () => {
      await expect(result.current.changePassword("old-password", "new-password")).rejects.toThrow(code);
    });

    expect(result.current.state).toBe("authenticated");
    expect(result.current.user?.id).toBe("alice");
    expect(setCsrfToken).toHaveBeenLastCalledWith("old-csrf");
    expect(client.getQueryData(["private-data"])).toEqual({ owner: "alice" });
    expect(useDraft.getState().runId).toBe("private-run");
  },
);

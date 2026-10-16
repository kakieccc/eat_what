import { act, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { getCsrfToken, handleUnauthorized } from "../src/lib/api";
import { defaults } from "../src/lib/schemas";
import { useDraft } from "../src/lib/store";

const user = {
  id: "user-a",
  username: "alpha",
  displayName: "甲",
  createdAt: "2026-10-16T00:00:00Z",
};
const signed = { user, csrfToken: "csrf-a" };
const draft = {
  ownerId: user.id,
  hasDraft: true,
  origin: { latitude: 31.3, longitude: 121.5, address: "出发位置" },
  preferences: { ...defaults, excludedFoods: ["火锅"], requestText: "清淡一点" },
  runId: "current-run",
};

function response(data: unknown, status = 200) {
  return new Response(JSON.stringify({ success: status === 200, data }), { status });
}

function Harness() {
  const auth = useAuth();
  return <>
    <p>{auth.state}</p>
    <p>{auth.user?.username}</p>
    <button onClick={() => void auth.retrySession()}>retry</button>
    <button onClick={() => void auth.logout()}>logout</button>
    <button onClick={() => void auth.login("beta", "password")}>login</button>
    <button onClick={() => void auth.register("beta", "password", "乙")}>register</button>
  </>;
}

function renderAuth() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["private"], "previous account data");
  return {
    client,
    ...render(<QueryClientProvider client={client}>
      <AuthProvider><Harness /></AuthProvider>
    </QueryClientProvider>),
  };
}

it("restores the same account's persisted conditions, origin and run after a reload", async () => {
  useDraft.setState(draft);
  const stored = sessionStorage.getItem("food-draft-v1")!;
  useDraft.getState().reset();
  sessionStorage.setItem("food-draft-v1", stored);
  await useDraft.persist.rehydrate();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(signed)));

  renderAuth();
  await screen.findByText("authenticated");

  expect(useDraft.getState()).toMatchObject(draft);
  expect(getCsrfToken()).toBe("csrf-a");
});

it.each(["user-b", null, 42])("discards a draft owned by %s before restoring another account", async (ownerId) => {
  sessionStorage.setItem("food-draft-v1", JSON.stringify({ version: 5, state: { ...draft, ownerId } }));
  await useDraft.persist.rehydrate();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(signed)));
  const { client } = renderAuth();
  await screen.findByText("authenticated");

  expect(useDraft.getState()).toMatchObject({ ownerId: user.id, hasDraft: false, origin: null, runId: null, preferences: defaults });
  expect(client.getQueryCache().getAll()).toHaveLength(0);
});

it("resets the old draft version once, then binds it to the restored account", async () => {
  sessionStorage.setItem("food-draft-v1", JSON.stringify({ version: 4, state: { ...draft, ownerId: undefined } }));
  await useDraft.persist.rehydrate();
  expect(useDraft.getState()).toMatchObject({ ownerId: null, runId: null, origin: null });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(signed)));
  renderAuth();
  await screen.findByText("authenticated");
  expect(useDraft.getState()).toMatchObject({ ownerId: user.id, hasDraft: false, preferences: defaults });
});

it.each(["offline", "unavailable"])("preserves the draft on %s and restores it when retry succeeds", async (failure) => {
  useDraft.setState(draft);
  const fetcher = vi.fn();
  if (failure === "offline") fetcher.mockRejectedValueOnce(new TypeError("offline"));
  else fetcher.mockResolvedValueOnce(response(null, 503));
  fetcher.mockResolvedValueOnce(response(signed));
  vi.stubGlobal("fetch", fetcher);
  renderAuth();

  await screen.findByText("error");
  expect(useDraft.getState()).toMatchObject(draft);
  fireEvent.click(screen.getByText("retry"));
  await screen.findByText("authenticated");
  expect(useDraft.getState()).toMatchObject(draft);
});

it("clears an expired session's draft and cached account data", async () => {
  useDraft.setState(draft);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(null, 401)));
  const { client } = renderAuth();
  await screen.findByText("anonymous");
  expect(useDraft.getState()).toMatchObject({ ownerId: null, runId: null, origin: null, hasDraft: false });
  expect(client.getQueryCache().getAll()).toHaveLength(0);
  expect(getCsrfToken()).toBeNull();
});

it.each(["logout", "unauthorized"])("clears the draft after %s", async (action) => {
  useDraft.setState(draft);
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce(response(signed))
    .mockResolvedValueOnce(response({ loggedOut: true })));
  const { client } = renderAuth();
  await screen.findByText("authenticated");

  if (action === "logout") fireEvent.click(screen.getByText("logout"));
  else act(() => handleUnauthorized());
  await screen.findByText("anonymous");
  expect(useDraft.getState()).toMatchObject({ ownerId: null, runId: null, origin: null, hasDraft: false });
  expect(client.getQueryCache().getAll()).toHaveLength(0);
  expect(getCsrfToken()).toBeNull();
});

it.each(["login", "register"])("binds a fresh draft when %s establishes a new account", async (action) => {
  useDraft.setState(draft);
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce(response(signed))
    .mockResolvedValueOnce(response({ user: { ...user, id: "user-b", username: "beta" }, csrfToken: "csrf-b" })));
  const { client } = renderAuth();
  await screen.findByText("alpha");
  fireEvent.click(screen.getByText(action));
  await screen.findByText("beta");
  expect(useDraft.getState()).toMatchObject({ ownerId: "user-b", hasDraft: false, runId: null, origin: null, preferences: defaults });
  expect(client.getQueryCache().getAll()).toHaveLength(0);
  expect(getCsrfToken()).toBe("csrf-b");
});

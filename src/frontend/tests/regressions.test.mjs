import assert from "node:assert/strict";
import { after, before, beforeEach, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

let server, api, stream, useDraft, defaults, schemas;
const originalFetch = globalThis.fetch;
const storage = new Map();

before(async () => {
  globalThis.sessionStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  Object.assign(process.env, {
    VITE_API_BASE_URL: "https://example.invalid",
    VITE_AMAP_JS_KEY: "test",
    VITE_AMAP_SECURITY_CODE: "test",
  });
  server = await createServer({
    root: fileURLToPath(new URL("..", import.meta.url)),
    configFile: false,
    server: { middlewareMode: true },
    optimizeDeps: { noDiscovery: true },
  });
  api = await server.ssrLoadModule("/src/lib/api.ts");
  stream = await server.ssrLoadModule("/src/lib/stream.ts");
  ({ useDraft } = await server.ssrLoadModule("/src/lib/store.ts"));
  schemas = await server.ssrLoadModule("/src/lib/schemas.ts");
  ({ defaults } = schemas);
});

beforeEach(() => {
  globalThis.fetch = originalFetch;
  api.advanceSession();
  api.setUnauthorizedHandler(null);
  useDraft.getState().reset();
});

after(async () => {
  globalThis.fetch = originalFetch;
  await server.close();
});

test("initializing a draft preserves an unconfirmed job and the tracked run", () => {
  useDraft.getState().initialize(defaults, "defaults", 0);
  useDraft.getState().setRunId("running-task");
  useDraft.getState().enqueue("recommendation", "/decision-runs", { original: true });
  const job = { ...useDraft.getState().job, status: "failed", error: "Confirmation timed out" };
  useDraft.getState().setJob(job);
  useDraft.getState().initialize({ ...defaults, requestText: "new draft" }, "history", null);
  assert.equal(useDraft.getState().runId, "running-task");
  assert.equal(useDraft.getState().job, job);
  assert.equal(useDraft.getState().preferences.requestText, "new draft");
  const persisted = JSON.parse(storage.get("food-draft-v1"));
  assert.equal(persisted.state.job.key, job.key);
  assert.deepEqual(persisted.state.job.body, { original: true });
});

test("rehydration preserves the complete current draft and its unconfirmed job", async () => {
  useDraft.getState().setOwnerId("user");
  useDraft.getState().initialize(defaults, "defaults", 0);
  useDraft.getState().setOrigin({ latitude: 31.23, longitude: 121.47, address: "Test" });
  useDraft.getState().setPreferences({ ...defaults, partySize: Number.NaN });
  useDraft.getState().setRunId("running-task");
  useDraft.getState().enqueue("recommendation", "/decision-runs", { original: true });
  const snapshot = storage.get("food-draft-v1");
  const key = useDraft.getState().job.key;
  useDraft.getState().reset();
  storage.set("food-draft-v1", snapshot);
  await useDraft.persist.rehydrate();
  const restored = useDraft.getState();
  assert.equal(restored.ownerId, "user");
  assert.equal(restored.hasDraft, true);
  assert.equal(restored.runId, "running-task");
  assert.equal(restored.job.key, key);
  assert.deepEqual(restored.job.body, { original: true });
  assert.equal(restored.prefill.revision, 0);
  assert.equal(restored.origin.address, "Test");
  assert.ok(Number.isNaN(restored.preferences.partySize));
});

test("a malformed stored draft is reported and is not partly restored", async () => {
  const errors = [];
  const originalError = console.error;
  console.error = (...args) => errors.push(args);
  try {
    storage.set("food-draft-v1", JSON.stringify({ version: 8, state: {
      ownerId: "old-user", hasDraft: true, runId: "old-run", preferences: defaults,
    } }));
    await useDraft.persist.rehydrate();
  } finally {
    console.error = originalError;
  }
  assert.equal(errors.length, 1);
  assert.equal(useDraft.getState().ownerId, null);
  assert.equal(useDraft.getState().runId, null);
  assert.equal(useDraft.getState().hasDraft, false);
});

test("account defaults and historical requests share the current input limits", () => {
  for (const preferences of [
    { ...defaults, allowedFoods: Array.from({ length: 6 }, (_, index) => `food-${index}`) },
    { ...defaults, budgetPerPerson: { min: "20.501", max: null } },
  ]) {
    assert.equal(schemas.accountDefaultsSchema.safeParse(schemas.accountDefaults(preferences)).success, false);
    assert.equal(schemas.decisionRequestSchema.safeParse({
      origin: { latitude: 31.23, longitude: 121.47, address: "Test" },
      preferences: {
        budgetPerPerson: preferences.budgetPerPerson, radiusMeters: preferences.radiusMeters,
        allowedFoods: preferences.allowedFoods, excludedFoods: preferences.excludedFoods,
      },
      mealPeriod: preferences.mealPeriod, partySize: preferences.partySize, requestText: preferences.requestText,
    }).success, false);
  }
});

function errorResponse(status = 502) {
  return Response.json({
    success: false,
    error: { code: "LLM_UNAVAILABLE", message: "模型服务暂时不可用", details: { retryable: true } },
    meta: { requestId: "request-123" },
  }, { status });
}

function checkError(error) {
  assert.ok(error instanceof api.ApiError);
  assert.equal(error.code, "LLM_UNAVAILABLE");
  assert.equal(error.message, "模型服务暂时不可用");
  assert.equal(error.retryable, true);
  assert.equal(error.requestId, "request-123");
  return true;
}

test("ordinary requests retain structured upstream error details", async () => {
  globalThis.fetch = async () => errorResponse();
  await assert.rejects(api.request("/preferences"), checkError);
});

test("SSE handshake failures retain the same structured error details", async () => {
  globalThis.fetch = async () => errorResponse(503);
  await assert.rejects(stream.subscribe("run-1", new AbortController().signal, () => {}), checkError);
});

test("a proxy HTML error keeps its request ID without exposing its body", async () => {
  globalThis.fetch = async () => new Response("<html>private proxy details</html>", {
    status: 502,
    headers: { "X-Request-ID": "proxy-123" },
  });
  await assert.rejects(api.request("/preferences"), (error) => {
    assert.equal(error.code, "INTERNAL_ERROR");
    assert.equal(error.requestId, "proxy-123");
    assert.equal(error.message, api.serverErrorMessage);
    return true;
  });
});

test("a response from a previous session cannot sign out the current session", async () => {
  let finish;
  let signedOut = false;
  api.setUnauthorizedHandler(() => { signedOut = true; });
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) {
      finish = () => {
        controller.enqueue(new TextEncoder().encode(JSON.stringify({
          success: false, error: { code: "AUTH_REQUIRED", message: "Expired session" },
        })));
        controller.close();
      };
    },
  }), { status: 401 });
  const pending = api.request("/preferences");
  await new Promise((resolve) => setImmediate(resolve));
  api.advanceSession();
  finish();
  await assert.rejects(pending, (error) => error.name === "AbortError");
  assert.equal(signedOut, false);
});

// Run with a Playwright Page and Vite origin; only mocked API traffic is used.
export default async function sseLimits(page, origin) {
  const results = [];
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  for (const [code, status] of [["USER_STREAM_LIMIT_REACHED", 429], ["STREAM_CAPACITY_REACHED", 503]]) {
    const context = await page.context().browser().newContext({ viewport: { width: 390, height: 844 } });
    const errors = [], logs = [], polls = [];
    let subscriptions = 0;
    const runId = "cbe1a844-98fb-44bc-8779-48ac6395e397";
    const defaults = { budgetPerPerson: { min: "20", max: "60" }, radiusMeters: 2000,
      allowedFoods: [], excludedFoods: [], requestText: "" };
    const request = { origin: { latitude: 31.23, longitude: 121.47, address: "测试位置" },
      preferences: { budgetPerPerson: defaults.budgetPerPerson, radiusMeters: 2000, allowedFoods: [], excludedFoods: [] },
      mealPeriod: "lunch", partySize: 1, requestText: "" };
    const headers = { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Headers": "content-type,x-request-id", "Access-Control-Allow-Methods": "GET,OPTIONS",
      "Content-Type": "application/json" };
    try {
      await context.route("**/auth/me", (route) => route.fulfill({ status: 200, headers,
        body: JSON.stringify({ success: true, data: { user: { id: "alpha", username: "alpha", displayName: "测试账号",
          createdAt: "2026-10-28T00:00:00Z" }, csrfToken: "csrf-alpha" } }) }));
      await context.route("**/preferences", (route) => {
        if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
        return route.fulfill({ status: 200, headers, body: JSON.stringify({ success: true, data: {
          defaults, sources: Object.fromEntries(Object.keys(defaults).map((key) => [key, "builtin"])),
          overrides: {}, revision: 0,
          learning: { mealCount: 0, status: "idle", lastSuccessAt: null, nextLearningAt: 10 },
        } }) });
      });
      await context.route(`**/decision-runs/${runId}`, (route) => {
        if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
        polls.push(Date.now());
        return route.fulfill({ status: 200, headers, body: JSON.stringify({ success: true, data: {
          decisionRunId: runId, discoverySessionId: "discovery", status: polls.length >= 3 ? "completed" : "pending",
          request, originalRequest: request, places: [], filterSummary: {}, suggestions: [], warnings: [],
          errorCode: null, choice: null,
        } }) });
      });
      await context.route(`**/decision-runs/${runId}/events`, (route) => {
        if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
        subscriptions++;
        return route.fulfill({ status, headers: { ...headers, "Retry-After": "2" }, body: JSON.stringify({
          success: false, error: { code, message: "实时进度连接已满", details: { retryable: true } },
        }) });
      });
      const tab = await context.newPage();
      tab.on("pageerror", (error) => errors.push(error.message));
      tab.on("console", (message) => {
        if (["error", "warning"].includes(message.type())) logs.push(message.text());
      });
      await tab.goto(`${origin}/profile`);
      await tab.getByRole("heading", { name: "你的用餐偏好", exact: true }).waitFor();
      check((await tab.title()).includes("今天吃什么") && new URL(tab.url()).origin === origin, "Unexpected page identity");
      await tab.evaluate(async (runId) => (await import("/src/lib/store.ts")).useDraft.getState().setRunId(runId), runId);
      const panel = tab.getByRole("complementary", { name: "选餐任务" });
      await panel.getByRole("alert").getByText("实时进度连接已满，已改为查询结果。", { exact: true }).waitFor();
      await panel.getByText("选餐任务已排队", { exact: true }).waitFor();
      await panel.getByText("推荐已完成", { exact: true }).waitFor({ timeout: 12000 });
      check(subscriptions === 1, `SSE reconnected repeatedly after ${code}`);
      check(polls.length >= 3 && polls[1] - polls[0] >= 1000, "Query fallback polled too quickly or did not run");
      check(await tab.evaluate(async () => (await import("/src/lib/store.ts")).useDraft.getState().runId) === runId,
        "SSE rejection discarded the accepted task");
      check(await tab.locator("vite-error-overlay").count() === 0 && errors.length === 0, `Runtime errors: ${errors.join(", ")}`);
      check(logs.every((message) => /Failed to load resource.*status of (429|503)/.test(message)), `Unexpected console errors: ${logs.join(", ")}`);
      results.push({ code, subscriptions, polls: polls.length, result: "completed" });
    } finally { await context.close(); }
  }
  return results;
}

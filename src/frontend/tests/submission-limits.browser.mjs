// Run with an existing Playwright Page and Vite origin; authentication and API responses are mocked.
export default async function submissionLimits(page, origin) {
  const context = await page.context().browser().newContext({ viewport: { width: 390, height: 844 } });
  const pageErrors = [], networkErrors = [], submissions = [], results = [];
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const headers = { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "content-type,x-request-id,x-auth-intent,idempotency-key,x-csrf-token",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS", "Content-Type": "application/json" };
  const cases = [
    { status: 503, code: "QUEUE_FULL", message: "当前推荐任务已满，任务未受理，请稍后重试", state: "rejected" },
    { status: 429, code: "USER_TASK_RATE_LIMITED", message: "提交推荐过于频繁，请稍后再试", state: "rejected" },
    { status: 503, code: "DEPENDENCY_UNAVAILABLE", message: "数据库暂时不可用", state: "failed" },
  ];
  let current;
  try {
    await context.route("**/auth/me", (route) => route.fulfill({ status: 200, headers,
      body: JSON.stringify({ success: true, data: { user: { id: "alpha", username: "alpha",
        displayName: "测试账号", createdAt: "2026-10-28T00:00:00Z" }, csrfToken: "csrf-alpha" } }) }));
    await context.route("**/preferences", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
      const defaults = { budgetPerPerson: { min: "20", max: "60" }, radiusMeters: 2000,
        allowedFoods: [], excludedFoods: [], requestText: "" };
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ success: true, data: {
        defaults, sources: Object.fromEntries(Object.keys(defaults).map((key) => [key, "builtin"])),
        overrides: {}, revision: 0,
        learning: { mealCount: 0, status: "idle", lastSuccessAt: null, nextLearningAt: 10 },
      } }) });
    });
    await context.route("**/decision-runs", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
      submissions.push({ code: current.code, key: route.request().headers()["idempotency-key"] });
      return route.fulfill({ status: current.status, headers: { ...headers, "Retry-After": "10" },
        body: JSON.stringify({ success: false, error: { code: current.code,
          message: current.message, details: { retryable: true } } }) });
    });
    const tab = await context.newPage();
    tab.on("pageerror", (error) => pageErrors.push(error.message));
    tab.on("console", (message) => {
      if (message.type() === "error" || message.type() === "warning") networkErrors.push(message.text());
    });
    await tab.goto(`${origin}/profile`);
    await tab.getByRole("heading", { name: "你的用餐偏好", exact: true }).waitFor();
    check(new URL(tab.url()).origin === origin && (await tab.title()).includes("今天吃什么"), "Unexpected page identity");
    for (current of cases) {
      const start = submissions.length;
      await tab.evaluate(async (code) => {
        const { useDraft } = await import("/src/lib/store.ts");
        useDraft.getState().enqueue("recommendation", "/decision-runs", { scenario: code });
      }, current.code);
      const panel = tab.getByRole("complementary", { name: "选餐任务" });
      const title = current.state === "rejected" ? "任务未受理，请查看提示后重试" : "提交未完成，请重试确认";
      await panel.getByText(title, { exact: true }).waitFor();
      await panel.getByRole("alert").getByText(current.message, { exact: true }).waitFor();
      check(await tab.evaluate(async () => (await import("/src/lib/store.ts")).useDraft.getState().job.status) === current.state,
        `Wrong submission state for ${current.code}`);
      check(submissions.length === start + 1, "Submission retried without user action");
      await tab.reload();
      await panel.getByText(title, { exact: true }).waitFor();
      await panel.getByRole("alert").getByText(current.message, { exact: true }).waitFor();
      check(submissions.length === start + 1, "Restoring an unconfirmed submission retried it automatically");
      await panel.getByRole("button", { name: "重试提交", exact: true }).click();
      await tab.waitForFunction(async (state) => (await import("/src/lib/store.ts")).useDraft.getState().job?.status === state, current.state);
      check(submissions.length === start + 2, "Manual retry did not submit exactly once");
      check(submissions[start].key === submissions[start + 1].key, "Manual retry changed the idempotency key");
      check(await tab.locator("vite-error-overlay").count() === 0, "Vite error overlay is visible");
      results.push(`${current.code}: ${current.state}, reload and manual retry preserve idempotency`);
    }
    check(pageErrors.length === 0, `Unhandled page errors: ${pageErrors.join(", ")}`);
    check(networkErrors.every((message) => /Failed to load resource.*status of (429|503)/.test(message)),
      `Unexpected browser console errors: ${networkErrors.join(", ")}`);
    return { viewport: "390x844", results, expectedHttpErrors: networkErrors.length };
  } finally { await context.close(); }
}

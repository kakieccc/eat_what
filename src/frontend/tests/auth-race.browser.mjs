/* global document */
// Run with an existing Playwright Page and a running Vite server; all API traffic is mocked.
export default async function authRace(page, origin) {
  const browser = page.context().browser();
  const results = [];
  const pageErrors = [];
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const deferred = () => {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
  };
  const payload = (account) => ({ success: true, data: {
    user: { id: account, username: account, displayName: `用户 ${account}`, createdAt: "2026-10-28T00:00:00Z" },
    csrfToken: `csrf-${account}`,
  } });
  const accountOf = (request) => /food_session=session-(\w+)/.exec(request.headers().cookie ?? "")?.[1];
  const cookie = (account) => account
    ? `food_session=session-${account}; Path=/; HttpOnly; Secure; SameSite=Lax`
    : "food_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax";
  const headers = {
    "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "content-type,x-request-id,x-auth-intent,idempotency-key,x-csrf-token",
    "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS", "Content-Type": "application/json",
  };
  const success = (route, account, data = payload(account)) => route.fulfill({
    status: 200, headers: { ...headers, "Set-Cookie": cookie(account) }, body: JSON.stringify(data),
  });
  async function setup(onMutation) {
    const context = await browser.newContext();
    context.on("page", (tab) => tab.on("pageerror", (error) => pageErrors.push(error.message)));
    await context.route(/\/auth\/(login|register|logout|change-password|me)(\?.*)?$/, async (route) => {
      const request = route.request();
      if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
      if (new URL(request.url()).pathname === "/auth/me") {
        const account = accountOf(request);
        return route.fulfill({ status: account ? 200 : 401, headers, body: JSON.stringify(account
          ? payload(account) : { success: false, error: { code: "AUTH_REQUIRED", message: "请先登录" } }) });
      }
      await onMutation(route);
    });
    await context.route("**/preferences", async (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
      const defaults = { budgetPerPerson: { min: "20", max: "60" }, radiusMeters: 2000,
        allowedFoods: [], excludedFoods: [], requestText: `saved-${accountOf(route.request())}` };
      await route.fulfill({ status: 200, headers, body: JSON.stringify({ success: true, data: {
        defaults, sources: Object.fromEntries(Object.keys(defaults).map((key) => [key, "builtin"])),
        overrides: {}, revision: 0,
        learning: { mealCount: 0, status: "idle", lastSuccessAt: null, nextLearningAt: 10 },
      } }) });
    });
    return context;
  }
  async function form(tab, account, mode = "login") {
    await tab.goto(`${origin}/${mode}`);
    await tab.getByLabel("用户名", { exact: true }).fill(account);
    await tab.getByLabel("密码", { exact: true }).fill("test-password");
    if (mode === "register") await tab.getByLabel("昵称", { exact: true }).fill(account);
  }
  const submit = (tab, mode = "login") => tab.getByRole("button", {
    name: mode === "register" ? "注册并登录" : "登录", exact: true,
  }).click();
  async function queued(tab) {
    await tab.waitForFunction(async () => (await navigator.locks.query()).pending
      .some((lock) => lock.name === "food-auth-session-v1"));
  }
  async function profile(tab, account) {
    await tab.getByRole("link", { name: "偏好", exact: true }).click();
    await tab.getByRole("region", { name: "当前账号" }).getByText(`用户 ${account}`, { exact: true }).waitFor();
    await tab.waitForFunction((value) => document.querySelector('textarea[name="requestText"]')?.value === value, `saved-${account}`);
    const actual = await tab.evaluate(async () => {
      const { request } = await import("/src/lib/api.ts");
      const { useDraft } = await import("/src/lib/store.ts");
      return { account: (await request("/auth/me")).user.id, owner: useDraft.getState().ownerId,
        requestText: useDraft.getState().preferences.requestText };
    });
    check(actual.account === account && actual.owner === account, `UI, Cookie or draft owner mismatch: ${JSON.stringify(actual)}`);
    check(actual.requestText !== "private-alpha", "Previous account's draft survived the switch");
  }

  // A late login cannot overtake B, and an A logout queued behind B must not log B out.
  {
    const alpha = deferred(), beta = deferred(), releaseAlpha = deferred(), releaseBeta = deferred();
    let betaStarted = false, logoutRequests = 0;
    const context = await setup(async (route) => {
      if (route.request().url().endsWith("/logout")) {
        logoutRequests++;
        return success(route, null, { success: true, data: { loggedOut: true } });
      }
      const { username } = route.request().postDataJSON();
      if (username === "alpha") { alpha.resolve(); await releaseAlpha.promise; }
      else { betaStarted = true; beta.resolve(); await releaseBeta.promise; }
      await success(route, username);
    });
    try {
      const a = await context.newPage(), b = await context.newPage();
      await form(a, "alpha"); await form(b, "beta");
      await submit(a); await alpha.promise;
      await submit(b); await queued(b);
      check(!betaStarted, "B's login was sent before A's Set-Cookie completed");
      releaseAlpha.resolve(); await beta.promise;
      await profile(a, "alpha");
      await a.evaluate(async () => {
        const { useDraft } = await import("/src/lib/store.ts");
        const draft = useDraft.getState();
        draft.setPreferences({ ...draft.preferences, requestText: "private-alpha" });
      });
      await a.getByRole("button", { name: "退出登录", exact: true }).click();
      await queued(a); releaseBeta.resolve();
      await profile(a, "beta"); await profile(b, "beta");
      check(logoutRequests === 0, "A's queued logout invalidated B's new session");
      results.push("overlapping logins, cache/draft isolation, stale logout: passed");
    } finally {
      releaseAlpha.resolve(); releaseBeta.resolve(); await context.close();
    }
  }

  // Failed login still releases the lock; registration follows the actual Cookie, not its response body.
  {
    const failed = deferred(), releaseFailure = deferred(), registered = deferred(), releaseRegister = deferred();
    let registerStarted = false, logoutRequests = 0;
    const context = await setup(async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/auth/login") {
        failed.resolve(); await releaseFailure.promise;
        return route.fulfill({ status: 401, headers, body: JSON.stringify({ success: false,
          error: { code: "INVALID_CREDENTIALS", message: "用户名或密码错误" } }) });
      }
      if (path === "/auth/register") {
        registerStarted = true; registered.resolve(); await releaseRegister.promise;
        return success(route, "beta", payload("stale_response"));
      }
      check(route.request().headers()["x-csrf-token"] === "csrf-beta", "Logout used a stale CSRF token");
      logoutRequests++;
      return success(route, null, { success: true, data: { loggedOut: true } });
    });
    try {
      const a = await context.newPage(), b = await context.newPage();
      await form(a, "alpha"); await form(b, "beta", "register");
      await submit(a); await failed.promise;
      await submit(b, "register"); await queued(b);
      check(!registerStarted, "Registration bypassed the login lock");
      releaseFailure.resolve(); await registered.promise;
      await a.getByRole("alert").getByText("用户名或密码错误", { exact: true }).waitFor();
      check(await a.getByLabel("用户名", { exact: true }).inputValue() === "alpha", "Failed login lost form input");
      releaseRegister.resolve();
      await profile(a, "beta"); await profile(b, "beta");
      await b.getByRole("button", { name: "退出登录", exact: true }).click();
      await a.getByRole("heading", { name: "欢迎回来" }).waitFor();
      await b.getByRole("heading", { name: "欢迎回来" }).waitFor();
      for (const tab of [a, b]) {
        check(await tab.evaluate(async () => (await import("/src/lib/store.ts")).useDraft.getState().ownerId) === null,
          "Logout left an account's draft behind");
      }
      check(logoutRequests === 1, "Logout did not run exactly once");
      results.push("failed login, queued registration, authoritative session read, cross-tab logout: passed");
    } finally {
      releaseFailure.resolve(); releaseRegister.resolve(); await context.close();
    }
  }

  // A response may set the Cookie before its body fails to parse.
  {
    const context = await setup((route) => route.fulfill({ status: 200,
      headers: { ...headers, "Set-Cookie": cookie("alpha") }, body: "{" }));
    try {
      const a = await context.newPage(), b = await context.newPage();
      await form(a, "alpha"); await form(b, "beta");
      await submit(a);
      await profile(a, "alpha"); await profile(b, "alpha");
      check(!(await a.evaluate(async () => (await navigator.locks.query()).held))
        .some((lock) => lock.name === "food-auth-session-v1"), "A failed response left the auth lock held");
      results.push("Cookie applied before response parsing failure: passed");
    } finally { await context.close(); }
  }

  {
    let requests = 0;
    const context = await setup(async (route) => { requests++; await success(route, "alpha"); });
    try {
      await context.addInitScript(() => Object.defineProperty(navigator, "locks", { value: undefined }));
      const a = await context.newPage();
      await form(a, "alpha"); await submit(a);
      await a.getByRole("alert").filter({ hasText: "请升级浏览器" }).waitFor();
      check(requests === 0, "Unsupported browsers bypassed auth serialization");
      results.push("unsupported browser fails before sending auth mutation: passed");
    } finally { await context.close(); }
  }
  check(pageErrors.length === 0, `Unhandled browser errors: ${pageErrors.join(", ")}`);
  return results;
}

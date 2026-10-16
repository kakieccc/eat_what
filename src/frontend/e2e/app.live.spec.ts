import { test, expect, type Page, type TestInfo } from "@playwright/test";
import type { Run } from "../src/lib/schemas";

const password = "Test-password-123";
const apiBase = "http://localhost:18000";
type ApiResult<T> = {
  status: number;
  payload: {
    success: boolean;
    data: T;
    error?: { code: string; message: string };
  };
};
type SignedIn = {
  user: { id: string; username: string; displayName: string };
  csrfToken: string;
};
type History = {
  items: {
    id: string;
    choice: { id: string; decisionRunId: string; place: { name: string } };
  }[];
};

async function api<T>(
  page: Page,
  path: string,
  method = "GET",
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<ApiResult<T>> {
  return page.evaluate(
    async (args) => {
      const result = await fetch(args.base + args.path, {
        method: args.method,
        credentials: "include",
        headers: { "Content-Type": "application/json", ...args.headers },
        body: args.body === undefined ? undefined : JSON.stringify(args.body),
      });
      return { status: result.status, payload: await result.json() };
    },
    { base: apiBase, path, method, body, headers },
  );
}

async function register(page: Page): Promise<string> {
  const username =
    "e2e_" +
    Date.now().toString(36) +
    "_" +
    Math.random().toString(36).slice(2, 6);
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "创建账号" })).toBeVisible();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("昵称").fill("测试账号");
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page).toHaveURL("http://localhost:15173/");
  await expect(
    page.getByRole("heading", { name: "今天，吃点什么？" }),
  ).toBeVisible();
  return username;
}

async function waitForRun(page: Page, id: string): Promise<Run> {
  const deadline = Date.now() + 35_000;
  while (Date.now() < deadline) {
    const result = await api<Run>(page, "/decision-runs/" + id);
    expect(result.status).toBe(200);
    if (["completed", "failed"].includes(result.payload.data.status))
      return result.payload.data;
    await page.waitForTimeout(250);
  }
  throw new Error("Decision did not reach a terminal state in 35 seconds.");
}

async function attach(testInfo: TestInfo, name: string, data: unknown) {
  await testInfo.attach(name, {
    body: Buffer.from(JSON.stringify(data, null, 2)),
    contentType: "application/json",
  });
}

test.beforeEach(async ({ page }, testInfo) => {
  const runtimeErrors: string[] = [];
  const consoleMessages: string[] = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type()))
      consoleMessages.push(message.type() + ": " + message.text());
  });
  testInfo.annotations.push({
    type: "browser",
    description: "Browser plugin not available; repeatable Playwright suite.",
  });
  await page.exposeFunction("testRuntimeErrors", () => runtimeErrors);
  await page.exposeFunction("testConsoleMessages", () => consoleMessages);
});

test.afterEach(async ({ page }, testInfo) => {
  if (page.isClosed()) return;
  await page.screenshot({
    path: testInfo.outputPath("screen.png"),
    fullPage: false,
  });
  const health = await page.evaluate(async () => {
    const callbacks = window as unknown as {
      testRuntimeErrors(): Promise<string[]>;
      testConsoleMessages(): Promise<string[]>;
    };
    return {
      url: location.href,
      title: document.title,
      runtimeErrors: await callbacks.testRuntimeErrors(),
      consoleMessages: await callbacks.testConsoleMessages(),
      hasOverlay: Boolean(document.querySelector("vite-error-overlay")),
    };
  });
  await attach(testInfo, "browser-health", health);
  expect(health.hasOverlay).toBe(false);
  expect(health.runtimeErrors).toEqual([]);
});

test("account and persisted preferences use real backend sessions", async ({
  page,
}, testInfo) => {
  const username = await register(page);
  await page.getByRole("link", { name: "偏好", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "你的用餐偏好" }),
  ).toBeVisible();
  await page.getByRole("radio", { name: "1 km", exact: true }).click();
  await page.getByRole("button", { name: "保存偏好", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("偏好已保存");
  await page.reload();
  await expect(
    page.getByRole("radio", { name: "1 km", exact: true }),
  ).toHaveAttribute("aria-checked", "true");

  // Profile editing and password changes currently have API contracts but no page controls.
  const me = await api<SignedIn>(page, "/auth/me");
  expect(me.status).toBe(200);
  const headers = { "X-CSRF-Token": me.payload.data.csrfToken };
  const updated = await api<SignedIn["user"]>(
    page,
    "/auth/me",
    "PATCH",
    { displayName: "修改后的昵称" },
    headers,
  );
  expect(updated.status).toBe(200);
  await page.reload();
  await expect(page.getByLabel("当前账号")).toContainText("修改后的昵称");
  const changed = await api(
    page,
    "/auth/change-password",
    "POST",
    {
      currentPassword: password,
      newPassword: "New-test-password-123",
    },
    headers,
  );
  expect(changed.status).toBe(200);
  await page.reload();
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码", { exact: true }).fill("New-test-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL("http://localhost:15173/profile");
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  await attach(testInfo, "account-result", {
    username,
    preferencesPersisted: true,
    passwordChanged: true,
    loggedOut: true,
  });
});

test("real recommendation, refinement, selection and history", async ({
  page,
}, testInfo) => {
  await register(page);
  await page.getByRole("link", { name: "先选一个出发地点" }).click();
  await expect(
    page.getByRole("heading", { name: "选择出发地点" }),
  ).toBeVisible();
  await page.getByLabel("搜索地址").fill("上海五角场");
  await page
    .getByRole("button", { name: /五角场/ })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "使用这个位置" }),
  ).toBeEnabled();
  await expect(page.locator(".amap-container").first()).toBeVisible();
  await page.getByRole("button", { name: "使用这个位置" }).click();
  await expect(page).toHaveURL("http://localhost:15173/");
  await page.getByLabel("最低预算").fill("");
  await page.getByLabel("最高预算").fill("");
  await page.getByRole("radio", { name: "5 km", exact: true }).click();
  await page.getByPlaceholder("想吃热乎的，今天不太想吃面…").fill("想吃清淡点");
  const creation = page.waitForResponse(
    (response) =>
      response.url() === apiBase + "/decision-runs" &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "帮我选一家" }).click();
  const created = await creation;
  const initial = await created.json();
  await attach(testInfo, "creation-result", initial);
  expect(created.status()).toBe(201);
  await expect(page).toHaveURL("http://localhost:15173/discover");
  const parent = await waitForRun(page, initial.data.decisionRunId);
  await attach(testInfo, "parent-result", parent);
  expect(parent.status, parent.errorCode ?? "parent run").toBe("completed");
  await expect(
    page.getByRole("button", { name: "更近", exact: true }),
  ).toBeEnabled();

  const refinement = page.waitForResponse(
    (response) =>
      response.url().endsWith("/refinements") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "更近", exact: true }).click();
  const refined = await refinement;
  const childResponse = await refined.json();
  await attach(testInfo, "refinement-created", childResponse);
  expect(refined.status()).toBe(201);
  const child = await waitForRun(page, childResponse.data.decisionRunId);
  await attach(testInfo, "child-result", child);
  expect(child.status, child.errorCode ?? "child run").toBe("completed");
  expect(child.discoverySessionId).toBe(parent.discoverySessionId);
  expect(
    child.places.length,
    "At least two real candidates are required to verify changing selection.",
  ).toBeGreaterThanOrEqual(2);
  const [first, second] = child.places;
  await page
    .locator(".place-card")
    .filter({ hasText: first.name })
    .getByRole("button", { name: "选这家", exact: true })
    .click();
  await expect(page.locator(".detail-name")).toHaveText(first.name);
  await expect(page.getByRole("button", { name: "已选这家" })).toBeDisabled();
  await expect(page.getByRole("textbox")).toHaveCount(0);
  const firstChoice = (
    await api<Run>(page, "/decision-runs/" + child.decisionRunId)
  ).payload.data.choice;
  await page.getByRole("link", { name: "返回推荐" }).click();
  await expect(page).toHaveURL("http://localhost:15173/discover");
  await page
    .locator(".place-card")
    .filter({ hasText: second.name })
    .getByRole("button", { name: "选这家", exact: true })
    .click();
  await expect(page.locator(".detail-name")).toHaveText(second.name);
  await expect(page.getByRole("button", { name: "已选这家" })).toBeDisabled();
  const final = (await api<Run>(page, "/decision-runs/" + child.decisionRunId))
    .payload.data;
  expect(final.choice?.id).toBe(firstChoice?.id);
  expect(final.choice?.candidateId).toBe(second.candidateId);
  await page.getByRole("link", { name: "历史", exact: true }).click();
  await expect(page.locator(".history-list article")).toHaveCount(1);
  await expect(page.locator(".history-list")).toContainText(second.name);
  await page.reload();
  await expect(page.locator(".history-list")).toContainText(second.name);
  const history = (await api<History>(page, "/discovery-sessions")).payload
    .data;
  expect(history.items).toHaveLength(1);
  expect(history.items[0].choice.id).toBe(final.choice?.id);
  expect(history.items[0].choice.decisionRunId).toBe(child.decisionRunId);
  await attach(testInfo, "selection-history-result", {
    final,
    history,
    semanticReview: "pending",
  });
});

test("logout in another tab revokes the shared session", async ({ page, context }) => {
  await register(page);
  const second = await context.newPage();
  try {
    await second.goto("http://localhost:15173/profile");
    await expect(second.getByRole("heading", { name: "你的用餐偏好" })).toBeVisible();
    await page.goto("/profile");
    await page.getByRole("button", { name: "退出登录", exact: true }).click();
    await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
    await second.getByRole("button", { name: "保存偏好", exact: true }).click();
    await expect(second.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
    expect((await api(second, "/preferences")).status).toBe(401);
  } finally { await second.close(); }
});

test("keyboard dialog, large text and history reload remain usable", async ({ page }) => {
  await register(page);
  await page.evaluate(() => { document.documentElement.style.fontSize = "24px"; });
  const trigger = page.getByRole("button", { name: /更多条件/ });
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("只考虑这些食物（任选其一）").fill("粤菜，轻食，日料，面食，东北菜，淮扬菜");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(trigger).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("link", { name: "历史", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("heading").first()).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("button", { name: "帮我选一家" })).toBeVisible();
});

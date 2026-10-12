import { expect, test, type Route } from "@playwright/test";
import { defaults } from "../src/lib/schemas";

const user = (username: string) => ({
  id: `user-${username}`,
  username,
  displayName: username === "alice" ? "小艾" : "小博",
  createdAt: "2026-01-01T00:00:00Z",
});
const signed = (username: string) => ({
  success: true, data: { user: user(username), csrfToken: `csrf-${username}` },
});
const unauthorized = { success: false, error: { code: "AUTH_REQUIRED", message: "请先登录" } };
const reply = (route: Route, json: unknown, status = 200) =>
  route.fulfill({ status, json });

test("guest registration returns to the requested page and logout clears the shell", async ({ page }) => {
  const pageErrors: string[] = [];
  let logoutAttempts = 0;
  let registerAttempts = 0;
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route("**/auth/me", (route) => reply(route, unauthorized, 401));
  await page.route("**/auth/register", (route) => {
    registerAttempts += 1;
    return reply(route, signed("alice"), 201);
  });
  await page.route("**/discovery-sessions", (route) => reply(route, {
    success: true, data: { items: [], nextCursor: null },
  }));
  await page.route("**/preferences", (route) => reply(route, { success: true, data: defaults }));
  await page.route("**/auth/logout", (route) => {
    logoutAttempts += 1;
    return logoutAttempts === 1
      ? reply(route, { success: false, error: { code: "DEPENDENCY_UNAVAILABLE", message: "暂时无法退出" } }, 503)
      : reply(route, { success: true, data: { loggedOut: true } });
  });

  await page.goto("/history");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "主导航" })).toHaveCount(0);
  await page.screenshot({
    path: `/tmp/eat-what-login-${test.info().project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("link", { name: "创建账号" }).click();
  await page.getByLabel("用户名").fill("alice");
  await page.getByLabel("密码").fill("secret88");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByLabel("昵称")).toBeFocused();
  await page.getByLabel("昵称").fill("   ");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("alert")).toContainText("昵称不能为空");
  await page.getByLabel("昵称").fill(" 小艾 ");
  await page.getByLabel("密码").fill("1234567");
  await page.getByRole("button", { name: "注册并登录" }).click();
  expect(await page.getByLabel("密码").evaluate((input: HTMLInputElement) => input.validity.tooShort)).toBe(true);
  await page.getByLabel("密码").fill("secret88");
  const registering = page.waitForRequest("**/auth/register");
  await page.getByRole("button", { name: "注册并登录" }).click();
  const request = await registering;
  expect(request.headers()["x-auth-intent"]).toBe("web");
  expect(request.postDataJSON()).toMatchObject({ password: "secret88", displayName: "小艾" });
  expect(registerAttempts).toBe(1);
  await expect(page).toHaveURL(/\/history$/);
  await expect(page.getByRole("heading", { name: "每一餐，都有迹可循" })).toBeVisible();

  await page.getByRole("link", { name: "偏好" }).click();
  await expect(page.getByRole("region", { name: "当前账号" })).toContainText("小艾");
  const failedSignOut = page.waitForRequest("**/auth/logout");
  await page.getByRole("button", { name: "退出登录" }).click();
  expect((await failedSignOut).headers()["x-csrf-token"]).toBe("csrf-alice");
  await expect(page.getByRole("alert")).toContainText("暂时无法退出");
  await expect(page.getByRole("region", { name: "当前账号" })).toContainText("小艾");
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("navigation", { name: "主导航" })).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});

test("failed login stays on the form and another account gets its own preferences", async ({ page }) => {
  let active = "";
  await page.route("**/auth/me", (route) => reply(route, unauthorized, 401));
  await page.route("**/auth/login", (route) => {
    const body = route.request().postDataJSON() as { username: string; password: string };
    if (body.password === "wrong-password")
      return reply(route, { success: false, error: { code: "INVALID_CREDENTIALS", message: "用户名或密码错误" } }, 401);
    active = body.username;
    return reply(route, signed(active));
  });
  await page.route("**/auth/logout", (route) => reply(route, {
    success: true, data: { loggedOut: true },
  }));
  await page.route("**/preferences", (route) => reply(route, {
    success: true, data: { ...defaults, requestText: active === "alice" ? "爱吃面" : "想吃米饭" },
  }));

  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("用户名").fill("alice");
  await page.getByLabel("密码").fill("wrong-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("用户名或密码错误");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("密码").fill("strong-password-12");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator('textarea[name="requestText"]')).toHaveValue("爱吃面");
  await page.getByRole("link", { name: "偏好" }).click();
  await page.getByRole("button", { name: "退出登录" }).click();
  await page.getByLabel("用户名").fill("bob");
  await page.getByLabel("密码").fill("strong-password-12");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator('textarea[name="requestText"]')).toHaveValue("想吃米饭");
});

test("session check can be retried and an expired session returns to login", async ({ page }) => {
  let checks = 0;
  await page.route("**/auth/me", (route) => {
    checks += 1;
    return checks === 1
      ? reply(route, { success: false, error: { code: "DEPENDENCY_UNAVAILABLE", message: "服务不可用" } }, 503)
      : reply(route, signed("alice"));
  });
  await page.route("**/preferences", (route) => reply(route, unauthorized, 401));
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  await expect(page.getByText("无法检查登录状态，请确认网络和后端服务。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "今天，吃点什么？" })).toHaveCount(0);
  await page.getByRole("button", { name: "重试" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  expect(checks).toBe(2);
});

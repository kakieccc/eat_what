import { test, expect } from "@playwright/test";
import { defaults } from "../src/lib/schemas";
test("home, form validation and manual location entry", async ({ page }) => {
  await page.route("**/auth/me", (route) => route.fulfill({ json: {
    success: true,
    data: { user: { id: "user-1", username: "tester", displayName: "测试账号", createdAt: "2026-01-01T00:00:00Z" }, csrfToken: "test-csrf" },
  } }));
  await page.route("**/preferences", (route) => route.fulfill({ json: {
    success: true, data: defaults,
  } }));
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page).toHaveTitle(/今天吃什么/);
  await expect(
    page.getByRole("heading", { name: "今天，吃点什么？" }),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/food-home-" + test.info().project.name + ".png",
    fullPage: true,
  });
  await page.getByRole("radio", { name: "1 km", exact: true }).click();
  await expect(
    page.getByRole("radio", { name: "1 km", exact: true }),
  ).toHaveAttribute("aria-checked", "true");
  await page.getByLabel("最低预算").fill("100");
  await page.getByLabel("最高预算").fill("20");
  await page.getByRole("button", { name: "帮我选一家", exact: true }).click();
  await expect(
    page.getByText("请检查预算上下限、搜索半径及是否有重复排除的菜系。"),
  ).toBeVisible();
  await page.getByRole("button", { name: /更多条件/ }).click();
  await expect(
    page.getByRole("heading", { name: "把这一餐，说得更具体" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "先选一个出发地点" }).click();
  await expect(page).toHaveURL(/\/map$/);
  await expect(
    page.getByRole("button", { name: "使用这个位置" }),
  ).toBeDisabled();
  expect(errors).toEqual([]);
});
test("real decision journey", async ({ page }) => {
  test.skip(
    process.env.FOOD_LIVE_TESTS !== "1" || !process.env.TEST_ADDRESS ||
      !process.env.TEST_USERNAME || !process.env.TEST_PASSWORD,
    "Requires real services, TEST_ADDRESS and a dedicated test account",
  );
  await page.goto("/login");
  await page.getByLabel("用户名").fill(process.env.TEST_USERNAME!);
  await page.getByLabel("密码").fill(process.env.TEST_PASSWORD!);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/map");
  await page.getByLabel("搜索地址").fill(process.env.TEST_ADDRESS!);
  await page.locator(".address-tips button").first().click();
  await expect(
    page.getByRole("button", { name: "使用这个位置" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "使用这个位置" }).click();
  await page.getByRole("button", { name: "帮我选一家", exact: true }).click();
  await expect(page.locator(".place-card").first()).toBeVisible({
    timeout: 45000,
  });
  await page
    .getByRole("button", { name: "选这家", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("link", { name: "在高德查看" }),
  ).toHaveAttribute("href", /^https:\/\/uri\.amap\.com\//);
  await page.getByRole("link", { name: "历史", exact: true }).click();
  await expect(page.locator(".history-list article").first()).toBeVisible();
});

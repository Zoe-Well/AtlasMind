import { expect, test } from "@playwright/test";

test("local development session is labeled as real persistent data", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("link", { name: "进入本地真实数据工作台" }).click();
  await expect(page.getByText("本地真实数据").first()).toBeVisible();
  await expect(page.getByText("页面中的答案与来源均为演示数据")).toHaveCount(0);
});

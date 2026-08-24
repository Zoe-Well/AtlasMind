import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

const pages = [
  ["01-chat", "/chat", "企业知识助手"],
  ["02-knowledge", "/knowledge", "数据接入"],
  ["03-graph", "/graph", "知识图谱"],
  ["04-rag", "/rag", "RAG 策略"],
  ["05-runs", "/runs", "运行中心"],
  ["06-approvals", "/approvals", "审批中心"],
  ["07-evaluations", "/evaluations", "质量评估"],
  ["08-governance", "/governance", "权限与审计"],
  ["09-system-states", "/system-states", "系统状态"],
] as const;

test("capture the complete desktop interface", async ({ page }) => {
  const outputDir = resolve(process.cwd(), "../design/screenshots/latest");
  await mkdir(outputDir, { recursive: true });
  await page.setViewportSize({ width: 1600, height: 1000 });

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "欢迎使用 AtlasMind" })).toBeVisible();
  await page.screenshot({
    path: resolve(outputDir, "00-login.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("link", { name: "进入本地工作台" }).click();

  for (const [fileName, route, heading] of pages) {
    await page.goto(route);
    await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
    await page.screenshot({
      path: resolve(outputDir, `${fileName}.png`),
      fullPage: true,
      animations: "disabled",
    });
  }
});

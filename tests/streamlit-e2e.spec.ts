import { expect, test } from "@playwright/test";

test("analyzes a queried ticker through IBKR", async ({ page }) => {
  test.setTimeout(120_000);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "FCN Wizard" })).toBeVisible();

  await page.getByRole("textbox", { name: "Ticker Query" }).fill("NVDA");
  await page.getByRole("button", { name: "Analyze" }).click();

  await expect(page.getByRole("heading", { name: "Candidate Ranking" })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Single-Name Decision Support")).toBeVisible();
  await expect(page.getByText("NVDA: score")).toBeVisible();
  await expect(page.getByText("IBKR connection failed")).toHaveCount(0);
});

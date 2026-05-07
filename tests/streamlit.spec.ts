import { expect, test } from "@playwright/test";

test("FCN Wizard dashboard loads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "FCN Wizard" })).toBeVisible();
  await expect(page.getByText("Ticker Query")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analyze" })).toBeVisible();
});

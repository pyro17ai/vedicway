import { expect, type Page } from "playwright/test";

export async function createMoscowChart(page: Page) {
  await page.goto("/");
  await page.getByLabel("Имя").fill("Александр");
  await page.getByLabel("Дата рождения").fill("2006-10-16");
  await page.getByLabel("Время рождения").fill("13:30");
  await page.getByRole("combobox", { name: "Место рождения" }).fill("Москва");
  await page.getByRole("option", { name: "Москва, Россия" }).click();
  await page.getByRole("button", { name: /рассчитать карту/i }).click();

  await expect(page).toHaveURL(/\/chart\/chart_[A-Za-z0-9_-]+\?tab=chart&varga=D1&mode=plain/);
  await expect(page.getByRole("grid", { name: "Южноиндийская карта D1" })).toBeVisible({ timeout: 30_000 });
}

export async function waitForExplanation(page: Page) {
  await page.getByRole("tab", { name: /^Объяснение/ }).click();
  await expect(page.getByRole("heading", { name: "Объяснение карты" })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("region", { name: "Восемь жизненных тем" })).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".domain-card")).toHaveCount(8, { timeout: 45_000 });
}

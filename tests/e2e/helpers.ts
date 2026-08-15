import { expect, type Page } from "playwright/test";

export async function createMoscowChart(page: Page) {
  await page.goto("/");
  const cookieChoice = page.getByRole("button", { name: "Отклонить необязательные", exact: true });
  if (await cookieChoice.isVisible()) await cookieChoice.click();
  await page.getByLabel("Дата рождения").fill("2006-10-16");
  await page.getByLabel("Время рождения").fill("13:30");
  await page.getByRole("combobox", { name: "Место рождения" }).fill("Москва");
  await page.getByRole("option", { name: "Москва, Россия" }).click();
  for (const checkbox of await page.locator(".legal-acceptance input[type=checkbox]").all()) {
    await checkbox.check();
  }
  await page.getByRole("button", { name: /рассчитать карту/i }).click();

  await expect(page).toHaveURL(
    /\/chart\/chart_[A-Za-z0-9_-]+\?tab=chart&varga=D1/,
    { timeout: 45_000 },
  );
  await expect(page.getByRole("grid", { name: "Южноиндийская карта D1" })).toBeVisible({ timeout: 30_000 });
}

export async function waitForExplanation(page: Page) {
  const explanation = page.locator("#workspace-panel-explanation");
  await expect(explanation.getByRole("heading", { name: "Объяснение карты" })).toBeVisible({ timeout: 45_000 });
  await explanation.scrollIntoViewIfNeeded();
  await expect(explanation.getByRole("region", { name: "Восемь жизненных тем" })).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".domain-card")).toHaveCount(8, { timeout: 45_000 });
}

export async function openTestCheckout(page: Page, email = "buyer@example.com") {
  await page.getByRole("button", { name: "Открыть полный текст" }).first().click();
  await page.getByRole("textbox", { name: /email для чека/i }).fill(email);
  await page.getByRole("checkbox", { name: /принимаю условия/i }).check();
  await page.getByRole("button", { name: /перейти к оплате/i }).click();
  await expect(page).toHaveURL(/\/api\/v1\/test\/checkout\/pur_[A-Za-z0-9_-]+/);
  await expect(page.getByRole("heading", { name: "Тестовая оплата YooKassa" })).toBeVisible();
}

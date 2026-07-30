import { expect, test } from "playwright/test";

test("платная ректификация открывается после оплаты и возвращает расчёт", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/");
  const cookieChoice = page.getByRole("button", {
    name: "Отклонить необязательные",
    exact: true,
  });
  if (await cookieChoice.isVisible()) await cookieChoice.click();

  await page.getByLabel("Дата рождения").fill("1985-05-17");
  await page.getByRole("combobox", { name: "Место рождения" }).fill("Москва");
  await page.getByRole("option", { name: "Москва, Россия" }).click();
  await page.getByLabel("Не знаю").check();
  await expect(page.getByText("300 ₽", { exact: true })).toBeVisible();
  for (const checkbox of await page.locator(".legal-acceptance input[type=checkbox]").all()) {
    await checkbox.check();
  }
  await page.getByRole("button", { name: /восстановить время/i }).click();

  const paywall = page.getByRole("dialog");
  await expect(paywall).toContainText("Восстановление времени рождения");
  await expect(paywall).toContainText("300 ₽");
  await paywall.getByRole("textbox", { name: /email для чека/i }).fill("buyer@example.com");
  await paywall.getByRole("checkbox", { name: /принимаю условия/i }).check();
  await paywall.getByRole("button", { name: /перейти к оплате/i }).click();

  await expect(page).toHaveURL(/\/api\/v1\/test\/checkout\/pur_[A-Za-z0-9_-]+/);
  await expect(page.getByText("300 ₽", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Оплатить тестовый заказ" }).click();
  await expect(page).toHaveURL(/\/rectification\/chart_[A-Za-z0-9_-]+/);
  await expect(page.getByRole("heading", {
    name: "Что близкие говорили о времени вашего рождения?",
  })).toBeVisible();

  await page.getByLabel("Утром").check();
  await page.getByRole("button", { name: "Далее" }).click();

  const datedEvents = [
    { year: "2003", month: "6" },
    { year: "2008", month: "9" },
    { year: "2012", month: "7" },
  ];
  for (const event of datedEvents) {
    await page.getByLabel("Год события").selectOption(event.year);
    await page.getByRole("button", { name: "Далее" }).click();
    await page.getByLabel("Месяц события").selectOption(event.month);
    await page.getByRole("button", { name: "Далее" }).click();
  }
  for (let index = 0; index < 4; index += 1) {
    await page.getByLabel("Год события").selectOption("skip");
    await page.getByRole("button", {
      name: index === 3 ? "Рассчитать время" : "Далее",
    }).click();
  }

  await expect(page.locator(".rectification-result")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("НАИБОЛЕЕ СОГЛАСОВАННОЕ ВРЕМЯ")).toBeVisible();
  await expect(page.getByRole("button", { name: "Скопировать время" })).toBeVisible();
  await expect(page.getByText(/вариантов проверено/)).toBeVisible();
});

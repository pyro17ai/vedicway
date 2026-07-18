// spec: docs/testing/chart-result-e2e.plan.md
import { expect, test } from "playwright/test";

import { createMoscowChart, openTestCheckout, waitForExplanation } from "./helpers";

test.describe("Доступ к подробному отчёту", () => {
  test("free-to-full-report", async ({ page }) => {
    test.setTimeout(90_000);
    // 1. Создать карту и открыть вкладку объяснения.
    await createMoscowChart(page);
    await waitForExplanation(page);

    // 2. Нажать «Подробнее» и закрыть окно клавишей Escape.
    const detailButton = page.getByRole("button", { name: "Подробнее" }).first();
    await detailButton.click();
    const paywall = page.getByRole("dialog", { name: /./ });
    await expect(paywall).toBeVisible();
    await expect(paywall).toContainText("990 ₽");
    await expect(paywall).toContainText("Без подписки");
    await page.keyboard.press("Escape");
    await expect(paywall).toBeHidden();
    await expect(detailButton).toBeFocused();

    // 3. Пройти redirect через локальный симулятор YooKassa и запросить PDF.
    await openTestCheckout(page);
    await page.getByRole("button", { name: "Оплатить тестовый заказ" }).click();
    await expect(page).toHaveURL(/\/chart\/chart_[A-Za-z0-9_-]+\?.*tab=explanation/);
    await expect(page.getByRole("dialog")).toContainText("На чём основано", { timeout: 45_000 });
    await page.getByRole("button", { name: "Закрыть подробный текст" }).click();

    const pdfButton = page.locator(".rail-pdf");
    await expect(pdfButton).toBeEnabled({ timeout: 45_000 });
    const download = page.waitForEvent("download");
    await pdfButton.click();
    const file = await download;
    expect((await file.suggestedFilename()).endsWith(".pdf")).toBe(true);
  });
});

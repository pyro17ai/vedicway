// spec: docs/testing/chart-result-e2e.plan.md
import { expect, test } from "playwright/test";

import { createMoscowChart, waitForExplanation } from "./helpers";

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

    // 3. Подтвердить тестовую оплату и запросить PDF.
    await detailButton.click();
    await page.getByRole("button", { name: "Открыть полный отчёт за 990 ₽" }).click();
    await expect(page.getByRole("dialog")).toContainText("На чём основано");
    await page.getByRole("button", { name: "Закрыть подробный текст" }).click();

    const pdfButton = page.getByRole("button", { name: /скачать PDF/i });
    await expect(pdfButton).toBeEnabled({ timeout: 15_000 });
    const download = page.waitForEvent("download");
    await pdfButton.click();
    const file = await download;
    expect((await file.suggestedFilename()).endsWith(".pdf")).toBe(true);
  });
});

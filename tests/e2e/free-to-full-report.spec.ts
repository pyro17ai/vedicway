// spec: docs/testing/chart-result-e2e.plan.md
import { expect, test } from "playwright/test";

import { createMoscowChart, openTestCheckout, waitForExplanation } from "./helpers";

test.describe("Доступ к подробному отчёту", () => {
  test("free-to-full-report", async ({ page }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: 1280, height: 620 });
    // 1. Создать карту и открыть вкладку объяснения.
    await createMoscowChart(page);
    await waitForExplanation(page);

    await page.getByRole("tab", { name: /^Вопросы/ }).click();
    const questionCard = page.locator(".workspace-questions-panel .question-card").first();
    await expect(questionCard).toBeVisible();
    await questionCard.hover();
    const hoverStyle = await questionCard.evaluate((element) => {
      const computed = getComputedStyle(element);
      const channels = computed.backgroundColor.match(/[\d.]+/g)?.map(Number) ?? [0, 0, 0];
      const brightness = (0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]) / 255;
      return { backgroundImage: computed.backgroundImage, brightness };
    });
    expect(hoverStyle.backgroundImage).toBe("none");
    expect(hoverStyle.brightness).toBeGreaterThan(0.8);
    await page.getByRole("tab", { name: /^Объяснение/ }).click();

    // 2. Нажать «Подробнее» и закрыть окно клавишей Escape.
    const detailButton = page.getByRole("button", { name: "Подробнее" }).first();
    await detailButton.click();
    const paywall = page.getByRole("dialog", { name: /./ });
    await expect(paywall).toBeVisible();
    await expect(paywall).toContainText("990 ₽");
    await expect(paywall).toContainText("Без подписки");
    const paywallBox = await paywall.boundingBox();
    const viewport = page.viewportSize();
    expect(paywallBox).not.toBeNull();
    expect(viewport).not.toBeNull();
    expect(paywallBox!.y).toBeGreaterThanOrEqual(12);
    expect(paywallBox!.y + paywallBox!.height).toBeLessThanOrEqual(viewport!.height - 12);
    await page.keyboard.press("Escape");
    await expect(paywall).toBeHidden();
    await expect(detailButton).toBeFocused();

    // 3. Пройти redirect через локальный симулятор YooKassa.
    await openTestCheckout(page);
    await page.getByRole("button", { name: "Оплатить тестовый заказ" }).click();
    await expect(page).toHaveURL(/\/chart\/chart_[A-Za-z0-9_-]+\?.*tab=explanation/);
    await expect(page.getByRole("dialog")).toContainText("На чём основано", { timeout: 45_000 });
    await page.getByRole("button", { name: "Закрыть подробный текст" }).click();

    // 4. PDF должен получить именно текущую варгу и режим, а не значения по умолчанию.
    await page.getByRole("tab", { name: /^Натальная карта/ }).click();
    await page.getByLabel("Варга").selectOption("D24");
    await page.getByRole("button", { name: "Профессионально" }).click();
    await expect(page).toHaveURL(/tab=chart&varga=D24&mode=expert/);

    const pdfButton = page.locator(".rail-pdf");
    await expect(pdfButton).toBeEnabled({ timeout: 45_000 });
    const renderRequest = page.waitForRequest((request) =>
      request.method() === "POST" && /\/reports\/pdf$/.test(new URL(request.url()).pathname),
    );
    const download = page.waitForEvent("download");
    await pdfButton.click();
    expect((await renderRequest).postDataJSON()).toEqual({
      preferences: {
        schema_version: "pdf-render-preferences.v1",
        varga: "D24",
        mode: "expert",
        chart_style: "south_indian",
      },
    });
    const file = await download;
    expect((await file.suggestedFilename()).endsWith(".pdf")).toBe(true);
  });
});

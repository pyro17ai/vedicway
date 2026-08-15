// spec: docs/testing/chart-result-e2e.plan.md
import { expect, test } from "playwright/test";

import { createMoscowChart, openTestCheckout, waitForExplanation } from "./helpers";

test.describe("Доступ к подробному отчёту", () => {
  test("free-to-full-report", async ({ page }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: 1280, height: 620 });
    // 1. Создать карту и дождаться персонального первого чтения.
    await createMoscowChart(page);
    await waitForExplanation(page);
    const firstReading = page.locator("#workspace-explanation-overview");
    const fullOffer = page.getByRole("region", { name: "Доступ к полному разбору" });
    await expect(firstReading).toBeVisible();
    await expect(firstReading.locator("p")).not.toBeEmpty();
    await expect(fullOffer).toBeVisible();
    const readingBox = await firstReading.boundingBox();
    const offerBox = await fullOffer.boundingBox();
    expect(readingBox).not.toBeNull();
    expect(offerBox).not.toBeNull();
    expect(readingBox!.y).toBeLessThan(offerBox!.y);

    // 2. Открыть полный текст и закрыть окно клавишей Escape.
    const detailButton = page.getByRole("button", { name: "Открыть полный текст" }).first();
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
    await expect(page).not.toHaveURL(/domain=/);
    await expect(page.getByRole("button", { name: "Все темы", exact: true })).toHaveAttribute("aria-pressed", "true");

    // 3. Пройти redirect через локальный симулятор YooKassa.
    await openTestCheckout(page);
    await page.getByRole("button", { name: "Оплатить тестовый заказ" }).click();
    await expect(page).toHaveURL(/\/chart\/chart_[A-Za-z0-9_-]+\?.*tab=explanation/);
    await expect(page.getByRole("dialog")).toContainText("На чём основано", { timeout: 45_000 });
    await page.getByRole("button", { name: "Закрыть подробный текст" }).click();

    // 4. PDF должен получить текущую варгу и единый понятный режим.
    await page.getByLabel("Варга").selectOption("D24");
    await expect(page.getByLabel("Варга")).toHaveValue("D24");
    await expect(page.getByRole("button", { name: "Профессионально" })).toHaveCount(0);

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
        mode: "plain",
        chart_style: "south_indian",
      },
    });
    const file = await download;
    expect((await file.suggestedFilename()).endsWith(".pdf")).toBe(true);
  });
});

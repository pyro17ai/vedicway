import { expect, test } from "playwright/test";

import { createMoscowChart, openTestCheckout, waitForExplanation } from "./helpers";


test.describe("Возврат из YooKassa", () => {
  test("query не открывает отчёт, а задержанное подтверждение восстанавливается после reload", async ({ page }) => {
    test.setTimeout(120_000);
    await createMoscowChart(page);
    await waitForExplanation(page);
    const chartUrl = new URL(page.url());
    const chartId = chartUrl.pathname.split("/").pop()!;

    await openTestCheckout(page);
    const checkoutUrl = page.url();
    const paymentState = await page.evaluate(() => JSON.parse(sessionStorage.getItem("vedicway:payment-return") ?? "null"));
    expect(paymentState.chartId).toBe(chartId);

    await page.goto(`/chart/${chartId}?payment_return=${paymentState.purchaseId}&success=true`);
    await expect(page.getByText(/проверяем платёж по данным YooKassa/i)).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.reload();
    await expect(page.getByText(/проверяем платёж по данным YooKassa/i)).toBeVisible();
    await page.getByRole("tab", { name: /^Объяснение/ }).click();
    await expect(page.getByRole("button", { name: "Подробнее" }).first()).toBeVisible({ timeout: 45_000 });

    await page.goto(`${checkoutUrl}?delay_ms=1500`);
    await page.getByRole("button", { name: "Оплатить тестовый заказ" }).click();
    await expect(page.getByText(/проверяем платёж/i)).toBeVisible();
    await expect(page.getByRole("dialog")).toContainText("На чём основано", { timeout: 60_000 });
  });
});

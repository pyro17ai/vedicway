import { expect, test } from "playwright/test";

import { createMoscowChart, openTestCheckout, waitForExplanation } from "./helpers";


test.describe("Возврат из YooKassa", () => {
  test("query не открывает отчёт, а задержанное подтверждение восстанавливается после reload", async ({ page }) => {
    test.setTimeout(180_000);
    await createMoscowChart(page);
    await waitForExplanation(page);
    const chartUrl = new URL(page.url());
    const chartId = chartUrl.pathname.split("/").pop()!;
    const freeResource = await page.evaluate(async (id) => {
      const response = await fetch(`/api/v1/charts/${id}`);
      return response.json();
    }, chartId);

    await openTestCheckout(page);
    const checkoutUrl = page.url();
    const paymentState = await page.evaluate(() => JSON.parse(sessionStorage.getItem("vedicway:payment-return") ?? "null"));
    expect(paymentState.chartId).toBe(chartId);

    await page.goto(`/chart/${chartId}?payment_return=${paymentState.purchaseId}&success=true`);
    await expect(page.getByText(/проверяем платёж по данным YooKassa/i)).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.reload();
    await expect(page.getByText(/проверяем платёж по данным YooKassa/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Открыть полный текст" }).first()).toBeVisible({ timeout: 45_000 });

    const chartResourcePattern = `**/api/v1/charts/${chartId}`;
    await page.route(chartResourcePattern, async (route) => {
      const response = await route.fetch();
      const resource = await response.json();
      if (resource.entitlement?.report_full) {
        resource.interpretation = freeResource.interpretation;
        resource.entitlement = {
          ...resource.entitlement,
          report_ready: false,
        };
      }
      await route.fulfill({ response, json: resource });
    });
    await page.goto(`${checkoutUrl}?delay_ms=1500`);
    await page.getByRole("button", { name: "Оплатить тестовый заказ" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: /оплата подтверждена.*готовим полный отчёт/i }),
    ).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Готовим полный текст" }).first()).toBeDisabled();

    await page.unroute(chartResourcePattern);
    await page.reload();
    await expect(page.getByRole("dialog")).toContainText("На чём основано", { timeout: 60_000 });
  });
});

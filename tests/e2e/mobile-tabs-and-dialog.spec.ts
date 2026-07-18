// spec: docs/testing/chart-result-e2e.plan.md
import { expect, test } from "playwright/test";

import { createMoscowChart, waitForExplanation } from "./helpers";

test.describe("Мобильная навигация", () => {
  test("mobile-tabs-and-dialog", async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 390, height: 844 });
    // 1. Открыть результат на ширине 390 px и перейти по трём вкладкам клавиатурой.
    await createMoscowChart(page);
    const chartTab = page.getByRole("tab", { name: /карта/i });
    await chartTab.focus();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/tab=explanation/);
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/tab=questions/);
    const saveButton = page.getByRole("button", { name: "Сохранить", exact: true }).first();
    await expect(saveButton).toBeVisible({ timeout: 45_000 });
    await saveButton.click();
    const statusButton = page.locator(".question-card__status > button").first();
    await expect(statusButton).toBeVisible();
    await statusButton.click();
    await page.getByRole("button", { name: "Обдумываю", exact: true }).click();
    await expect(statusButton).toHaveText("Обдумываю");
    expect(await page.locator("body").evaluate((body) => body.scrollWidth <= window.innerWidth)).toBe(true);

    // 2. Открыть paywall и проверить фокус-ловушку.
    await waitForExplanation(page);
    await page.getByRole("button", { name: "Подробнее" }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const closeButton = dialog.getByRole("button", { name: "Вернуться к карте" });
    await closeButton.focus();
    await page.keyboard.press("Shift+Tab");
    await expect(dialog.getByRole("button", { name: /открыть полный отчёт/i })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });
});

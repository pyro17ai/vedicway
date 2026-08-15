// spec: docs/testing/chart-result-e2e.plan.md
import { expect, test } from "playwright/test";

import { createMoscowChart, waitForExplanation } from "./helpers";

test.describe("Мобильное первое чтение", () => {
  test("mobile-topic-and-payment-dialog", async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 390, height: 844 });
    // 1. Выбранная тема открывает и фокусирует своё краткое объяснение.
    await createMoscowChart(page);
    await waitForExplanation(page);
    await page.getByRole("button", { name: "Характер", exact: true }).click();
    const character = page.locator("#domain-card-character");
    await expect(character).toBeVisible();
    await expect(character).toBeFocused();
    await expect(page).toHaveURL(/domain=character/);
    expect(await page.locator("body").evaluate((body) => body.scrollWidth <= window.innerWidth)).toBe(true);

    // 2. Поля и кнопки оплаты находятся в одном scroll-контейнере.
    await character.getByRole("button", { name: "Открыть полный текст" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const closeButton = dialog.getByRole("button", { name: "Закрыть окно оплаты" });
    const email = dialog.getByRole("textbox", { name: /email для чека и готового результата/i });
    const submit = dialog.getByRole("button", { name: /перейти к оплате/i });
    await expect(submit).not.toBeInViewport();
    await submit.scrollIntoViewIfNeeded();
    await submit.click();
    await expect(email).toBeFocused();
    await expect(email).toBeInViewport();

    // 3. Фокус-ловушка сохраняет явный возврат из окна оплаты.
    await closeButton.focus();
    await page.keyboard.press("Shift+Tab");
    await expect(submit).toBeFocused();
    await dialog.getByRole("button", { name: "Вернуться к разбору" }).click();
    await expect(dialog).toBeHidden();
    await expect(page).toHaveURL(/tab=explanation/);
    await expect(page).not.toHaveURL(/domain=/);
    await expect(page.getByRole("button", { name: "Все темы", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".domain-card")).toHaveCount(8);
  });
});

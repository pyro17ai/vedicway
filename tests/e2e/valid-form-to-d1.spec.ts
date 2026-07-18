// spec: docs/testing/chart-result-e2e.plan.md
import { expect, test } from "playwright/test";

import { createMoscowChart } from "./helpers";

test.describe("Создание карты", () => {
  test("valid-form-to-d1", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    // 1. Ввести имя, дату, время и выбрать Москву из серверных подсказок.
    await createMoscowChart(page);
    const skipLink = page.getByRole("link", { name: "Перейти к содержанию результата" });
    await skipLink.focus();
    await expect(skipLink).toBeFocused();
    await expect(page.getByRole("gridcell")).toHaveCount(12);
    await expect(page.getByRole("gridcell", { name: /Скорпион, дом 1, лагна/ })).toBeVisible();

    // 2. Выбрать ячейку и включить профессиональный режим.
    await page.getByRole("gridcell").first().click();
    await expect(page.getByText("Выбранный знак", { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "Профессионально" }).click();
    await expect(page).toHaveURL(/tab=chart&varga=D1&mode=expert/);
    await expect(page.getByText(/°\d{2}′/).first()).toBeVisible();
    expect(consoleErrors).toEqual([]);
  });
});

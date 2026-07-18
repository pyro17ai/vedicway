import { expect, test } from "playwright/test";

test.describe("Публичные тексты демонстрации", () => {
  test("не раскрывают внутренние технические названия в трёх вкладках результата", async ({ page }) => {
    await page.goto("/");

    const showcase = page.getByRole("region", { name: "Пример результата натальной карты" });
    await expect(showcase).toBeVisible();
    const panel = showcase.getByRole("tabpanel");

    await panel.getByRole("button", { name: "Исходные данные" }).click();
    await expect(panel.getByRole("region", { name: "Исходные данные карты" })).toContainText(
      "Сидерический зодиак",
    );

    await showcase.getByRole("tab", { name: "Объяснение" }).click();
    await panel.getByRole("button", { name: "Подробнее" }).first().click();
    await expect(panel.getByText(/готовый отчёт раскрывает тему через положение карты/i)).toBeVisible();

    await showcase.getByRole("tab", { name: "Вопросы к себе" }).click();
    await panel.getByRole("button", { name: "Почему этот вопрос?" }).first().click();
    await expect(panel.locator(".question-card__why")).toBeVisible();

    const publicCopy = (await showcase.textContent()) ?? "";
    expect(publicCopy).not.toMatch(/codex|pyjhora|\bmcp\b|get_rasi_chart|get_vimsottari_dasha/i);
  });
});

import { expect, test } from "playwright/test";

test.describe("Публичные тексты демонстрации", () => {
  test("не раскрывают внутренние технические названия в трёх вкладках результата", async ({ page }) => {
    await page.goto("/");

    const showcase = page.getByRole("region", { name: "Пример результата натальной карты" });
    await expect(showcase).toBeVisible();

    await showcase.getByRole("gridcell", { name: /Скорпион, дом 1, лагна/i }).click();
    await expect(showcase.getByText("Выбранный знак · дом 1")).toBeVisible();
    await expect(showcase.getByText("Скорпион · Лагна")).toBeVisible();

    await showcase.getByRole("tab", { name: "Объяснение" }).click();
    await showcase.getByRole("button", { name: "Подробнее" }).first().click();
    await expect(showcase.getByText(/готовый отчёт раскрывает тему через положение карты/i)).toBeVisible();
    await expect(showcase.getByText("Лагна · Скорпион · дом 1")).toBeVisible();

    await showcase.getByRole("tab", { name: "Вопросы к себе" }).click();
    await showcase.getByRole("button", { name: "Почему этот вопрос?" }).first().click();
    await expect(showcase.getByText(/Луна · Рак · 25,7398°/i)).toBeVisible();
    await expect(showcase.getByText("Источник: Положения основной карты D1")).toBeVisible();

    await expect(showcase).not.toContainText("get_rasi_chart");
    await expect(showcase).not.toContainText("get_vimsottari_dasha");
    await expect(showcase).not.toContainText(/Hermes|Codex|PyJHora|MCP|искусственн/i);
  });
});

import { expect, test } from "playwright/test";

test.describe("Публичные тексты демонстрации", () => {
  test("не раскрывают внутренние технические названия в трёх вкладках результата", async ({ page }) => {
    await page.goto("/");

    const showcase = page.getByRole("region", { name: "Пример результата натальной карты" });
    await expect(showcase).toBeVisible();

    const data = showcase.getByRole("region", { name: "Расчётные данные карты" });
    await data.getByRole("tab", { name: "Аспекты" }).click();
    await expect(data.getByText(/основание: положения основной карты D1/i)).toBeVisible();

    await showcase.getByRole("tab", { name: "Объяснение" }).click();
    await showcase.getByRole("button", { name: /Подробнее: Лагна в Скорпионе/ }).click();
    await expect(showcase.getByText("Источник: Положения основной карты D1")).toBeVisible();

    await showcase.getByRole("tab", { name: "Вопросы к себе" }).click();
    await showcase.getByRole("button", { name: "Работа", exact: true }).click();
    await showcase.getByRole("button", { name: /Периоды и работа/ }).click();
    await expect(showcase.getByText(/нужно завершить расчёт периодов Вимшоттари/i)).toBeVisible();

    await expect(showcase).not.toContainText("get_rasi_chart");
    await expect(showcase).not.toContainText("get_vimsottari_dasha");
  });
});

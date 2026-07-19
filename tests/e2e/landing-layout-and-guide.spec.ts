import { expect, test } from "playwright/test";

test("desktop-компоновка помещает форму и все три вкладки результата в один экран", async ({ page }) => {
  await page.setViewportSize({ width: 1569, height: 920 });
  await page.goto("/");

  await expect(page.getByRole("link", { name: "Главная", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Пример готового результата")).toBeVisible();

  const heroLayout = await page.evaluate(() => {
    const hero = document.querySelector<HTMLElement>(".hero")!.getBoundingClientRect();
    const form = document.querySelector<HTMLElement>(".chart-card")!.getBoundingClientRect();
    return { heroBottom: hero.bottom, formBottom: form.bottom, sectionHeight: hero.height };
  });
  expect(heroLayout.formBottom).toBeLessThan(heroLayout.heroBottom - 20);
  expect(heroLayout.sectionHeight).toBeLessThanOrEqual(920);

  const showcase = page.getByRole("region", { name: "Пример результата натальной карты" });
  await showcase.scrollIntoViewIfNeeded();
  const showcaseHeight = await showcase.evaluate((element) => element.getBoundingClientRect().height);
  expect(showcaseHeight).toBeLessThanOrEqual(920);

  for (const name of ["Натальная карта", "Объяснение", "Вопросы к себе"]) {
    await showcase.getByRole("tab", { name }).click();
    await page.waitForTimeout(260);
    const fit = await showcase.evaluate((element) => {
      const stage = element.querySelector<HTMLElement>(".results-stage")!.getBoundingClientRect();
      const content = element.querySelector<HTMLElement>(".result-workspace")!.getBoundingClientRect();
      return content.bottom <= stage.bottom + 1;
    });
    expect(fit).toBe(true);
  }
});

test("публичный гид не открывает редактор, а админка требует вход", async ({ page }) => {
  await page.setViewportSize({ width: 1569, height: 920 });
  await page.goto("/guide");

  await expect(page.getByRole("heading", { name: "Гид по астрологии" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Первые материалы готовятся" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Редактор статей" })).toHaveCount(0);

  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Вход в редакцию" })).toBeVisible();
  await expect(page.getByLabel("Рабочая почта")).toBeVisible();
  await expect(page.getByLabel("Пароль")).toBeVisible();
  await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();
});

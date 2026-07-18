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

test("гид начинает пустым, а редактор публикует полноценную статью", async ({ page }) => {
  await page.setViewportSize({ width: 1569, height: 920 });
  await page.goto("/guide");

  await expect(page.getByRole("heading", { name: "Гид по астрологии" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Первые материалы готовятся" })).toBeVisible();
  await page.getByRole("button", { name: "Редактор статей" }).click();
  await expect(page).toHaveURL(/\/guide\/editor$/);

  await page.getByLabel("Заголовок статьи").fill("Как читать первый дом натальной карты");
  await page.getByLabel("Лид").fill("Разбираем первый дом как отправную точку карты и связываем его знак с повседневными наблюдениями.");
  await page.getByLabel("Текст статьи").fill("Первый дом задаёт точку отсчёта всей натальной карты и описывает способ, которым человек проявляет себя в мире. Его чтение начинается со знака на восходе и продолжается через положение управителя.\n\n## С чего начать\n\nСначала найдите восходящий знак, затем посмотрите, где расположен его управитель. Сопоставьте эти два положения и только после этого переходите к отдельным деталям.");
  await page.getByLabel("Метаописание").fill("Пошаговое объяснение первого дома натальной карты: восходящий знак, управитель дома и порядок чтения основных показателей.");
  await page.getByRole("button", { name: /Опубликовать/ }).click();

  await expect(page.getByRole("status")).toHaveText("Статья опубликована и появилась в гиде.");
  await page.getByRole("button", { name: "Гид" }).click();
  await expect(page.getByRole("heading", { name: "Как читать первый дом натальной карты" })).toBeVisible();
  await page.getByRole("button", { name: /Читать: Как читать первый дом/ }).click();

  await expect(page).toHaveURL(/\/guide\/kak-chitat-pervyy-dom-natalnoy-karty$/);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", /\/guide\/kak-chitat-pervyy-dom-natalnoy-karty$/);
  const structuredData = await page.locator("#vedicway-article-jsonld").evaluate((element) => element.textContent ?? "");
  expect(structuredData).toContain('"@type":"Article"');
});

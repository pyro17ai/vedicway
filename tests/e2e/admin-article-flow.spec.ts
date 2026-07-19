import { resolve } from "node:path";

import { expect, test } from "playwright/test";

const imagePath = resolve("public/assets/avatar-01.png");

test("администратор публикует статью с обложкой и изображением внутри текста", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/admin");
  await page.getByLabel("Рабочая почта").fill("editor@vedicway.ru");
  await page.getByLabel("Пароль").fill("playwright-admin-password-2026");
  await page.getByRole("button", { name: "Войти" }).click();

  await expect(page.getByRole("heading", { name: "Состояние редакции" })).toBeVisible();
  await page.getByRole("button", { name: "Новый материал" }).click();

  await page.getByLabel("Заголовок статьи").fill("Как читать первый дом ведической карты");
  await page.getByLabel(/^Лид/).fill(
    "Практический разбор первого дома помогает увидеть лагну, её управителя и главные опоры характера.",
  );
  await page.getByLabel("Описание обложки").fill("Южноиндийская натальная карта и знак восходящего дома");
  await page.locator(".admin-cover input[type=file]").setInputFiles(imagePath);
  await expect(page.getByRole("status")).toContainText("Изображение подготовлено");

  const body = [
    "Первый дом, или лагна, задаёт точку отсчёта всей ведической карты. Его читают вместе со знаком восходящего дома, положением управителя лагны и влиянием планет.",
    "## С чего начать",
    "Сначала определите знак лагны. Затем найдите его управителя и проверьте дом, знак и связи с другими планетами. Такой порядок сохраняет смысл карты и не сводит трактовку к одному символу.",
  ].join("\n\n");
  await page.locator("textarea.admin-content").fill(body);
  page.once("dialog", (dialog) => dialog.accept("Фрагмент южноиндийской карты с отмеченной лагной"));
  await page.locator(".admin-content-header input[type=file]").setInputFiles(imagePath);
  await expect(page.getByRole("status")).toContainText("Изображение подготовлено");

  await page.getByLabel(/^SEO-заголовок/).fill("Как читать первый дом ведической карты | VedicWay");
  await page.getByLabel(/^Метаописание/).fill(
    "Разбираем первый дом ведической натальной карты: знак лагны, управителя, планеты и последовательность чтения без отрыва от всей карты.",
  );
  await page.getByRole("button", { name: "Опубликовать" }).click();
  await expect(page.getByRole("status")).toContainText("Материал опубликован в гиде.");

  await page.goto("/guide");
  const card = page.getByRole("heading", { name: "Как читать первый дом ведической карты" });
  await expect(card).toBeVisible();
  const articleCard = card.locator("xpath=ancestor::article");
  await expect(articleCard.locator("img")).toHaveAttribute("alt", "Южноиндийская натальная карта и знак восходящего дома");
  await articleCard.getByRole("link", { name: /Как читать первый дом/ }).first().click();

  await expect(page).toHaveURL(/\/guide\/kak-chitat-pervyy-dom-vedicheskoy-karty$/);
  await expect(page.getByRole("heading", { name: "Как читать первый дом ведической карты" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "С чего начать" })).toBeVisible();
  await expect(page.locator(".article-reading__body img")).toHaveAttribute(
    "alt",
    "Фрагмент южноиндийской карты с отмеченной лагной",
  );
});

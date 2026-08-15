import { expect, test, type Page } from "playwright/test";

async function expectInlineFaqAnswers(page: Page) {
  const section = page.locator(".faq-section");
  const triggers = page.locator(".faq-item__trigger");

  await section.scrollIntoViewIfNeeded();
  await expect(triggers).toHaveCount(5);
  await expect(triggers.nth(0)).toHaveAttribute("aria-expanded", "false");

  for (let index = 0; index < 5; index += 1) {
    await triggers.nth(index).click();
    const item = page.locator(".faq-item").nth(index);
    const answer = item.locator(".faq-item__answer");
    await expect(answer).toBeVisible();
    const expandedCount = await triggers.evaluateAll((elements) =>
      elements.filter((element) => element.getAttribute("aria-expanded") === "true").length,
    );
    const placement = await item.evaluate((element) => {
      const trigger = element.querySelector<HTMLElement>(".faq-item__trigger")!;
      const inlineAnswer = element.querySelector<HTMLElement>(".faq-item__answer")!;
      const triggerRect = trigger.getBoundingClientRect();
      const answerRect = inlineAnswer.getBoundingClientRect();
      const itemRect = element.getBoundingClientRect();
      return {
        startsAfterQuestion: answerRect.top >= triggerRect.bottom - 1,
        endsInsideItem: answerRect.bottom <= itemRect.bottom + 1,
      };
    });

    expect(placement).toEqual({ startsAfterQuestion: true, endsInsideItem: true });
    expect(expandedCount).toBe(1);
    await expect(triggers.nth(index)).toHaveAttribute("aria-expanded", "true");
    await triggers.nth(index).click();
    await expect(answer).toBeHidden();
    await expect(page.locator(".faq-list")).toHaveAttribute("data-open-index", "none");
  }
}

test("FAQ открывает ответ под вопросом на desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1672, height: 941 });
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Часто задаваемые вопросы" })).toBeVisible();
  await page.locator(".faq-section").scrollIntoViewIfNeeded();
  await page.locator(".faq-section").screenshot({ path: "artifacts/faq-desktop-1672x941.png" });
  await expectInlineFaqAnswers(page);
  await expect(page.locator(".faq-legal-footer")).toBeVisible();
  await expect(page.getByRole("link", { name: "Политика обработки персональных данных" })).toHaveAttribute("href", "/legal/privacy");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

});

test("FAQ остаётся стабильным и читаемым на mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.locator(".faq-section").scrollIntoViewIfNeeded();
  await page.locator(".faq-section").screenshot({ path: "artifacts/faq-mobile-390x844.png" });
  await expectInlineFaqAnswers(page);
  await expect(page.locator(".faq-legal-footer")).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

});

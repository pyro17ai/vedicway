import { expect, test, type Page } from "playwright/test";

async function expectStableFaqHeight(page: Page) {
  const section = page.locator(".faq-section");
  const triggers = page.locator(".faq-item__trigger");

  await section.scrollIntoViewIfNeeded();
  await expect(triggers).toHaveCount(5);
  await expect(triggers.nth(0)).toHaveAttribute("aria-expanded", "false");

  const initialHeight = await section.evaluate((element) => element.getBoundingClientRect().height);

  for (let index = 0; index < 5; index += 1) {
    await triggers.nth(index).click();
    await page.waitForTimeout(280);

    const currentHeight = await section.evaluate((element) => element.getBoundingClientRect().height);
    const expandedCount = await triggers.evaluateAll((elements) =>
      elements.filter((element) => element.getAttribute("aria-expanded") === "true").length,
    );
    const activeItemFits = await page.locator(".faq-item").nth(index).evaluate(
      (element) => element.scrollHeight <= element.clientHeight + 1,
    );

    expect(Math.abs(currentHeight - initialHeight)).toBeLessThanOrEqual(0.5);
    expect(expandedCount).toBe(1);
    expect(activeItemFits).toBe(true);
    await expect(triggers.nth(index)).toHaveAttribute("aria-expanded", "true");
  }

  await triggers.nth(4).click();
  await page.waitForTimeout(280);
  expect(await triggers.evaluateAll((elements) => elements.filter((element) => element.getAttribute("aria-expanded") === "true").length)).toBe(0);
  await expect(page.locator(".faq-list")).toHaveAttribute("data-open-index", "none");
}

test("FAQ повторяет референс и не меняет высоту на desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1672, height: 941 });
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Часто задаваемые вопросы" })).toBeVisible();
  await page.locator(".faq-section").scrollIntoViewIfNeeded();
  await page.locator(".faq-section").screenshot({ path: "artifacts/faq-desktop-1672x941.png" });
  await expectStableFaqHeight(page);
  await expect(page.locator(".faq-legal-footer")).toBeVisible();
  await expect(page.getByRole("link", { name: "Политика обработки персональных данных" })).toHaveAttribute("href", "/legal/privacy-policy");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

});

test("FAQ остаётся стабильным и читаемым на mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.locator(".faq-section").scrollIntoViewIfNeeded();
  await page.locator(".faq-section").screenshot({ path: "artifacts/faq-mobile-390x844.png" });
  await expectStableFaqHeight(page);
  await expect(page.locator(".faq-legal-footer")).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

});

import { expect, test, type Page } from "playwright/test";

const TEST_EMAIL = "private-owner@example.test";
const ACCEPTED_RESPONSE = JSON.stringify({ status: "accepted" });

async function assertEmailStayedOutOfBrowserState(page: Page, consoleMessages: string[]) {
  expect(page.url()).not.toContain(TEST_EMAIL);
  expect(consoleMessages.join("\n")).not.toContain(TEST_EMAIL);

  const browserState = await page.evaluate(() => ({
    local: { ...localStorage },
    session: { ...sessionStorage },
    cookies: document.cookie,
  }));
  expect(JSON.stringify(browserState)).not.toContain(TEST_EMAIL);
}

test.describe("Восстановление доступа и обращения по персональным данным", () => {
  test("обе формы показывают нейтральный результат и не оставляют email в браузере", async ({ page }) => {
    const consoleMessages: string[] = [];
    page.on("console", (message) => consoleMessages.push(message.text()));

    const submitted: Array<{ url: string; body: unknown }> = [];
    await page.route("**/api/v1/access/recovery", async (route) => {
      submitted.push({ url: route.request().url(), body: route.request().postDataJSON() });
      await route.fulfill({ status: 202, contentType: "application/json", body: ACCEPTED_RESPONSE });
    });
    await page.route("**/api/v1/privacy/requests", async (route) => {
      submitted.push({ url: route.request().url(), body: route.request().postDataJSON() });
      await route.fulfill({ status: 202, contentType: "application/json", body: ACCEPTED_RESPONSE });
    });

    await page.goto("/access/recovery");
    await page.getByRole("button", { name: "Отклонить необязательные cookies" }).click();
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, nofollow, noarchive");
    await page.getByRole("textbox", { name: "Email" }).fill(TEST_EMAIL);
    await page.getByRole("button", { name: "Отправить запрос" }).click();
    await expect(page.getByRole("status")).toContainText("Если заказ найден");
    await assertEmailStayedOutOfBrowserState(page, consoleMessages);

    await page.goto("/privacy/request");
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, nofollow, noarchive");
    await page.getByLabel("Предмет обращения").selectOption("erase");
    await page.getByRole("textbox", { name: "Email" }).fill(TEST_EMAIL);
    await page.getByRole("button", { name: "Отправить запрос" }).click();
    await expect(page.getByRole("status")).toContainText("Обращение принято");
    await assertEmailStayedOutOfBrowserState(page, consoleMessages);

    expect(submitted).toEqual([
      { url: expect.stringMatching(/\/api\/v1\/access\/recovery$/), body: { email: TEST_EMAIL } },
      { url: expect.stringMatching(/\/api\/v1\/privacy\/requests$/), body: { type: "erase", email: TEST_EMAIL } },
    ]);
  });
});

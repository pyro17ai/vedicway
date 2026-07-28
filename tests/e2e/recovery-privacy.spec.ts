import { expect, test, type Page } from "playwright/test";
import { execFileSync } from "node:child_process";
import { delimiter, resolve } from "node:path";

const TEST_EMAIL = "private-owner@example.test";
const ACCEPTED_RESPONSE = JSON.stringify({ status: "accepted" });

function pythonOutput(source: string, args: string[]): string {
  const python = process.env.VEDICWAY_E2E_PYTHON ?? "python";
  const pythonPath = [resolve("backend/src"), process.env.PYTHONPATH].filter(Boolean).join(delimiter);
  return execFileSync(python, ["-c", source, ...args], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: pythonPath },
    encoding: "utf8",
  }).trim();
}

function createMagicLink(chartId: string): string {
  const dataDir = process.env.VEDICWAY_E2E_DATA_DIR;
  if (!dataDir) throw new Error("VEDICWAY_E2E_DATA_DIR is missing");
  return pythonOutput(
    "import sys; from vedicway_backend.store import Store; print(Store(sys.argv[1]).create_magic_link(sys.argv[2]))",
    [dataDir, chartId],
  );
}

function magicState(token: string, chartId: string): { usedAt: string | null; accessCount: number } {
  const dataDir = process.env.VEDICWAY_E2E_DATA_DIR;
  if (!dataDir) throw new Error("VEDICWAY_E2E_DATA_DIR is missing");
  const raw = pythonOutput(
    [
      "import hashlib,json,sqlite3,sys",
      "db=sqlite3.connect(sys.argv[1] + '/vedicway.sqlite3')",
      "db.row_factory=sqlite3.Row",
      "token_hash=hashlib.sha256(sys.argv[2].encode()).hexdigest()",
      "link=db.execute('SELECT used_at FROM magic_links WHERE token_hash=?',(token_hash,)).fetchone()",
      "access=db.execute('SELECT COUNT(*) AS count FROM chart_access WHERE chart_id=?',(sys.argv[3],)).fetchone()",
      "print(json.dumps({'usedAt': link['used_at'] if link else None, 'accessCount': access['count']}))",
    ].join(";"),
    [dataDir, token, chartId],
  );
  return JSON.parse(raw) as { usedAt: string | null; accessCount: number };
}

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

  test("почтовый scanner GET не расходует ссылку, доступ выдаёт только явный POST", async ({
    browser,
    page,
    request,
  }) => {
    const legalResponse = await request.get("/api/v1/legal/config");
    expect(legalResponse.ok()).toBeTruthy();
    const legalConfig = await legalResponse.json();
    const created = await request.post("/api/v1/charts", {
      data: {
        local_date: "1998-09-15",
        local_time: "17:28",
        place_id: "ru-moscow-524901",
        legal: {
          personal_data: true,
          personal_data_version: legalConfig.versions.personal_data_consent,
          terms: true,
          terms_version: legalConfig.versions.terms,
        },
      },
      headers: { "Idempotency-Key": `recovery-e2e-${Date.now()}` },
    });
    expect(created.status()).toBe(202);
    const chartId = String((await created.json()).chart_id);
    const token = createMagicLink(chartId);
    const magicPath = `/api/v1/magic-links/${token}`;
    const baseline = magicState(token, chartId);

    const scannerContext = await browser.newContext({
      baseURL: process.env.PLAYWRIGHT_BASE_URL
        ?? `http://127.0.0.1:${process.env.VEDICWAY_E2E_FRONTEND_PORT ?? "5183"}`,
    });
    const scannerPage = await scannerContext.newPage();
    await scannerPage.goto(magicPath);
    await expect(scannerPage).toHaveURL(/\/access\/confirm$/);
    await expect(scannerPage.locator('meta[name="robots"]')).toHaveAttribute(
      "content",
      "noindex, nofollow, noarchive",
    );
    expect(magicState(token, chartId)).toEqual(baseline);
    expect((await scannerContext.cookies()).some((cookie) => cookie.name === "vw_session")).toBe(false);

    await page.goto(magicPath);
    await expect(page).toHaveURL(/\/access\/confirm$/);
    const rejectCookies = page.getByRole("button", { name: "Отклонить необязательные cookies" });
    if (await rejectCookies.isVisible()) await rejectCookies.click();
    await page.getByRole("button", { name: "Открыть материалы" }).click();
    await expect(page).toHaveURL(new RegExp(`/chart/${chartId}$`));

    const granted = magicState(token, chartId);
    expect(granted.usedAt).not.toBeNull();
    expect(granted.accessCount).toBe(baseline.accessCount + 1);

    const scannerRejectCookies = scannerPage.getByRole("button", {
      name: "Отклонить необязательные cookies",
    });
    if (await scannerRejectCookies.isVisible()) await scannerRejectCookies.click();
    const replayResponse = scannerPage.waitForResponse(
      (response) => response.url().endsWith("/api/v1/magic-links/confirm"),
    );
    await scannerPage.getByRole("button", { name: "Открыть материалы" }).click();
    expect((await replayResponse).status()).toBe(401);
    expect((await scannerContext.cookies()).some((cookie) => cookie.name === "vw_session")).toBe(false);
    expect(magicState(token, chartId)).toEqual(granted);
    await scannerContext.close();
  });
});

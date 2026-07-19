import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RecoveryPage } from "./RecoveryPage";

describe("RecoveryPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "vw_magic_csrf=; Max-Age=0; Path=/";
  });

  it("отправляет email и показывает одинаковый нейтральный результат", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "accepted" }), { status: 202 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<RecoveryPage kind="access" onNavigate={vi.fn()} />);
    await user.type(screen.getByRole("textbox", { name: "Email" }), "buyer@example.com");
    await user.click(screen.getByRole("button", { name: "Отправить запрос" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Если заказ найден");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/access/recovery",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "buyer@example.com" }),
      }),
    );
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      "content",
      "noindex, nofollow, noarchive",
    );
  });

  it("отправляет отдельный запрос на удаление персональных данных", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "accepted" }), { status: 202 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<RecoveryPage kind="privacy" onNavigate={vi.fn()} />);
    await user.selectOptions(screen.getByLabelText("Предмет обращения"), "erase");
    await user.type(screen.getByRole("textbox", { name: "Email" }), "owner@example.ru");
    await user.click(screen.getByRole("button", { name: "Отправить запрос" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Обращение принято");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/privacy/requests",
      expect.objectContaining({
        body: JSON.stringify({ type: "erase", email: "owner@example.ru" }),
      }),
    );
  });

  it("подтверждает magic-link только явной POST-формой с double-submit токеном", () => {
    const csrf = "csrf-token-with-at-least-thirty-two-characters";
    document.cookie = `vw_magic_csrf=${encodeURIComponent(csrf)}; Path=/; SameSite=Strict`;

    render(<RecoveryPage kind="confirm" onNavigate={vi.fn()} />);

    const form = screen.getByRole("button", { name: "Открыть материалы" }).closest("form");
    expect(form).toHaveAttribute("method", "post");
    expect(form).toHaveAttribute("action", "/api/v1/magic-links/confirm");
    expect(form?.querySelector('input[name="csrf_token"]')).toHaveValue(csrf);
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      "content",
      "noindex, nofollow, noarchive",
    );
    expect(document.querySelector('meta[name="referrer"]')).toHaveAttribute(
      "content",
      "no-referrer",
    );
  });
});

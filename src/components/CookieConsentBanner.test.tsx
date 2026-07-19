import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { readCookiePreferences } from "../lib/legal";
import { CookieConsentBanner } from "./CookieConsentBanner";

describe("CookieConsentBanner", () => {
  beforeEach(() => window.localStorage.clear());

  it("не включает необязательную аналитику без явного согласия", async () => {
    const user = userEvent.setup();
    render(<CookieConsentBanner />);

    const dialog = screen.getByRole("dialog", { name: "Настройки cookies" });
    expect(dialog).toBeInTheDocument();
    expect(dialog).not.toHaveAttribute("aria-modal");
    await user.click(screen.getByRole("button", { name: "Отклонить необязательные" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(readCookiePreferences()?.analytics).toBe(false);
  });

  it("закрывается с отказом по Escape, когда фокус находится в плашке", async () => {
    const user = userEvent.setup();
    render(<CookieConsentBanner />);

    const settings = screen.getByRole("button", { name: "Настроить" });
    settings.focus();
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(readCookiePreferences()?.analytics).toBe(false);
  });

  it("сохраняет выбранную категорию и повторно открывает настройки", async () => {
    const user = userEvent.setup();
    render(<CookieConsentBanner />);

    await user.click(screen.getByRole("button", { name: "Настроить" }));
    await user.click(screen.getByRole("checkbox", { name: /Аналитические/ }));
    await user.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    expect(readCookiePreferences()?.analytics).toBe(true);

    window.dispatchEvent(new CustomEvent("vedicway:open-cookie-settings"));
    expect(await screen.findByRole("dialog", { name: "Настройки cookies" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Аналитические/ })).toBeChecked();
  });
});

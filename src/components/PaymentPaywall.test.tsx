import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PaymentPublicConfig } from "../lib/chart-api";
import { PaymentPaywall } from "./PaymentPaywall";


const config: PaymentPublicConfig = {
  product_code: "full_report_v1",
  title: "Полный персональный отчёт",
  price_minor: 99_000,
  currency: "RUB",
  offer_version: "2026-07-18",
  offer_url: "https://vedicway.example/legal/offer",
  privacy_url: "https://vedicway.example/legal/privacy",
};


function renderPaywall(overrides: Partial<Parameters<typeof PaymentPaywall>[0]> = {}) {
  const onClose = vi.fn();
  const onCheckout = vi.fn().mockResolvedValue(undefined);
  render(
    <PaymentPaywall
      title="Отношения и близость"
      summary="Подробное чтение вашей карты"
      config={config}
      onClose={onClose}
      onCheckout={onCheckout}
      {...overrides}
    />,
  );
  return { onClose, onCheckout };
}


describe("PaymentPaywall", () => {
  it("requires a valid receipt email and explicit offer consent", async () => {
    const user = userEvent.setup();
    const { onCheckout } = renderPaywall();

    await user.click(screen.getByRole("button", { name: /перейти к оплате/i }));
    expect(screen.getByText(/укажите email для чека/i)).toBeInTheDocument();
    expect(screen.getByText(/подтвердите оферту/i)).toBeInTheDocument();
    expect(onCheckout).not.toHaveBeenCalled();

    await user.type(screen.getByRole("textbox", { name: /email для чека/i }), "broken");
    await user.click(screen.getByRole("checkbox", { name: /принимаю условия/i }));
    await user.click(screen.getByRole("button", { name: /перейти к оплате/i }));
    expect(screen.getByText(/проверьте адрес email/i)).toBeInTheDocument();
  });

  it("links to legal documents but keeps access recovery outside the paywall", () => {
    renderPaywall();
    expect(screen.getByRole("link", { name: /условия оферты/i })).toHaveAttribute("href", config.offer_url);
    expect(screen.getByRole("link", { name: /политикой обработки данных/i })).toHaveAttribute("href", config.privacy_url);
    expect(screen.getByRole("link", { name: /условия оферты/i })).toHaveAttribute("target", "_blank");
    expect(screen.queryByRole("link", { name: /восстановить доступ/i })).not.toBeInTheDocument();
  });

  it("locks double submission while checkout is being created", async () => {
    const user = userEvent.setup();
    let resolveCheckout: (() => void) | undefined;
    const onCheckout = vi.fn(() => new Promise<void>((resolve) => { resolveCheckout = resolve; }));
    renderPaywall({ onCheckout });

    await user.type(screen.getByRole("textbox", { name: /email для чека/i }), "buyer@example.com");
    await user.click(screen.getByRole("checkbox", { name: /принимаю условия/i }));
    await user.click(screen.getByRole("button", { name: /перейти к оплате/i }));

    expect(screen.getByRole("button", { name: /создаём платёж/i })).toBeDisabled();
    expect(onCheckout).toHaveBeenCalledTimes(1);
    resolveCheckout?.();
    await waitFor(() => expect(onCheckout).toHaveBeenCalledTimes(1));
  });

  it("shows a safe provider error and lets the user retry", async () => {
    const user = userEvent.setup();
    const onCheckout = vi.fn().mockRejectedValueOnce(new Error("Платёжный сервис временно не отвечает"));
    renderPaywall({ onCheckout });

    await user.type(screen.getByRole("textbox", { name: /email для чека/i }), "buyer@example.com");
    await user.click(screen.getByRole("checkbox", { name: /принимаю условия/i }));
    await user.click(screen.getByRole("button", { name: /перейти к оплате/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Платёжный сервис временно не отвечает");
    expect(screen.getByRole("button", { name: /повторить/i })).toBeEnabled();
  });

  it("focuses the title and closes on Escape", async () => {
    const user = userEvent.setup();
    const { onClose } = renderPaywall();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Отношения и близость" })).toHaveFocus());
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

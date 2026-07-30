import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  afterEach(() => {
    window.history.replaceState({}, "", "/");
  });

  it("собирает первый экран по продуктовому контракту", () => {
    const { container } = render(<App />);

    expect(screen.getByText("ВЕДИЧЕСКАЯ НАТАЛЬНАЯ КАРТА")).toBeInTheDocument();
    expect(screen.getByText("ОНЛАЙН")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /получите вашу натальную карту/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Главная" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Гид по астрологии" })).toHaveAttribute("href", "/guide");
    expect(screen.getByText("Пример готового результата")).toBeInTheDocument();
    expect(screen.getByText("Проверяемый расчёт")).toBeInTheDocument();
    expect(container.querySelector("#natal-chart-form")).toBeInTheDocument();
    expect(container.querySelectorAll("main")).toHaveLength(1);
    expect(
      screen.getByRole("region", { name: "Пример результата натальной карты" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Часто задаваемые вопросы" })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/Hermes|Codex|PyJHora|MCP|искусственн/i);
  });

  it("открывает старый адрес восстановления внутри главной hero-формы", () => {
    window.history.replaceState({}, "", "/access/recovery");
    render(<App />);

    expect(screen.getByText("ВЕДИЧЕСКАЯ НАТАЛЬНАЯ КАРТА")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Восстановить оплаченный разбор" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Email оплаты" })).toBeInTheDocument();
  });

  it.each([
    ["/legal/offer", "Публичная оферта и пользовательское соглашение"],
    ["/legal/privacy", "Политика обработки персональных данных"],
  ])("открывает платёжный legal-маршрут %s вместо 404", (path, heading) => {
    window.history.replaceState({}, "", path);
    render(<App />);

    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Страница не найдена" })).not.toBeInTheDocument();
  });

  it("открывает локальную страницу методологии", () => {
    window.history.replaceState({}, "", "/methodology");
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "Метод расчёта натальной карты" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/PyJHora 4\.7\.0/)).toBeInTheDocument();
  });
});

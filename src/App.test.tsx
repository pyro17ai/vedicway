import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("собирает первый экран по продуктовому контракту", () => {
    const { container } = render(<App />);

    expect(screen.getByText("ПОЗНАЙ СЕБЯ")).toBeInTheDocument();
    expect(screen.getByText("ЧЕРЕЗ КОСМОС")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /получите вашу натальную карту/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Главная" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Гид по астрологии" })).toHaveAttribute("href", "/guide");
    expect(screen.getByText("Пример готового результата")).toBeInTheDocument();
    expect(container.querySelectorAll("[data-avatar]")).toHaveLength(4);
    expect(container.querySelectorAll("main")).toHaveLength(1);
    expect(
      screen.getByRole("region", { name: "Пример результата натальной карты" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Часто задаваемые вопросы" })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/Hermes|Codex|PyJHora|MCP|искусственн/i);
  });
});

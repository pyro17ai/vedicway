import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { FaqSection } from "./FaqSection";

describe("FaqSection", () => {
  it("показывает пять вопросов и начинает полностью закрытым", () => {
    render(<FaqSection />);

    const triggers = within(screen.getByTestId("faq-list")).getAllByRole("button");
    expect(triggers).toHaveLength(5);
    expect(triggers.every((trigger) => trigger.getAttribute("aria-expanded") === "false")).toBe(true);
    expect(screen.getByTestId("faq-list")).toHaveAttribute("data-open-index", "none");
    expect(screen.queryByRole("region", { name: /Что такое натальная карта/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Блог" })).toHaveAttribute("href", "/blog");
    expect(screen.getByRole("link", { name: "Метод" })).toHaveAttribute("href", "/methodology");
    expect(screen.getByRole("link", { name: "Запрос по персональным данным" })).toHaveAttribute("href", "/privacy/request");
  });

  it("открывает выбранный ответ и закрывает его повторным нажатием", async () => {
    const user = userEvent.setup();
    render(<FaqSection />);

    const triggers = within(screen.getByTestId("faq-list")).getAllByRole("button");
    await user.click(triggers[3]);

    expect(triggers[3]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("faq-list")).toHaveAttribute("data-open-index", "3");
    const answer = screen.getByRole("region", { name: /Чем ведическая астрология/i });
    expect(answer).toHaveTextContent("сидерический зодиак");
    expect(triggers[3].closest(".faq-item")).toContainElement(answer);
    expect(triggers.filter((trigger) => trigger.getAttribute("aria-expanded") === "true")).toHaveLength(1);

    await user.click(triggers[3]);

    expect(triggers.every((trigger) => trigger.getAttribute("aria-expanded") === "false")).toBe(true);
    expect(screen.getByTestId("faq-list")).toHaveAttribute("data-open-index", "none");
    expect(screen.queryByRole("region", { name: /Чем ведическая астрология/i })).not.toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { FaqSection } from "./FaqSection";

describe("FaqSection", () => {
  it("показывает пять вопросов и начинает полностью закрытым", () => {
    render(<FaqSection />);

    const triggers = screen.getAllByRole("button");
    expect(triggers).toHaveLength(5);
    expect(triggers.every((trigger) => trigger.getAttribute("aria-expanded") === "false")).toBe(true);
    expect(screen.getByTestId("faq-list")).toHaveAttribute("data-open-index", "none");
  });

  it("открывает выбранный ответ и закрывает его повторным нажатием", async () => {
    const user = userEvent.setup();
    render(<FaqSection />);

    const triggers = screen.getAllByRole("button");
    await user.click(triggers[3]);

    expect(triggers[3]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("faq-list")).toHaveAttribute("data-open-index", "3");
    expect(triggers.filter((trigger) => trigger.getAttribute("aria-expanded") === "true")).toHaveLength(1);

    await user.click(triggers[3]);

    expect(triggers.every((trigger) => trigger.getAttribute("aria-expanded") === "false")).toBe(true);
    expect(screen.getByTestId("faq-list")).toHaveAttribute("data-open-index", "none");
  });
});

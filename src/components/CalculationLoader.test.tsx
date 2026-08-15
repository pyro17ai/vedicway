import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CalculationLoader } from "./CalculationLoader";

describe("CalculationLoader", () => {
  it.each([
    ["chart", "Строим натальную карту"],
    ["explanation", "Готовим объяснение и вопросы"],
    ["questions", "Готовим объяснение и вопросы"],
    ["rectification", "Сопоставляем варианты времени"],
  ] as const)("показывает доступный статус %s", (variant, title) => {
    render(<CalculationLoader variant={variant} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(title);
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveAttribute("aria-atomic", "true");
    expect(status).toHaveAttribute("aria-busy", "true");
  });
});

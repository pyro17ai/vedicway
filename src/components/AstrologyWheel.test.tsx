import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AstrologyWheel } from "./AstrologyWheel";

describe("AstrologyWheel", () => {
  it("строит двенадцать секторов только из оранжевой линейной графики", () => {
    const { container } = render(<AstrologyWheel />);
    const wheel = container.querySelector('[data-testid="astrology-wheel"]');

    expect(wheel).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelectorAll("[data-spoke]")).toHaveLength(12);
    expect(wheel?.outerHTML).not.toMatch(/#fff|#ffffff|white|rgb\(255/i);
  });
});

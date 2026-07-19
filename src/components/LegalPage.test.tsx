import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LegalPage } from "./LegalPage";

const legalConfig = {
  operator_name: "ООО ВедикВей",
  operator_address: "Москва, ул. Примерная, 1",
  inn: "7700000000",
  ogrn: "1000000000000",
  privacy_email: "privacy@example.ru",
  configured: true,
  interpretation_processor_enabled: true,
  interpretation_processor_configured: true,
  interpretation_processor_name: "Example Processor LLC",
  interpretation_processor_address: "123 Example Street, Dublin",
  interpretation_processor_country: "Ирландия",
  interpretation_processor_purpose: "подготовка персонализированного объяснения карты",
  interpretation_processor_data_categories: [
    "расчётные астрологические показатели",
    "связи между показателями",
  ],
  interpretation_processor_cross_border: true,
};

afterEach(() => vi.unstubAllGlobals());

function mockLegalConfig() {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(legalConfig),
  }));
}

describe("LegalPage interpretation processor disclosure", () => {
  it("называет обработчика, цель, категории и трансграничную передачу в политике", async () => {
    mockLegalConfig();
    render(<LegalPage kind="privacy" onNavigate={() => undefined} />);

    const heading = await screen.findByRole("heading", { name: "5. Передача и инфраструктура" });
    const section = heading.closest("section");
    expect(section).not.toBeNull();
    const policy = within(section as HTMLElement);
    expect(policy.getByText(/Example Processor LLC/)).toBeInTheDocument();
    expect(section).toHaveTextContent("подготовка персонализированного объяснения карты");
    expect(section).toHaveTextContent("расчётные астрологические показатели; связи между показателями");
    expect(section).toHaveTextContent("Передача этому обработчику является трансграничной");
  });

  it("повторяет раскрытие обработчика в отдельном согласии", async () => {
    mockLegalConfig();
    render(<LegalPage kind="consent" onNavigate={() => undefined} />);

    const heading = await screen.findByRole("heading", { name: "Разрешённые действия" });
    expect(heading.closest("section")).toHaveTextContent("Example Processor LLC");
    expect(screen.getByText("Редакция от 2026-07-19-v2")).toBeInTheDocument();
  });
});

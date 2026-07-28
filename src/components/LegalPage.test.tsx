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
  it("публикует оферту с порядком акцепта и законными правами потребителя", async () => {
    mockLegalConfig();
    render(<LegalPage kind="terms" onNavigate={() => undefined} />);

    expect(await screen.findByText(/Акцептом оферты для платной услуги/)).toBeInTheDocument();
    expect(screen.getByRole("heading", {
      name: "Публичная оферта и пользовательское соглашение",
    })).toBeInTheDocument();
    expect(screen.getByText(/фактически понесённых расходов/)).toBeInTheDocument();
    expect(screen.getByText(/десятидневный срок/)).toBeInTheDocument();
  });

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
    expect(screen.getByText("Редакция от 2026-07-28")).toBeInTheDocument();
  });

  it("не заявляет обработку имени, которого больше нет в форме и хранилище", async () => {
    mockLegalConfig();
    const { container } = render(<LegalPage kind="privacy" onNavigate={() => undefined} />);

    await screen.findByRole("heading", { name: "2. Какие данные обрабатываются" });
    expect(container).not.toHaveTextContent("имя для подписи результата");
  });
});

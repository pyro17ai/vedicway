import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LegalPage } from "./LegalPage";

const legalConfig = {
  operator_name: "ООО ВедикВей",
  operator_address: "Москва, ул. Примерная, 1",
  inn: "7700000000",
  ogrn: "1000000000000",
  privacy_email: "privacy@example.ru",
  configured: true,
};

afterEach(() => vi.unstubAllGlobals());

function mockLegalConfig() {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(legalConfig),
  }));
}

describe("LegalPage", () => {
  it("публикует оферту с порядком акцепта и законными правами потребителя", async () => {
    mockLegalConfig();
    render(<LegalPage kind="terms" onNavigate={() => undefined} />);

    expect(await screen.findByText(/Акцептом оферты для платной услуги/)).toBeInTheDocument();
    expect(screen.getByRole("heading", {
      name: "Публичная оферта и пользовательское соглашение",
    })).toBeInTheDocument();
    expect(screen.getByText(/фактически понесённых расходов/)).toBeInTheDocument();
    expect(screen.getByText(/десятидневный срок/)).toBeInTheDocument();
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      "content",
      "noindex, follow, noarchive",
    );
  });

  it("описывает инфраструктуру без упоминаний ИИ-провайдера", async () => {
    mockLegalConfig();
    const { container } = render(<LegalPage kind="privacy" onNavigate={() => undefined} />);

    const heading = await screen.findByRole("heading", { name: "5. Передача и инфраструктура" });
    const section = heading.closest("section");
    expect(section).not.toBeNull();
    expect(section).toHaveTextContent("Основная запись, систематизация, накопление и хранение");
    expect(container).not.toHaveTextContent(/OpenAI|искусственн(?:ый|ого) интеллект/i);
  });

  it("публикует новую редакцию отдельного согласия без названия стороннего генератора", async () => {
    mockLegalConfig();
    const { container } = render(<LegalPage kind="consent" onNavigate={() => undefined} />);

    const heading = await screen.findByRole("heading", { name: "Разрешённые действия" });
    expect(heading.closest("section")).toHaveTextContent("Передача допускается только в объёме");
    expect(screen.getByText("Редакция от 2026-07-31")).toBeInTheDocument();
    expect(container).not.toHaveTextContent(/OpenAI|искусственн(?:ый|ого) интеллект/i);
  });

  it("не заявляет обработку имени, которого больше нет в форме и хранилище", async () => {
    mockLegalConfig();
    const { container } = render(<LegalPage kind="privacy" onNavigate={() => undefined} />);

    await screen.findByRole("heading", { name: "2. Какие данные обрабатываются" });
    expect(container).not.toHaveTextContent("имя для подписи результата");
  });
});

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ResultsShowcase } from "./ResultsShowcase";

describe("ResultsShowcase", () => {
  it("показывает демонстрацию в виде реального рабочего кабинета без профиля", () => {
    render(<ResultsShowcase />);

    const showcase = screen.getByRole("region", { name: "Пример результата натальной карты" });

    expect(within(showcase).queryByText("После расчёта")).not.toBeInTheDocument();
    expect(within(showcase).getByText(/15 сентября 1998 · 17:28 · Москва, Россия · UTC\+4/)).toBeInTheDocument();
    expect(within(showcase).getByRole("grid", { name: "Южноиндийская карта D1" })).toBeInTheDocument();
    expect(within(showcase).getByText("С чего начать")).toBeInTheDocument();
    expect(within(showcase).queryByLabelText(/Текущий профиль/i)).not.toBeInTheDocument();
    expect(within(showcase).queryByText(/Демонстрационный профиль|Александр/)).not.toBeInTheDocument();
    expect(within(showcase).queryByText("VedicWay")).not.toBeInTheDocument();
  });

  it("сохраняет три сгенерированные иконки и доступные состояния rail-вкладок", () => {
    render(<ResultsShowcase />);

    const expected = [
      ["Натальная карта", "/assets/results-nav-chart-light.png"],
      ["Объяснение", "/assets/results-nav-explanation-light.png"],
      ["Вопросы к себе", "/assets/results-nav-questions-light.png"],
    ] as const;

    expected.forEach(([name, src], index) => {
      const tab = screen.getByRole("tab", { name });
      expect(tab.querySelector(`img[src="${src}"]`)).toBeInTheDocument();
      expect(tab).toHaveAttribute("aria-selected", index === 0 ? "true" : "false");
    });
  });

  it("переключает панели rail кликом и по клавиатуре", async () => {
    const user = userEvent.setup();
    render(<ResultsShowcase />);

    const chartTab = screen.getByRole("tab", { name: "Натальная карта" });
    chartTab.focus();

    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("tab", { name: "Объяснение" })).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Объяснение карты" })).toBeInTheDocument();

    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Вопросы к себе" })).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Вопросы к себе" })).toBeInTheDocument();

    await user.keyboard("{Home}");
    expect(chartTab).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Натальная карта" })).toBeInTheDocument();

    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("tab", { name: "Вопросы к себе" })).toHaveFocus();
  });

  it("даёт читать D1 через выбор знака в едином понятном режиме", async () => {
    const user = userEvent.setup();
    render(<ResultsShowcase />);

    await user.click(screen.getByRole("gridcell", { name: /Скорпион, дом 1, лагна/i }));
    expect(screen.getByText("Выбранный знак · дом 1")).toBeInTheDocument();
    expect(screen.getByText("Скорпион · Лагна")).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "Профессионально" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Режим просмотра")).not.toBeInTheDocument();
  });

  it("оставляет демонстрационные объяснения некликабельными и возвращает пользователя к карте", async () => {
    const user = userEvent.setup();
    render(<ResultsShowcase />);

    await user.click(screen.getByRole("tab", { name: "Объяснение" }));

    expect(screen.queryAllByRole("button", { name: /Подробнее/ })).toHaveLength(0);
    expect(screen.queryByText(/Этот фрагмент показывает, как готовый отчёт раскрывает тему/)).not.toBeInTheDocument();
    expect(screen.getByText("Лагна · Скорпион · дом 1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Вернуться к карте" }));
    expect(screen.getByRole("tab", { name: "Натальная карта" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Натальная карта" })).toBeInTheDocument();
  });

  it("сохраняет вопрос, фильтрует список и раскрывает его основание", async () => {
    const user = userEvent.setup();
    render(<ResultsShowcase />);

    await user.click(screen.getByRole("tab", { name: "Вопросы к себе" }));
    const saveButtons = screen.getAllByRole("button", { name: "Сохранить" });
    await user.click(saveButtons[0]);
    expect(screen.getByRole("button", { name: "Сохранено" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Сохранённые" }));
    expect(screen.getAllByRole("heading")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Почему этот вопрос?" }));
    expect(screen.getByText(/Луна · Рак · 25,7398° · Ашлеша · пада 3/)).toBeInTheDocument();
  });
});

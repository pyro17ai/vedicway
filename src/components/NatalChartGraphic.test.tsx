import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { NatalChartGraphic } from "./NatalChartGraphic";

describe("NatalChartGraphic", () => {
  it("строит fixed-sign South Indian grid и распределяет 12 объектов по контрольному snapshot", () => {
    const { container } = render(<NatalChartGraphic />);
    const chart = screen.getByRole("region", { name: "Южноиндийская карта D1" });

    expect(within(chart).getAllByRole("button", { name: /^Знак / })).toHaveLength(12);
    expect(container.querySelectorAll("[data-chart-object]")).toHaveLength(12);
    expect(within(screen.getByRole("button", { name: "Знак Рак" })).getByText(/Луна/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Знак Рак" })).getByText(/Сатурн/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Знак Дева" })).getByText(/Солнце/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Знак Дева" })).getByText(/Венера/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Знак Дева" })).getByText(/Кету/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Знак Весы" })).getByText(/Марс/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Знак Весы" })).getByText(/Меркурий/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Знак Весы" })).getByText(/Юпитер/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Знак Рыбы" })).getByText(/Раху/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Знак Скорпион" })).getByText(/Лагна/)).toBeInTheDocument();
  });

  it("раскрывает точные данные выбранной ячейки без наложения на список объектов", async () => {
    const user = userEvent.setup();
    render(<NatalChartGraphic />);

    await user.click(screen.getByRole("button", { name: "Знак Рак" }));

    const popover = screen.getByRole("status", { name: "Детали знака Рак" });
    expect(within(popover).getByText("Луна · 25,7398° · Ашлеша · пада 3")).toBeInTheDocument();
    expect(within(popover).getByText("Сатурн · 28,8553° · Ашлеша · пада 4")).toBeInTheDocument();
    expect(within(popover).getByText("Источник: Положения основной карты D1")).toBeInTheDocument();
  });
});

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { searchCities } from "../lib/city-search";
import { BirthChartForm } from "./BirthChartForm";

vi.mock("../lib/city-search", () => ({
  searchCities: vi.fn(),
}));

const city = {
  id: 524901,
  label: "Москва, Москва, Россия",
  name: "Москва",
  country: "Россия",
  admin1: "Москва",
  latitude: 55.75222,
  longitude: 37.61556,
  timezone: "Europe/Moscow",
};

describe("BirthChartForm", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(searchCities).mockResolvedValue([city]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("показывает постоянные подписи и нативные поля даты и времени", () => {
    render(<BirthChartForm />);

    expect(screen.getByLabelText("Имя")).toBeInTheDocument();
    expect(screen.getByLabelText("Дата рождения")).toHaveAttribute("type", "date");
    expect(screen.getByLabelText("Время рождения")).toHaveAttribute("type", "time");
    expect(screen.getByRole("combobox", { name: "Место рождения" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /рассчитать карту/i })).toBeEnabled();
  });

  it("объясняет ошибки после отправки и переводит фокус к первому полю", async () => {
    render(<BirthChartForm />);

    fireEvent.click(screen.getByRole("button", { name: /рассчитать карту/i }));

    expect(screen.getByText("Введите имя")).toBeInTheDocument();
    expect(screen.getByText("Укажите дату рождения")).toBeInTheDocument();
    expect(screen.getByText("Укажите время рождения")).toBeInTheDocument();
    expect(screen.getByText("Выберите город из списка")).toBeInTheDocument();
    expect(screen.getByLabelText("Имя")).toHaveFocus();
  });

  it("откладывает поиск и выбирает город с клавиатуры", async () => {
    render(<BirthChartForm />);
    const combobox = screen.getByRole("combobox", { name: "Место рождения" });

    fireEvent.change(combobox, { target: { value: "Москва" } });
    expect(searchCities).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });

    expect(searchCities).toHaveBeenCalledWith("Москва", expect.any(AbortSignal));
    expect(screen.getByRole("option", { name: "Москва, Москва, Россия" })).toBeInTheDocument();

    fireEvent.keyDown(combobox, { key: "ArrowDown" });
    fireEvent.keyDown(combobox, { key: "Enter" });

    expect(combobox).toHaveValue("Москва, Москва, Россия");
  });

  it("подтверждает полностью заполненную форму без очистки данных", async () => {
    render(<BirthChartForm />);

    fireEvent.change(screen.getByLabelText("Имя"), { target: { value: "Анна" } });
    fireEvent.change(screen.getByLabelText("Дата рождения"), { target: { value: "1991-04-12" } });
    fireEvent.change(screen.getByLabelText("Время рождения"), { target: { value: "14:25" } });

    const combobox = screen.getByRole("combobox", { name: "Место рождения" });
    fireEvent.change(combobox, { target: { value: "Москва" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });
    screen.getByRole("option", { name: city.label });
    fireEvent.keyDown(combobox, { key: "ArrowDown" });
    fireEvent.keyDown(combobox, { key: "Enter" });

    fireEvent.click(screen.getByRole("button", { name: /рассчитать карту/i }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(screen.getByRole("status")).toHaveTextContent("Данные приняты");
    expect(screen.getByLabelText("Имя")).toHaveValue("Анна");
  });
});

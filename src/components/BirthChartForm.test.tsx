import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createChart } from "../lib/chart-api";
import { searchCities } from "../lib/city-search";
import { BirthChartForm } from "./BirthChartForm";

vi.mock("../lib/city-search", () => ({
  searchCities: vi.fn(),
}));

vi.mock("../lib/chart-api", async () => {
  const actual = await vi.importActual<typeof import("../lib/chart-api")>("../lib/chart-api");
  return { ...actual, createChart: vi.fn() };
});

const city = {
  id: "moscow-ru",
  label: "Москва, Россия",
  name: "Москва",
  country: "RU",
  countryCode: "RU",
  admin1: "Россия",
  latitude: 55.7558,
  longitude: 37.6173,
  timezone: "Europe/Moscow",
};

describe("BirthChartForm", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(searchCities).mockResolvedValue([city]);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("показывает постоянные подписи, нативные поля и требует отдельные согласия", () => {
    render(<BirthChartForm />);

    expect(screen.getByLabelText("Имя")).toBeInTheDocument();
    expect(screen.getByLabelText("Дата рождения")).toHaveAttribute("type", "date");
    expect(screen.getByLabelText("Время рождения")).toHaveAttribute("type", "time");
    expect(screen.getByRole("combobox", { name: "Место рождения" })).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: /рассчитать карту/i });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /согласие на обработку персональных данных/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /пользовательское соглашение/i }));
    expect(submit).toBeEnabled();
  });

  it("объясняет ошибки после отправки и переводит фокус к первому полю", () => {
    render(<BirthChartForm />);
    fireEvent.click(screen.getByRole("checkbox", { name: /согласие на обработку персональных данных/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /пользовательское соглашение/i }));
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
    expect(screen.getByRole("option", { name: city.label })).toBeInTheDocument();

    fireEvent.keyDown(combobox, { key: "ArrowDown" });
    fireEvent.keyDown(combobox, { key: "Enter" });

    fireEvent.click(screen.getByRole("checkbox", { name: /согласие на обработку персональных данных/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /пользовательское соглашение/i }));
    expect(combobox).toHaveValue(city.label);
  });

  it("отправляет подтверждённое место в BFF и передаёт созданный chart_id", async () => {
    const onChartCreated = vi.fn();
    vi.mocked(createChart).mockResolvedValueOnce({ chart_id: "chart-test-1" });
    render(<BirthChartForm onChartCreated={onChartCreated} />);

    fireEvent.change(screen.getByLabelText("Имя"), { target: { value: "Анна" } });
    fireEvent.change(screen.getByLabelText("Дата рождения"), { target: { value: "1991-04-12" } });
    fireEvent.change(screen.getByLabelText("Время рождения"), { target: { value: "14:25" } });
    const combobox = screen.getByRole("combobox", { name: "Место рождения" });
    fireEvent.change(combobox, { target: { value: "Москва" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });
    fireEvent.keyDown(combobox, { key: "ArrowDown" });
    fireEvent.keyDown(combobox, { key: "Enter" });

    fireEvent.click(screen.getByRole("checkbox", { name: /согласие на обработку персональных данных/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /пользовательское соглашение/i }));
    fireEvent.click(screen.getByRole("button", { name: /рассчитать карту/i }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(createChart).toHaveBeenCalledWith({
      localDate: "1991-04-12",
      localTime: "14:25",
      placeId: city.id,
      place: {
        displayName: city.label,
        countryCode: city.countryCode,
        latitude: city.latitude,
        longitude: city.longitude,
        timezone: city.timezone,
      },
      timeAccuracy: "exact",
      personalDataConsent: true,
      termsAccepted: true,
    });
    expect(onChartCreated).toHaveBeenCalledWith("chart-test-1");
    expect(screen.getByRole("status")).toHaveTextContent("Карта принята. Переходим к расчёту.");
    expect(screen.getByLabelText("Имя")).toHaveValue("Анна");
  });
});

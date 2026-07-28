import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChartCell, ChartSection } from "../lib/chart-api";
import { formatChartDegree, SouthIndianChart } from "./SouthIndianChart";

const signs = ["Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева", "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"];

function cells(): ChartCell[] {
  return signs.map((sign_label, sign_index) => ({
    sign_index,
    sign_code: `S${sign_index}`,
    sign_label,
    house_number: sign_index + 1,
    is_lagna: sign_index === 7,
    planets: sign_index === 1
      ? [
        { planet_code: "moon", label: "Луна", short_label: "Лу", classical: true, sign_index, sign_label, house_number: 2, longitude_in_sign: 12.8, total_longitude: 42.8, nakshatra: "Криттика", pada: 1, retrograde: false, source_path: "positions.moon" },
        { planet_code: "rahu", label: "Раху", short_label: "Ра", classical: true, sign_index, sign_label, house_number: 2, longitude_in_sign: 24.2, total_longitude: 54.2, nakshatra: "Рохини", pada: 3, retrograde: true, source_path: "positions.rahu" },
      ]
      : [],
  }));
}

const readySection: ChartSection = {
  section: "d1",
  status: "ready",
  data: { cells: cells(), ascendant: { sign_label: "Скорпион" } },
};

describe("SouthIndianChart", () => {
  it("строит двенадцать фиксированных знаков южноиндийской D1", () => {
    render(<SouthIndianChart section={readySection} varga="D1" mode="plain" selectedSign={null} onSelectSign={vi.fn()} />);

    expect(screen.getByRole("grid", { name: "Южноиндийская карта D1" })).toBeInTheDocument();
    expect(screen.getAllByRole("gridcell")).toHaveLength(12);
    expect(screen.getByRole("gridcell", { name: /Скорпион, дом 8, лагна/ })).toBeInTheDocument();
    expect(screen.getByRole("gridcell", { name: /Телец, дом 2, Луна, Раху/ })).toBeInTheDocument();
  });

  it("открывает доступное описание выбранной ячейки без пересчёта карты", () => {
    const onSelectSign = vi.fn();
    render(<SouthIndianChart section={readySection} varga="D1" mode="expert" selectedSign={1} onSelectSign={onSelectSign} />);

    expect(screen.getByText("Выбранный знак · дом 2")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("Луна · 12°48′ · Криттика");
    fireEvent.click(screen.getByRole("gridcell", { name: /Телец, дом 2/ }));
    expect(onSelectSign).toHaveBeenCalledWith(1);
  });

  it("объясняет выбранную лагну одним коротким предложением", () => {
    render(<SouthIndianChart section={readySection} varga="D1" mode="plain" selectedSign={7} onSelectSign={vi.fn()} />);

    expect(screen.getByText("Лагной называют восходящий в момент рождения знак, от которого отсчитываются дома натальной карты.")).toBeInTheDocument();
    expect(screen.queryByText(/профессиональном режиме/i)).not.toBeInTheDocument();
  });

  it("показывает карту-скелет до готовности D1", () => {
    render(<SouthIndianChart section={{ section: "d1", status: "queued" }} varga="D1" mode="plain" selectedSign={null} onSelectSign={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Строим основную карту");
  });

  it("не выводит несуществующую шестидесятую минуту", () => {
    expect(formatChartDegree(29.9999)).toBe("29°59′");
  });
});

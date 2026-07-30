import { useMemo } from "react";

import type { ChartCell, ChartSection, PlanetPosition } from "../lib/chart-api";
import { CalculationLoader } from "./CalculationLoader";

type SouthIndianChartProps = {
  section: ChartSection | null;
  varga: string;
  mode: "plain" | "expert";
  selectedSign: number | null;
  onSelectSign: (signIndex: number) => void;
};

const positions: Record<number, { row: number; column: number }> = {
  0: { row: 1, column: 1 },
  1: { row: 1, column: 2 },
  2: { row: 1, column: 3 },
  3: { row: 1, column: 4 },
  4: { row: 2, column: 4 },
  5: { row: 3, column: 4 },
  6: { row: 4, column: 4 },
  7: { row: 4, column: 3 },
  8: { row: 4, column: 2 },
  9: { row: 4, column: 1 },
  10: { row: 3, column: 1 },
  11: { row: 2, column: 1 },
};

function chartData(section: ChartSection | null) {
  const data = section?.data as { cells?: ChartCell[]; ascendant?: { sign_label?: string } } | undefined;
  return {
    cells: Array.isArray(data?.cells) ? data.cells : [],
    ascendant: data?.ascendant,
  };
}

export function formatChartDegree(value: number) {
  const totalMinutes = Math.min(29 * 60 + 59, Math.max(0, Math.floor(value * 60)));
  const degrees = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${degrees}°${String(minutes).padStart(2, "0")}′`;
}

function PlanetLine({ planet, mode }: { planet: PlanetPosition; mode: "plain" | "expert" }) {
  const detail = mode === "expert" ? ` ${formatChartDegree(planet.longitude_in_sign)}` : "";
  return (
    <span className={`south-chart__planet${planet.classical ? "" : " south-chart__planet--outer"}`}>
      <span className="south-chart__planet-name">{mode === "plain" ? planet.short_label : planet.label}</span>
      <span className="south-chart__planet-degree">{detail}</span>
      {planet.retrograde && <abbr title="ретроградная" aria-label="ретроградная">R</abbr>}
    </span>
  );
}

export function SouthIndianChart({ section, varga, mode, selectedSign, onSelectSign }: SouthIndianChartProps) {
  const { cells, ascendant } = useMemo(() => chartData(section), [section]);
  const selectedCell = cells.find((cell) => cell.sign_index === selectedSign) ?? null;

  if (!section || section.status === "queued" || section.status === "running") {
    return <CalculationLoader variant="chart" />;
  }

  if (section.status === "error" || section.status === "unavailable") {
    return <div className="workspace-notice workspace-notice--warning">Этот фрагмент карты пока недоступен. Основные готовые разделы сохранены.</div>;
  }

  return (
    <div className="south-chart-wrap">
      <div className="south-chart" role="grid" aria-label={`Южноиндийская карта ${varga}`}>
        {cells.map((cell) => {
          const position = positions[cell.sign_index];
          const selected = cell.sign_index === selectedSign;
          return (
            <button
              className={`south-chart__cell${selected ? " is-selected" : ""}${cell.is_lagna ? " is-lagna" : ""}`}
              key={cell.sign_index}
              type="button"
              role="gridcell"
              aria-pressed={selected}
              aria-label={`${cell.sign_label}, дом ${cell.house_number}${cell.is_lagna ? ", лагна" : ""}${cell.planets.length ? `, ${cell.planets.map((planet) => planet.label).join(", ")}` : ", пустая ячейка"}`}
              style={{ gridRow: position.row, gridColumn: position.column }}
              onClick={() => onSelectSign(cell.sign_index)}
            >
              <span className="south-chart__cell-heading">
                <span>{cell.sign_label}</span>
                <small>Дом {cell.house_number}</small>
              </span>
              {cell.is_lagna && <span className="south-chart__lagna">Лагна</span>}
              <span className="south-chart__planets">
                {cell.planets.map((planet) => <PlanetLine key={planet.planet_code} planet={planet} mode={mode} />)}
              </span>
            </button>
          );
        })}
        <div className="south-chart__center" aria-label={`${varga}, ${ascendant?.sign_label ?? ""}`}>
          <span className="south-chart__eyebrow">{varga} · Раши</span>
          <strong>{varga === "D1" ? "Основная карта" : `Дробная карта ${varga}`}</strong>
          <p>Южноиндийская фиксированная сетка знаков</p>
          <span className="south-chart__method">Лахири · дома от лагны</span>
        </div>
      </div>

      <div className="south-chart__selection" aria-live="polite">
        {selectedCell ? (
          <>
            <div>
              <span className="south-chart__selection-kicker">Выбранный знак · дом {selectedCell.house_number}</span>
              <strong>{selectedCell.sign_label}{selectedCell.is_lagna ? " · Лагна" : ""}</strong>
            </div>
            {selectedCell.is_lagna && (
              <p>Лагной называют восходящий в момент рождения знак, от которого отсчитываются дома натальной карты.</p>
            )}
            {selectedCell.planets.length ? (
              <ul>
                {selectedCell.planets.map((planet) => (
                  <li key={planet.planet_code}>
                    <b>{planet.label}</b> · {formatChartDegree(planet.longitude_in_sign)} · {planet.nakshatra}{planet.pada ? `, пада ${planet.pada}` : ""}
                  </li>
                ))}
              </ul>
            ) : !selectedCell.is_lagna && <p>В этом доме нет планет.</p>}
          </>
        ) : <p>Выберите знак, чтобы прочитать положения и точные координаты.</p>}
      </div>

      <table className="sr-only">
        <caption>Текстовая таблица южноиндийской карты {varga}</caption>
        <thead><tr><th>Знак</th><th>Дом</th><th>Планеты</th></tr></thead>
        <tbody>{cells.map((cell) => <tr key={cell.sign_index}><td>{cell.sign_label}{cell.is_lagna ? " (Лагна)" : ""}</td><td>{cell.house_number}</td><td>{cell.planets.map((planet) => planet.label).join(", ") || "Нет"}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

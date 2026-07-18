import { useState } from "react";

import {
  demoPlanets,
  demoSnapshot,
  formatDegree,
  southIndianSigns,
} from "./results-demo-data";

export function NatalChartGraphic() {
  const [selectedRasi, setSelectedRasi] = useState<number | null>(null);
  const selectedSign = southIndianSigns.find((sign) => sign.rasiIndex === selectedRasi);
  const selectedPlanets = demoPlanets.filter((planet) => planet.rasiIndex === selectedRasi);

  return (
    <section
      className="natal-chart"
      role="region"
      aria-label="Южноиндийская карта D1"
    >
      <div className="natal-chart__frame">
        <div className="natal-chart__grid">
          {southIndianSigns.map((sign) => {
            const planets = demoPlanets.filter((planet) => planet.rasiIndex === sign.rasiIndex);
            const isAscendant = sign.rasiIndex === 8;

            return (
              <button
                className={`natal-chart__cell${selectedRasi === sign.rasiIndex ? " is-selected" : ""}`}
                key={sign.rasiIndex}
                type="button"
                aria-label={`Знак ${sign.name}`}
                aria-pressed={selectedRasi === sign.rasiIndex}
                style={{ gridRow: sign.row, gridColumn: sign.column }}
                onClick={() => setSelectedRasi(selectedRasi === sign.rasiIndex ? null : sign.rasiIndex)}
              >
                <span className="natal-chart__house">{sign.rasiIndex}</span>
                <span className="natal-chart__sign-line">
                  <b aria-hidden="true">{sign.glyph}</b>
                  <span>{sign.name}</span>
                </span>
                <span className="natal-chart__rule" aria-hidden="true" />
                <span className="natal-chart__objects">
                  {isAscendant && <span className="natal-chart__lagna">ASC · Лагна</span>}
                  {planets.map((planet) => (
                    <span
                      className={`natal-chart__object${planet.additional ? " natal-chart__object--additional" : ""}`}
                      data-chart-object
                      key={planet.id}
                    >
                      <span aria-hidden="true">{planet.glyph}</span> {planet.name}
                    </span>
                  ))}
                </span>
              </button>
            );
          })}

          <div className="natal-chart__center" aria-label="Параметры карты">
            <span className="natal-chart__kicker">D1 · RĀŚI</span>
            <strong>Южноиндийская карта</strong>
            <p>Знаки зафиксированы<br />планеты сгруппированы по rasi</p>
            <span className="natal-chart__method">Lahiri · whole-sign</span>
            <i aria-hidden="true" />
          </div>
        </div>
      </div>

      <p className="natal-chart__hint">
        Нажмите на знак, чтобы увидеть точные координаты объектов.
      </p>

      {selectedSign && (
        <div
          className="natal-chart__detail"
          role="status"
          aria-label={`Детали знака ${selectedSign.name}`}
        >
          <div>
            <span className="natal-chart__detail-glyph" aria-hidden="true">{selectedSign.glyph}</span>
            <div>
              <small>Выбранный знак</small>
              <strong>{selectedSign.name}</strong>
            </div>
          </div>
          <div className="natal-chart__detail-list">
            {selectedSign.rasiIndex === 8 && (
              <p>Лагна · {formatDegree(demoSnapshot.ascendant.degree)} · {demoSnapshot.ascendant.nakshatra}</p>
            )}
            {selectedPlanets.length > 0 ? (
              selectedPlanets.map((planet) => (
                <p key={planet.id}>
                  {planet.name} · {formatDegree(planet.degree)} · {planet.nakshatra} · пада {planet.pada}
                </p>
              ))
            ) : (
              <p>В этом знаке нет объектов.</p>
            )}
          </div>
          <small>Источник: {demoSnapshot.source}</small>
        </div>
      )}
    </section>
  );
}

import { useRef, useState, type KeyboardEvent } from "react";
import {
  ArrowLeft,
  Bookmark,
  ChevronDown,
  ChevronRight,
  Download,
  Pencil,
  Sparkles,
} from "lucide-react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

import type { ChartSection, PlanetPosition } from "../lib/chart-api";
import { SouthIndianChart, formatChartDegree } from "./SouthIndianChart";
import {
  demoPlanets,
  demoQuestions,
  demoSnapshot,
  southIndianSigns,
  wholeSignHouses,
} from "./results-demo-data";

type ResultTab = "chart" | "explanation" | "questions";
type DemoMode = "plain" | "expert";

const resultTabs = [
  { id: "chart", label: "Натальная карта", icon: "/assets/results-nav-chart.png" },
  { id: "explanation", label: "Объяснение", icon: "/assets/results-nav-explanation.png" },
  { id: "questions", label: "Вопросы к себе", icon: "/assets/results-nav-questions.png" },
] as const;

const demoPlanetPositions: PlanetPosition[] = demoPlanets.map((planet) => ({
  planet_code: planet.id,
  label: planet.name,
  short_label: planet.name,
  classical: !planet.additional,
  sign_index: planet.rasiIndex - 1,
  sign_label: planet.sign,
  house_number: wholeSignHouses.find((house) => house.sign === planet.sign)?.number ?? 1,
  longitude_in_sign: planet.degree,
  total_longitude: (planet.rasiIndex - 1) * 30 + planet.degree,
  nakshatra: planet.nakshatra,
  pada: planet.pada,
  retrograde: false,
  source_path: "demo.d1.planets",
}));

const demoD1: ChartSection = {
  section: "d1",
  status: "ready",
  data: {
    ascendant: { sign_label: demoSnapshot.ascendant.sign },
    cells: southIndianSigns.map((sign) => ({
      sign_index: sign.rasiIndex - 1,
      sign_code: String(sign.rasiIndex),
      sign_label: sign.name,
      house_number: wholeSignHouses.find((house) => house.sign === sign.name)?.number ?? 1,
      is_lagna: sign.name === demoSnapshot.ascendant.sign,
      planets: demoPlanetPositions.filter((planet) => planet.sign_index === sign.rasiIndex - 1),
    })),
  },
};

type DemoDomain = {
  id: string;
  sectionLabel: string;
  title: string;
  summary: string;
  evidence: string;
  state?: "ready" | "pending";
};

const demoDomains: DemoDomain[] = [
  {
    id: "character",
    sectionLabel: "Характер",
    title: "Внутренний стержень",
    summary: "Лагна задаёт отправную точку карты и помогает увидеть, с какой позиции человек входит в события своей жизни.",
    evidence: "Лагна · Скорпион · дом 1",
  },
  {
    id: "inner-support",
    sectionLabel: "Внутренняя опора",
    title: "Эмоциональная безопасность",
    summary: "Луна показывает, какие условия помогают почувствовать опору, восстановить силы и не терять контакт со своими потребностями.",
    evidence: "Луна · Рак · Ашлеша · пада 3",
  },
  {
    id: "relationships",
    sectionLabel: "Отношения",
    title: "Взаимность и личные границы",
    summary: "Раздел соединяет дом партнёрства с положениями планет, которые участвуют в теме близости и договорённостей.",
    evidence: "7 дом · Телец · дома от лагны",
  },
  {
    id: "family-home",
    sectionLabel: "Семья и дом",
    title: "Привычная среда",
    summary: "Здесь собраны указания на повседневную среду, чувство дома и то, как устроена потребность в устойчивости.",
    evidence: "4 дом · Водолей · дома от лагны",
  },
  {
    id: "work",
    sectionLabel: "Работа",
    title: "Практический ритм",
    summary: "Карта помогает наблюдать, как человек выстраивает усилие, распределяет внимание и выбирает способ действовать в задачах.",
    evidence: "Солнце и Венера · Дева",
  },
  {
    id: "money",
    sectionLabel: "Деньги",
    title: "Ресурсы и ориентиры",
    summary: "Разбор объединяет второй дом и его управителя, чтобы дать язык для наблюдения за отношением к личным ресурсам.",
    evidence: "2 дом · Стрелец · дома от лагны",
  },
  {
    id: "learning",
    sectionLabel: "Обучение",
    title: "Система знаний",
    summary: "В этой теме карта связывает девятый дом с привычками мышления, выбором наставников и личными ориентирами.",
    evidence: "9 дом · Рак · дома от лагны",
  },
  {
    id: "current-period",
    sectionLabel: "Текущий период",
    title: "Периоды Вимшоттари",
    summary: "Даты махадаш и антардаш добавляются после отдельного расчёта периодов и никогда не подменяются текстом по основной карте.",
    evidence: "Периоды требуют отдельного расчёта",
    state: "pending",
  },
];

function ChartResult({ onOpenExplanation }: { onOpenExplanation: () => void }) {
  const [mode, setMode] = useState<DemoMode>("plain");
  const [selectedSign, setSelectedSign] = useState<number | null>(null);
  const [showInputDetails, setShowInputDetails] = useState(false);
  const visiblePlanets = demoPlanetPositions.filter((planet) => mode === "expert" || planet.classical);

  return (
    <div className="result-workspace result-workspace--chart workspace-panel">
      <header className="workspace-header result-workspace-header">
        <div>
          <span className="workspace-header__kicker">Ваша карта</span>
          <h2>Натальная карта</h2>
          <p>{demoSnapshot.date} · {demoSnapshot.time} · {demoSnapshot.place} · {demoSnapshot.timezone}</p>
        </div>
        <div className="workspace-header__controls result-workspace-header__controls">
          <button
            className="result-demo-edit"
            type="button"
            aria-expanded={showInputDetails}
            aria-controls="result-input-details"
            onClick={() => setShowInputDetails((value) => !value)}
          >
            <Pencil aria-hidden="true" /> Исходные данные
          </button>
          <label className="workspace-select">
            <span>Варга</span>
            <select aria-label="Варга демонстрации" value="D1" onChange={() => undefined}>
              <option value="D1">D1</option>
            </select>
          </label>
          <div className="mode-switch" aria-label="Режим просмотра">
            <button type="button" className={mode === "plain" ? "is-active" : ""} onClick={() => setMode("plain")}>Понятно</button>
            <button type="button" className={mode === "expert" ? "is-active" : ""} onClick={() => setMode("expert")}>Профессионально</button>
          </div>
        </div>
      </header>

      {showInputDetails && (
        <section className="result-demo-input-details" id="result-input-details" aria-label="Исходные данные карты">
          <p><small>Дата и время</small>{demoSnapshot.date} · {demoSnapshot.time}</p>
          <p><small>Место</small>{demoSnapshot.place} · {demoSnapshot.timezone}</p>
          <p><small>Метод</small>Сидерический зодиак · айанамша {demoSnapshot.ayanamsa} · дома от лагны</p>
        </section>
      )}

      <div className="chart-scene-grid result-chart-scene">
        <section className="chart-visual-panel">
          <SouthIndianChart
            section={demoD1}
            varga="D1"
            mode={mode}
            selectedSign={selectedSign}
            onSelectSign={(sign) => setSelectedSign((current) => current === sign ? null : sign)}
          />
        </section>

        <aside className="chart-insight-panel">
          <section className="insight-card">
            <span className="insight-card__eyebrow">С чего начать</span>
            <h3>Сначала посмотрите на лагну и Луну</h3>
            <p>Лагна задаёт отсчёт домов, а Луна помогает заметить эмоциональную опору. Выберите знак в квадрате, чтобы увидеть положения и координаты.</p>
            <button type="button" className="text-action" onClick={onOpenExplanation}>
              Перейти к объяснениям <ChevronRight aria-hidden="true" />
            </button>
          </section>

          <section className="position-table">
            <h3>Ключевые положения</h3>
            <ul>
              {visiblePlanets.slice(0, mode === "expert" ? 12 : 7).map((planet) => (
                <li key={planet.planet_code}>
                  <span>{planet.label}</span>
                  <span>{planet.sign_label}</span>
                  <b>{formatChartDegree(planet.longitude_in_sign)}</b>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>

      <div className="chart-lower-grid">
        <section className="data-strip">
          <h3>Панчанг</h3>
          <dl>
            <div><dt>Накшатра Луны</dt><dd>{demoSnapshot.moon.nakshatra}</dd></div>
            <div><dt>Пада</dt><dd>{demoSnapshot.moon.pada}</dd></div>
            <div><dt>Лунный знак</dt><dd>{demoSnapshot.moon.sign}</dd></div>
          </dl>
        </section>
        <section className="data-strip">
          <h3>Периоды Вимшоттари</h3>
          <p>Периоды считаются отдельным модулем. Готовый раздел покажет махадаши, антардаши и их даты без ручных допущений.</p>
        </section>
        <section className="data-strip">
          <h3>Метод</h3>
          <p>Сидерический зодиак · айанамша {demoSnapshot.ayanamsa} · дома от лагны. Положения рассчитываются для указанного времени и места рождения.</p>
        </section>
      </div>
    </div>
  );
}

function ExplanationResult({ onReturnToChart }: { onReturnToChart: () => void }) {
  const [activeDomain, setActiveDomain] = useState<string | null>(null);
  const [openedDomain, setOpenedDomain] = useState<string | null>(null);
  const visibleDomains = activeDomain ? demoDomains.filter((domain) => domain.id === activeDomain) : demoDomains;

  return (
    <div className="result-workspace result-workspace--explanation workspace-panel">
      <header className="workspace-header result-workspace-header">
        <div>
          <span className="workspace-header__kicker">Первое чтение</span>
          <h2>Объяснение карты</h2>
          <p>Выводы связаны с видимыми положениями карты, а разделы с отдельным расчётом честно показывают своё состояние.</p>
        </div>
        <div className="workspace-header__controls result-workspace-header__controls">
          <button className="result-demo-edit" type="button" onClick={onReturnToChart}>
            <ArrowLeft aria-hidden="true" /> Вернуться к карте
          </button>
          <div className="domain-filter" aria-label="Фильтр тем карты">
            <button type="button" className={!activeDomain ? "is-active" : ""} onClick={() => setActiveDomain(null)}>Все темы</button>
            {demoDomains.slice(0, 4).map((domain) => (
              <button
                type="button"
                key={domain.id}
                className={activeDomain === domain.id ? "is-active" : ""}
                onClick={() => setActiveDomain(domain.id)}
              >
                {domain.sectionLabel}
              </button>
            ))}
          </div>
        </div>
      </header>

      <section className="overview-card">
        <div>
          <span className="overview-card__eyebrow">Главный рисунок</span>
          <h3>Карта как система взаимосвязанных ориентиров</h3>
          <p>Здесь не обещают готовый сценарий жизни. Разбор связывает положения, дома и периоды, чтобы человек мог наблюдать собственные устойчивые паттерны.</p>
        </div>
        <button type="button" className="text-action" onClick={() => setActiveDomain("character")}>
          Открыть первую тему <ChevronRight aria-hidden="true" />
        </button>
      </section>

      <section className="domain-grid" aria-label="Темы готового отчёта">
        {visibleDomains.map((domain) => {
          const isOpened = openedDomain === domain.id;
          return (
            <article className={`domain-card${domain.state === "pending" ? " domain-card--insufficient" : ""}`} key={domain.id}>
              <div className="domain-card__topline">
                <span>{domain.sectionLabel}</span>
                <small>{domain.state === "pending" ? "Нужен расчёт" : "Опора в карте"}</small>
              </div>
              <h3>{domain.title}</h3>
              <p>{domain.summary}</p>
              {domain.state === "pending" && <p className="domain-card__limit">Точные даты появятся после расчёта периодов.</p>}
              <div className="evidence-chips">
                <span className="result-evidence-chip">{domain.evidence}</span>
              </div>
              <button
                type="button"
                className="text-action"
                aria-expanded={isOpened}
                aria-controls={`demo-domain-detail-${domain.id}`}
                onClick={() => setOpenedDomain(isOpened ? null : domain.id)}
              >
                {isOpened ? "Свернуть" : "Подробнее"} <ChevronRight aria-hidden="true" />
              </button>
              {isOpened && (
                <p className="result-domain-detail" id={`demo-domain-detail-${domain.id}`}>
                  Этот фрагмент показывает, как готовый отчёт раскрывает тему через положение карты, а не через общий текст без основания.
                </p>
              )}
            </article>
          );
        })}
      </section>
    </div>
  );
}

function QuestionsResult() {
  const [savedQuestions, setSavedQuestions] = useState<Set<string>>(() => new Set());
  const [showSavedOnly, setShowSavedOnly] = useState(false);
  const [openedFact, setOpenedFact] = useState<string | null>(null);
  const visibleQuestions = showSavedOnly
    ? demoQuestions.filter((question) => savedQuestions.has(question.title))
    : demoQuestions;

  const toggleSaved = (title: string) => {
    setSavedQuestions((current) => {
      const next = new Set(current);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });
  };

  return (
    <div className="result-workspace result-workspace--questions workspace-panel">
      <header className="workspace-header result-workspace-header">
        <div>
          <span className="workspace-header__kicker">Личное наблюдение</span>
          <h2>Вопросы к себе</h2>
          <p>Вопросы помогают заметить, как темы карты проявляются в решениях, отношениях и повседневных привычках.</p>
        </div>
        <div className="workspace-header__controls result-workspace-header__controls">
          <div className="question-progress" aria-label="Фильтр вопросов">
            <span>{savedQuestions.size} сохранено</span>
            <button type="button" className={!showSavedOnly ? "is-active" : ""} onClick={() => setShowSavedOnly(false)}>Все</button>
            <button type="button" className={showSavedOnly ? "is-active" : ""} onClick={() => setShowSavedOnly(true)}>Сохранённые</button>
          </div>
        </div>
      </header>

      <p className="questions-lead">Каждый вопрос привязан к отдельной теме. Его можно сохранить, а затем раскрыть опору в карте.</p>

      {visibleQuestions.length ? (
        <section className="questions-grid" aria-label="Вопросы готового отчёта">
          {visibleQuestions.map((question, index) => {
            const isSaved = savedQuestions.has(question.title);
            const isFactOpened = openedFact === question.title;
            return (
              <article className="question-card result-question-card" key={question.title}>
                <header>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <small>{question.topics[0]}</small>
                </header>
                <h3>{question.title}</h3>
                <p className="result-question-card__prompt">{question.prompt}</p>
                <div className="question-card__actions">
                  <button type="button" aria-pressed={isSaved} onClick={() => toggleSaved(question.title)}>
                    <Bookmark aria-hidden="true" /> {isSaved ? "Сохранено" : "Сохранить"}
                  </button>
                  <button
                    type="button"
                    aria-expanded={isFactOpened}
                    aria-controls={`demo-question-fact-${question.title.replaceAll(" ", "-")}`}
                    onClick={() => setOpenedFact(isFactOpened ? null : question.title)}
                  >
                    <ChevronDown aria-hidden="true" /> Почему этот вопрос?
                  </button>
                </div>
                {isFactOpened && (
                  <div className="question-card__why" id={`demo-question-fact-${question.title.replaceAll(" ", "-")}`}>
                    <p>{question.fact}</p>
                    <small>{question.insufficient ? "Этот раздел появится после отдельного расчёта периодов." : `Источник: ${question.source}`}</small>
                  </div>
                )}
              </article>
            );
          })}
        </section>
      ) : (
        <p className="workspace-notice">Сохранённых вопросов пока нет. Вернитесь к списку и отметьте те, к которым хотите вернуться.</p>
      )}
    </div>
  );
}

export function ResultsShowcase() {
  const [activeTab, setActiveTab] = useState<ResultTab>("chart");
  const [downloadNotice, setDownloadNotice] = useState("");
  const showcaseRef = useRef<HTMLElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const suppressPanelMotionRef = useRef(false);

  useGSAP(() => {
    const panel = panelRef.current;
    if (!panel) return;

    const reduceMotion = typeof window !== "undefined"
      && typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (suppressPanelMotionRef.current) {
      suppressPanelMotionRef.current = false;
      gsap.set(panel, { clearProps: "all" });
      return;
    }

    if (reduceMotion) {
      gsap.fromTo(panel, { opacity: 0.94 }, { opacity: 1, duration: 0.12, ease: "none", clearProps: "opacity" });
      return;
    }

    gsap.fromTo(
      panel,
      { opacity: 0.9, y: 8 },
      { opacity: 1, y: 0, duration: 0.24, ease: "power2.out", clearProps: "transform,opacity" },
    );
  }, { scope: showcaseRef, dependencies: [activeTab], revertOnUpdate: true });

  const activateTab = (tab: ResultTab, withMotion = true) => {
    suppressPanelMotionRef.current = !withMotion;
    setActiveTab(tab);
  };

  const moveTabFocus = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null;

    if (event.key === "ArrowDown" || event.key === "ArrowRight") nextIndex = (index + 1) % resultTabs.length;
    if (event.key === "ArrowUp" || event.key === "ArrowLeft") nextIndex = (index - 1 + resultTabs.length) % resultTabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = resultTabs.length - 1;
    if (nextIndex === null) return;

    event.preventDefault();
    activateTab(resultTabs[nextIndex].id, false);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <section
      className="results-showcase"
      ref={showcaseRef}
      role="region"
      aria-label="Пример результата натальной карты"
      data-od-id="results-showcase"
    >
      <div className="results-transition" aria-label="Пример готового результата">
        <span aria-hidden="true" />
        <p><strong>ПРИМЕР ГОТОВОГО РЕЗУЛЬТАТА</strong></p>
        <span aria-hidden="true" />
      </div>

      <div className="results-demo-window">
        <aside className="results-sidebar">
          <nav className="results-nav" role="tablist" aria-label="Разделы результата">
            {resultTabs.map((tab, index) => (
              <button
                className={`results-nav__item${activeTab === tab.id ? " is-active" : ""}`}
                key={tab.id}
                id={`results-tab-${tab.id}`}
                ref={(node) => { tabRefs.current[index] = node; }}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-controls="results-active-panel"
                tabIndex={activeTab === tab.id ? 0 : -1}
                onClick={() => activateTab(tab.id)}
                onKeyDown={(event) => moveTabFocus(event, index)}
              >
                <span className="results-nav__icon" aria-hidden="true">
                  <img src={tab.icon} alt="" width="192" height="192" loading="lazy" decoding="async" />
                </span>
                <span>{tab.label}</span>
              </button>
            ))}
          </nav>

          <div className="results-download">
            <p className="results-download__status"><Sparkles aria-hidden="true" /> Карта и первое чтение готовы</p>
            <button
              type="button"
              onClick={() => setDownloadNotice("Демонстрационный PDF появится после полного расчёта карты.")}
            >
              <Download aria-hidden="true" />
              Скачать PDF
            </button>
            {downloadNotice && <p role="status">{downloadNotice}</p>}
          </div>
        </aside>

        <div
          className="results-stage"
          id="results-active-panel"
          ref={panelRef}
          role="tabpanel"
          aria-labelledby={`results-tab-${activeTab}`}
        >
          {activeTab === "chart" && <ChartResult onOpenExplanation={() => activateTab("explanation")} />}
          {activeTab === "explanation" && <ExplanationResult onReturnToChart={() => activateTab("chart")} />}
          {activeTab === "questions" && <QuestionsResult />}
        </div>
      </div>
    </section>
  );
}

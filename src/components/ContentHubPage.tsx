import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import {
  ArrowDown,
  ArrowUpRight,
  Asterisk,
  BookMarked,
  BookOpenText,
  CircleDot,
  Compass,
  Grid2x2,
  Milestone,
  Search,
  Sparkles,
} from "lucide-react";
import {
  type MouseEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  publicArticles,
  type ArticleDifficulty,
  type ContentArticleSummary,
  type ContentSection,
} from "../lib/content-api";
import { applySeo, publicOrigin } from "../lib/seo";
import { ArticleMedia } from "./ArticleMedia";
import { SiteHeader } from "./SiteHeader";

gsap.registerPlugin(useGSAP, ScrollTrigger);

export type NavigateHandler = (path: string) => void;

type ContentHubPageProps = {
  section: ContentSection;
  onNavigate: NavigateHandler;
  initialArticles?: ContentArticleSummary[];
};

type LevelFilter = "all" | ArticleDifficulty;
type GuideCategory =
  | "Основы астрологии"
  | "Планеты и дома"
  | "Время и циклы"
  | "Практика чтения карты";
type CategoryFilter = "all" | GuideCategory;
const GUIDE_ARTICLE_COUNT = 202;

const GUIDE_SECTIONS = [
  {
    number: "01",
    title: "Основы астрологии",
    description:
      "Термины, устройство сидерической карты и базовый язык джйотиша.",
    icon: Compass,
  },
  {
    number: "02",
    title: "Планеты и дома",
    description:
      "Грахи, бхавы и связи, из которых складывается предметное чтение карты.",
    icon: Grid2x2,
  },
  {
    number: "03",
    title: "Время и циклы",
    description:
      "Даши, транзиты, панчанга и расчётные правила работы со временем.",
    icon: CircleDot,
  },
  {
    number: "04",
    title: "Практика чтения карты",
    description:
      "Пошаговые алгоритмы, проверка гипотез и продвинутый синтез показателей.",
    icon: Asterisk,
  },
] as const satisfies ReadonlyArray<{
  number: string;
  title: GuideCategory;
  description: string;
  icon: typeof Compass;
}>;

const copy = {
  guide: {
    eyebrow: "Библиотека знаний VedicWay",
    title: "Гид по астрологии",
    lead: "Практический гид по ведической астрологии с материалами о натальной карте, планетах, домах, аспектах и последовательном чтении джйотиш.",
    libraryTitle: "Читайте по порядку или находите нужный приём",
    emptyTitle: "Каталог гида готов к публикации",
    emptyText: "В коде закреплены 202 адреса и четыре раздела. Codex загружает материалы через закрытый HTML-шлюз.",
    seoTitle: "Гид по ведической астрологии | VedicWay",
    seoDescription:
      "Практический гид по ведической астрологии с материалами о натальной карте, планетах, домах, аспектах и последовательном чтении джйотиш.",
  },
  blog: {
    eyebrow: "Редакционный журнал VedicWay",
    title: "Блог VedicWay",
    lead: "Блог о ведической астрологии с материалами о натальных картах, планетах, прогнозах и практических методах чтения джйотиш.",
    libraryTitle: "Свежие материалы и подробные разборы",
    emptyTitle: "Первый материал уже можно публиковать",
    emptyText: "Контентный шлюз, поиск, уровни сложности и шаблон статьи готовы. Пустая витрина сохранена намеренно.",
    seoTitle: "Блог об астрологии | VedicWay",
    seoDescription:
      "Блог о ведической астрологии с материалами о натальных картах, планетах, прогнозах и практических методах чтения джйотиш.",
  },
} satisfies Record<ContentSection, Record<string, string>>;

function plainLeftClick(event: MouseEvent<HTMLAnchorElement>) {
  return (
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}

function formatDate(value: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
}

function materialCountLabel(value: number) {
  const lastTwo = value % 100;
  const last = value % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return `${value} материалов`;
  if (last === 1) return `${value} материал`;
  if (last >= 2 && last <= 4) return `${value} материала`;
  return `${value} материалов`;
}

function articleMatches(
  article: ContentArticleSummary,
  query: string,
  level: LevelFilter,
  category: CategoryFilter,
) {
  if (level !== "all" && article.difficulty !== level) return false;
  if (category !== "all" && article.category !== category) return false;
  const normalized = query.trim().toLocaleLowerCase("ru-RU");
  if (!normalized) return true;
  return [
    article.title,
    article.excerpt,
    article.category,
    ...article.tags,
  ]
    .join(" ")
    .toLocaleLowerCase("ru-RU")
    .includes(normalized);
}

export function ContentHubPage({
  section,
  onNavigate,
  initialArticles,
}: ContentHubPageProps) {
  const root = useRef<HTMLDivElement>(null);
  const contentLibrary = useRef<HTMLElement>(null);
  const [articles, setArticles] = useState<ContentArticleSummary[]>(
    () => initialArticles ?? [],
  );
  const [loading, setLoading] = useState(() => !initialArticles);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState<LevelFilter>("all");
  const [category, setCategory] = useState<CategoryFilter>("all");
  const page = copy[section];

  useEffect(() => {
    let active = true;
    const hasServerSnapshot = Boolean(initialArticles);
    setLoading(!hasServerSnapshot);
    setFailed(false);
    setQuery("");
    setLevel("all");
    setCategory("all");
    publicArticles(section)
      .then(({ items }) => {
        if (active) setArticles(items);
      })
      .catch(() => {
        if (active) {
          if (!hasServerSnapshot) {
            setArticles([]);
            setFailed(true);
          }
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [initialArticles, section]);

  useEffect(
    () => {
      const origin = publicOrigin();
      const canonical = `${origin}/${section}`;
      return applySeo({
        title: page.seoTitle,
        description: page.seoDescription,
        path: `/${section}`,
        noindex: !loading && articles.length === 0,
        noindexFollow: true,
        structuredData: [
          {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "@id": `${canonical}#collection`,
            name: page.title,
            description: page.seoDescription,
            url: canonical,
            inLanguage: "ru-RU",
            isPartOf: {
              "@type": "WebSite",
              name: "VedicWay",
              url: `${origin}/`,
            },
            mainEntity: {
              "@type": "ItemList",
              numberOfItems: articles.length,
              itemListElement: articles.map((article, index) => ({
                "@type": "ListItem",
                position: index + 1,
                url: article.canonical_url,
                name: article.title,
              })),
            },
          },
          {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            itemListElement: [
              {
                "@type": "ListItem",
                position: 1,
                name: "Главная",
                item: `${origin}/`,
              },
              {
                "@type": "ListItem",
                position: 2,
                name: page.title,
                item: canonical,
              },
            ],
          },
        ],
      });
    },
    [articles, loading, page, section],
  );

  const filtered = useMemo(
    () =>
      articles.filter((article) =>
        articleMatches(article, query, level, category),
      ),
    [articles, category, level, query],
  );
  const guideSectionStats = useMemo(
    () =>
      new Map(
        GUIDE_SECTIONS.map((guideSection) => {
          const items = articles.filter(
            (article) => article.category === guideSection.title,
          );
          return [
            guideSection.title,
            {
              total: items.length,
              beginner: items.filter(
                (article) => article.difficulty === "beginner",
              ).length,
              expert: items.filter(
                (article) => article.difficulty === "expert",
              ).length,
            },
          ] as const;
        }),
      ),
    [articles],
  );
  const guideScope =
    category === "all"
      ? articles
      : articles.filter((article) => article.category === category);
  const guideLevelCounts = {
    beginner: guideScope.filter(
      (article) => article.difficulty === "beginner",
    ).length,
    expert: guideScope.filter(
      (article) => article.difficulty === "expert",
    ).length,
  };
  const publishedGuideCount = articles.length;
  const guidePublicationLabel = loading
    ? "Проверяем библиотеку"
    : `${materialCountLabel(publishedGuideCount)} в четырёх разделах`;

  useGSAP(
    () => {
      if (
        !root.current ||
        typeof window.matchMedia !== "function" ||
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ) {
        return;
      }
      const cards = gsap.utils.toArray<HTMLElement>("[data-content-card]");
      cards.forEach((card) => {
        gsap.fromTo(
          card,
          { autoAlpha: 0, y: 28 },
          {
            autoAlpha: 1,
            y: 0,
            duration: 0.62,
            ease: "power2.out",
            scrollTrigger: {
              trigger: card,
              start: "top 88%",
              once: true,
            },
          },
        );
      });
    },
    {
      scope: root,
      dependencies: [filtered.length, section],
      revertOnUpdate: true,
    },
  );

  const follow = (event: MouseEvent<HTMLAnchorElement>, path: string) => {
    if (!plainLeftClick(event)) return;
    event.preventDefault();
    onNavigate(path);
  };

  const chooseCategory = (value: CategoryFilter) => {
    setCategory(value);
    if (value === "all") return;
    window.requestAnimationFrame(() => {
      const reduceMotion =
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      contentLibrary.current?.scrollIntoView?.({
        behavior: reduceMotion ? "auto" : "smooth",
        block: "start",
      });
    });
  };

  return (
    <div className="content-site" ref={root}>
      <SiteHeader active={section} onNavigate={onNavigate} />
      <main className="content-hub">
        <nav className="content-breadcrumbs" aria-label="Хлебные крошки">
          <a href="/" onClick={(event) => follow(event, "/")}>
            Главная
          </a>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{page.title}</span>
        </nav>

        {section === "guide" ? (
          <section
            className="guide-atlas-hero"
            aria-labelledby="content-hub-title"
          >
            <header className="guide-atlas-hero__masthead">
              <span className="content-eyebrow">
                <BookMarked aria-hidden="true" />
                {page.eyebrow}
              </span>
              <span>Маршрут 01 / 04</span>
            </header>

            <div className="guide-atlas-hero__body">
              <div className="guide-atlas-hero__copy">
                <h1 id="content-hub-title">
                  <span>Гид по</span>{" "}
                  <em>астрологии</em>
                </h1>
                <p>{page.lead}</p>
                <a href="#guide-route">
                  Смотреть структуру
                  <ArrowDown aria-hidden="true" />
                </a>
              </div>

              <div className="guide-atlas-hero__diagram" aria-hidden="true">
                <span className="guide-atlas-hero__north">N</span>
                <span className="guide-atlas-hero__coordinate">
                  55°45′ · 37°37′
                </span>
                <svg viewBox="0 0 360 360" focusable="false">
                  <path
                    className="guide-atlas-hero__route-shadow"
                    d="M44 304 C104 270 74 205 152 186 C222 169 202 96 312 52"
                  />
                  <path
                    className="guide-atlas-hero__route"
                    d="M44 304 C104 270 74 205 152 186 C222 169 202 96 312 52"
                  />
                  <circle cx="44" cy="304" r="7" />
                  <circle cx="128" cy="195" r="7" />
                  <circle cx="232" cy="139" r="7" />
                  <circle cx="312" cy="52" r="7" />
                </svg>
                <span className="guide-atlas-hero__step guide-atlas-hero__step--one">
                  01
                </span>
                <span className="guide-atlas-hero__step guide-atlas-hero__step--two">
                  02
                </span>
                <span className="guide-atlas-hero__step guide-atlas-hero__step--three">
                  03
                </span>
                <span className="guide-atlas-hero__step guide-atlas-hero__step--four">
                  04
                </span>
                <span className="guide-atlas-hero__seal">
                  <Compass />
                  Путь чтения
                </span>
              </div>
            </div>

            <footer className="guide-atlas-hero__footer">
              <span>Четыре раздела от терминов до синтеза карты</span>
              <span>{guidePublicationLabel}</span>
            </footer>
          </section>
        ) : (
          <section
            className="content-hub__hero"
            aria-labelledby="content-hub-title"
          >
            <div>
              <span className="content-eyebrow">
                <Sparkles aria-hidden="true" />
                {page.eyebrow}
              </span>
              <h1 id="content-hub-title">{page.title}</h1>
              <p>{page.lead}</p>
            </div>
            <div className="content-hub__constellation" aria-hidden="true">
              <span />
              <span />
              <span />
              <i />
            </div>
          </section>
        )}

        {section === "guide" ? (
          <section
            className="guide-route"
            id="guide-route"
            aria-labelledby="guide-route-title"
          >
            <header className="guide-route__header">
              <div className="guide-route__intro">
                <span className="content-eyebrow">
                  <Milestone aria-hidden="true" />
                  Структура гида
                </span>
                <h2 id="guide-route-title">
                  Четыре раздела, единая библиотека
                </h2>
                <p>
                  Выберите область гида, затем уточните глубину материала.
                  Категория и уровень работают вместе с поиском по всем
                  статьям.
                </p>
              </div>

              <div
                className="guide-route__metrics"
                aria-label="Четыре раздела гида и два уровня сложности"
              >
                <span>
                  <strong>4</strong>
                  раздела гида
                </span>
                <i aria-hidden="true">×</i>
                <span>
                  <strong>2</strong>
                  уровня сложности
                </span>
              </div>

              <div
                className="guide-route__publication"
                aria-busy={loading}
                role="progressbar"
                aria-label="Опубликованные статьи гида"
                aria-valuemin={0}
                aria-valuemax={GUIDE_ARTICLE_COUNT}
                aria-valuenow={publishedGuideCount}
                aria-valuetext={guidePublicationLabel}
              >
                <span>{guidePublicationLabel}</span>
                <div aria-hidden="true">
                  <i
                    style={{
                      width: `${Math.min(
                        100,
                        (publishedGuideCount / GUIDE_ARTICLE_COUNT) * 100,
                      )}%`,
                    }}
                  />
                </div>
              </div>
            </header>

            <ol className="guide-route__chapters">
              {GUIDE_SECTIONS.map((guideSection) => {
                const stats = guideSectionStats.get(guideSection.title) ?? {
                  total: 0,
                  beginner: 0,
                  expert: 0,
                };
                const SectionIcon = guideSection.icon;
                const active = category === guideSection.title;
                return (
                  <li
                    className={`is-published${active ? " is-active" : ""}`}
                    key={guideSection.title}
                  >
                    <button
                      type="button"
                      aria-label={`Показать раздел: ${guideSection.title}`}
                      aria-pressed={active}
                      onClick={() => chooseCategory(guideSection.title)}
                    >
                      <header>
                        <span className="guide-route__chapter-number">
                          {guideSection.number}
                        </span>
                        <SectionIcon aria-hidden="true" />
                        <span className="guide-route__chapter-state">
                          {materialCountLabel(stats.total)}
                        </span>
                      </header>
                      <span className="guide-route__chapter-kind">
                        Раздел гида
                      </span>
                      <h3>{guideSection.title}</h3>
                      <p>{guideSection.description}</p>
                      <footer>
                        <span>{stats.beginner} для новичков</span>
                        <span>{stats.expert} для экспертов</span>
                        <ArrowDown aria-hidden="true" />
                      </footer>
                    </button>
                  </li>
                );
              })}
            </ol>

            <section
              className="guide-route__levels"
              aria-labelledby="guide-levels-title"
            >
              <header>
                <span>Глубина материала</span>
                <h3 id="guide-levels-title">
                  Выберите глубину внутри любого раздела
                </h3>
                <button
                  type="button"
                  aria-label="Показать все уровни в выбранном разделе"
                  className={level === "all" ? "is-active" : ""}
                  aria-pressed={level === "all"}
                  onClick={() => setLevel("all")}
                >
                  Все уровни
                </button>
              </header>
              <div className="guide-route__level-actions">
                <button
                  type="button"
                  className={level === "beginner" ? "is-active" : ""}
                  aria-pressed={level === "beginner"}
                  onClick={() => setLevel("beginner")}
                >
                  <strong>
                    <span>01</span>
                    Новичок
                  </strong>
                  <span>
                    Термины объясняются с нуля, а порядок чтения разобран по
                    шагам.
                  </span>
                  <small>
                    {materialCountLabel(guideLevelCounts.beginner)}
                  </small>
                </button>
                <button
                  type="button"
                  className={level === "expert" ? "is-active" : ""}
                  aria-pressed={level === "expert"}
                  onClick={() => setLevel("expert")}
                >
                  <strong>
                    <span>02</span>
                    Эксперт
                  </strong>
                  <span>
                    Материал требует базовых понятий и разбирает связи внутри
                    карты глубже.
                  </span>
                  <small>{materialCountLabel(guideLevelCounts.expert)}</small>
                </button>
              </div>
            </section>
          </section>
        ) : null}

        <section
          className="content-library"
          ref={contentLibrary}
          aria-labelledby="content-library-title"
        >
          <header className="content-library__header">
            <div>
              <span className="content-eyebrow">
                <BookOpenText aria-hidden="true" />
                Библиотека
              </span>
              <h2 id="content-library-title">{page.libraryTitle}</h2>
            </div>
            <p aria-live="polite">
              {filtered.length === articles.length
                ? materialCountLabel(articles.length)
                : `${materialCountLabel(filtered.length)} из ${articles.length}`}
            </p>
          </header>

          <div className="content-discovery">
            <label className="content-search">
              <span className="sr-only">Поиск по статьям</span>
              <Search aria-hidden="true" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Поиск по статьям"
                placeholder="Тема, термин или вопрос"
              />
            </label>
            <div className="content-levels" aria-label="Уровень материала">
              {(
                [
                  ["all", "Все уровни"],
                  ["beginner", "Новичок"],
                  ["expert", "Эксперт"],
                ] as const
              ).map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  className={level === value ? "is-active" : ""}
                  aria-pressed={level === value}
                  onClick={() => setLevel(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            {section === "guide" ? (
              <div
                className="content-categories"
                aria-label="Раздел гида"
              >
                {(
                  [
                    ["all", "Все разделы"],
                    ...GUIDE_SECTIONS.map(
                      (guideSection) =>
                        [guideSection.title, guideSection.title] as const,
                    ),
                  ] as const
                ).map(([value, label]) => (
                  <button
                    type="button"
                    key={value}
                    className={category === value ? "is-active" : ""}
                    aria-pressed={category === value}
                    onClick={() => setCategory(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          {loading ? (
            <div className="content-state" role="status">
              <span className="content-state__pulse" aria-hidden="true" />
              <p>Собираем библиотеку…</p>
            </div>
          ) : failed ? (
            <div className="content-state" role="alert">
              <h3>Библиотека временно недоступна</h3>
              <p>Сервер не ответил. Обновите страницу через минуту.</p>
            </div>
          ) : articles.length === 0 ? (
            <div className="content-state content-state--empty" role="status">
              <span aria-hidden="true">✦</span>
              <h3>{page.emptyTitle}</h3>
              <p>{page.emptyText}</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="content-state content-state--empty" role="status">
              <span aria-hidden="true">⌕</span>
              <h3>Совпадений нет</h3>
              <p>
                Сократите запрос либо измените раздел или уровень сложности.
              </p>
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setLevel("all");
                  setCategory("all");
                }}
              >
                Сбросить поиск
              </button>
            </div>
          ) : (
            <div className="content-grid" aria-live="polite">
              {filtered.map((article) => {
                const path = `/${section}/${article.slug}`;
                return (
                  <article
                    className="content-card"
                    data-content-card
                    key={article.id}
                  >
                    <a
                      className="content-card__media"
                      href={path}
                      aria-label={`Открыть: ${article.title}`}
                      onClick={(event) => follow(event, path)}
                    >
                      {article.coverImage ? (
                        <ArticleMedia
                          asset={article.coverImage}
                          sizes="(max-width: 720px) calc(100vw - 32px), (max-width: 1100px) 50vw, 390px"
                        />
                      ) : article.cover_image_url ? (
                        <img
                          src={article.cover_image_url}
                          alt={article.cover_image_alt}
                          loading="lazy"
                          decoding="async"
                        />
                      ) : (
                        <span aria-hidden="true">✦</span>
                      )}
                    </a>
                    <div className="content-card__body">
                      <div className="content-card__meta">
                        <span
                          className={`difficulty-badge difficulty-badge--${article.difficulty}`}
                        >
                          {article.difficulty_label}
                        </span>
                        <span>{article.category}</span>
                      </div>
                      <h3>{article.title}</h3>
                      <p>{article.excerpt}</p>
                      <footer>
                        <time
                          dateTime={
                            article.published_at ?? article.updated_at
                          }
                        >
                          {formatDate(
                            article.published_at ?? article.updated_at,
                          )}
                        </time>
                        <a
                          href={path}
                          aria-label={`Читать: ${article.title}`}
                          onClick={(event) => follow(event, path)}
                        >
                          Читать
                          <ArrowUpRight aria-hidden="true" />
                        </a>
                      </footer>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

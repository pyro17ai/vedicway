import { useEffect, type MouseEvent } from "react";

import { applySeo, publicOrigin } from "../lib/seo";
import { SiteHeader } from "./SiteHeader";

export type TrustPageKind = "about" | "methodology" | "editorial-policy";

type TrustPageProps = {
  kind: TrustPageKind;
  onNavigate: (path: string) => void;
};

const pages = {
  about: {
    path: "/about",
    title: "О сервисе VedicWay",
    description:
      "Кто создаёт VedicWay, как устроен сервис ведической натальной карты и где проходит граница между расчётом и интерпретацией.",
    lead:
      "VedicWay рассчитывает сидерическую натальную карту и помогает читать её на русском языке. За материалами и продуктовой логикой стоит редакция VedicWay.",
    sections: [
      {
        title: "Что делает сервис",
        paragraphs: [
          "Расчёт использует дату, местное время и координаты рождения. Результат содержит карту D1, положения планет, лагну и последующие расчётные разделы.",
          "Тексты объясняют астрологические понятия в культурном и образовательном контексте. Они не заменяют медицинскую, юридическую или финансовую консультацию.",
        ],
      },
      {
        title: "Кто отвечает за материалы",
        paragraphs: [
          "Редакция VedicWay проверяет структуру статьи, внутренние ссылки, источники и соответствие видимого текста структурированным данным. Дата изменения хранится вместе с каждой публикацией.",
          "Замечания по фактической ошибке или источнику можно отправить на vedicway-ru@yandex.ru с адресом страницы и фрагментом, который требует проверки.",
        ],
      },
    ],
  },
  methodology: {
    path: "/methodology",
    title: "Метод расчёта натальной карты",
    description:
      "Методология VedicWay: сидерический зодиак, аянамша Лахири, дома от лагны, точность времени рождения и границы интерпретации.",
    lead:
      "VedicWay фиксирует расчётные настройки рядом с результатом, чтобы одну карту можно было повторно проверить при тех же исходных данных.",
    sections: [
      {
        title: "Расчётные настройки",
        paragraphs: [
          "Основная карта строится в сидерическом зодиаке с аянамшей Лахири. Дома отсчитываются от лагны, а интерфейс показывает карту в южноиндийском стиле.",
          "Расчётный контур использует PyJHora 4.7.0 и Swiss Ephemeris 2.10.3.2. Контрольная карта проверяет лагну и положение Луны перед запуском публичного контура.",
        ],
      },
      {
        title: "Точность исходных данных",
        paragraphs: [
          "Дата и координаты определяют астрономическую основу расчёта. Ошибка во времени рождения способна изменить лагну, дома и дробные карты.",
          "Если время известно приблизительно, VedicWay помечает ограничение в результате. Пользователь должен сверять исходные данные до трактовки показателей, чувствительных к минутам.",
        ],
      },
      {
        title: "Граница интерпретации",
        paragraphs: [
          "Астрологическая трактовка относится к традиции джйотиш и служит материалом для самонаблюдения. Сервис не выдаёт диагнозы, правовые решения или инвестиционные рекомендации.",
        ],
      },
    ],
  },
  "editorial-policy": {
    path: "/editorial-policy",
    title: "Редакционная политика VedicWay",
    description:
      "Как редакция VedicWay отбирает источники, проверяет статьи о джйотиш, исправляет ошибки и отделяет факты от трактовки.",
    lead:
      "Каждая статья проходит автоматическую проверку разметки и ручную редактуру до публикации. Материал с битой кодировкой, неизвестной внутренней ссылкой или пустым списком источников блокируется.",
    sections: [
      {
        title: "Источники",
        paragraphs: [
          "Редакция указывает внешние источники в видимом блоке статьи. Ссылки из этого блока совпадают с полем citation в Schema.org.",
          "Для расчётных утверждений приоритет получают документация используемого программного контура и проверяемые астрономические данные. Исторические и традиционные положения сопровождаются названием школы или текста, когда различие школ меняет вывод.",
        ],
      },
      {
        title: "Контроль качества",
        paragraphs: [
          "Публикационный шлюз проверяет кодировку UTF-8, минимальный объём, структуру заголовков, уникальность метаданных и все внутренние маршруты. Повторяющиеся предложения внутри одной статьи также блокируют выпуск.",
          "Дата изменения показывает последнюю содержательную редакцию. Исправление опечатки не должно маскироваться под обновление методологии.",
        ],
      },
      {
        title: "Исправления",
        paragraphs: [
          "Сообщение об ошибке принимается по адресу vedicway-ru@yandex.ru. В письме нужны URL, спорный фрагмент и источник, который подтверждает исправление.",
        ],
      },
    ],
  },
} satisfies Record<
  TrustPageKind,
  {
    path: string;
    title: string;
    description: string;
    lead: string;
    sections: Array<{ title: string; paragraphs: string[] }>;
  }
>;

function plainLeftClick(event: MouseEvent<HTMLAnchorElement>) {
  return event.button === 0
    && !event.metaKey
    && !event.ctrlKey
    && !event.shiftKey
    && !event.altKey;
}

export function TrustPage({ kind, onNavigate }: TrustPageProps) {
  const page = pages[kind];

  useEffect(
    () =>
      applySeo({
        title: `${page.title} | VedicWay`,
        description: page.description,
        path: page.path,
        structuredData: [
          {
            "@context": "https://schema.org",
            "@type": "AboutPage",
            "@id": `${publicOrigin()}${page.path}#page`,
            url: `${publicOrigin()}${page.path}`,
            name: page.title,
            description: page.description,
            inLanguage: "ru-RU",
            about: {
              "@type": "Organization",
              "@id": `${publicOrigin()}/about#organization`,
              name: "VedicWay",
              url: `${publicOrigin()}/about`,
            },
          },
        ],
      }),
    [page],
  );

  const follow = (event: MouseEvent<HTMLAnchorElement>, path: string) => {
    if (!plainLeftClick(event)) return;
    event.preventDefault();
    onNavigate(path);
  };

  return (
    <div className="content-site">
      <SiteHeader active={null} onNavigate={onNavigate} />
      <main className="trust-page">
        <nav className="content-breadcrumbs" aria-label="Хлебные крошки">
          <a href="/" onClick={(event) => follow(event, "/")}>Главная</a>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{page.title}</span>
        </nav>
        <article>
          <header>
            <span>Прозрачность VedicWay</span>
            <h1>{page.title}</h1>
            <p>{page.lead}</p>
          </header>
          {page.sections.map((section) => (
            <section key={section.title}>
              <h2>{section.title}</h2>
              {section.paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </section>
          ))}
          <nav aria-label="Дополнительная информация">
            <a href="/about" onClick={(event) => follow(event, "/about")}>О сервисе</a>
            <a href="/methodology" onClick={(event) => follow(event, "/methodology")}>Метод расчёта</a>
            <a href="/editorial-policy" onClick={(event) => follow(event, "/editorial-policy")}>Редакционная политика</a>
          </nav>
        </article>
      </main>
    </div>
  );
}

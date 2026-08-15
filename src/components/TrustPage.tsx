import { useEffect, type MouseEvent } from "react";

import { applySeo, publicOrigin } from "../lib/seo";
import { SiteHeader } from "./SiteHeader";

export type TrustPageKind = "about" | "methodology" | "editorial-policy" | "report-example";

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
          "Оператор сайта: ИП Корольский Вадимир Васильевич, ИНН 722407070173, ОГРНИП 311723232700200. Замечания по фактической ошибке или источнику принимаются по адресу vedicway-ru@yandex.com.",
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
          "Сообщение об ошибке принимается по адресу vedicway-ru@yandex.com. В письме нужны URL, спорный фрагмент и источник, который подтверждает исправление.",
        ],
      },
    ],
  },
  "report-example": {
    path: "/report-example",
    title: "Пример полного отчёта по натальной карте",
    description:
      "Демонстрационный полный отчёт VedicWay: общий синтез, восемь жизненных тем, профессиональный вектор и текущие с будущими периодами Вимшоттари.",
    lead:
      "Статический пример показывает объём и устройство платного отчёта до оплаты.",
    sections: [],
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
  const pageType = kind === "about" ? "AboutPage" : "WebPage";

  useEffect(
    () =>
      applySeo({
        title: `${page.title} | VedicWay`,
        description: page.description,
        path: page.path,
        noindex: kind === "report-example",
        noindexFollow: kind === "report-example",
        structuredData: [
          {
            "@context": "https://schema.org",
            "@type": pageType,
            "@id": `${publicOrigin()}${page.path}#page`,
            url: `${publicOrigin()}${page.path}`,
            name: page.title,
            description: page.description,
            inLanguage: "ru-RU",
            about: {
              "@type": "Organization",
              "@id": `${publicOrigin()}/about#organization`,
              name: "VedicWay",
              alternateName: "VedicWay.ru",
              legalName: "ИП Корольский Вадимир Васильевич",
              url: `${publicOrigin()}/`,
              email: "vedicway-ru@yandex.com",
              taxID: "722407070173",
              identifier: {
                "@type": "PropertyValue",
                propertyID: "ОГРНИП",
                value: "311723232700200",
              },
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
                item: `${publicOrigin()}/`,
              },
              {
                "@type": "ListItem",
                position: 2,
                name: page.title,
                item: `${publicOrigin()}${page.path}`,
              },
            ],
          },
        ],
      }),
    [page, pageType],
  );

  const follow = (event: MouseEvent<HTMLAnchorElement>, path: string) => {
    if (!plainLeftClick(event)) return;
    event.preventDefault();
    onNavigate(path);
  };

  if (kind === "report-example") {
    return (
      <div className="content-site">
        <SiteHeader active={null} onNavigate={onNavigate} />
        <main className="trust-page trust-page--report-example">
          <nav className="content-breadcrumbs" aria-label="Хлебные крошки">
            <a href="/" onClick={(event) => follow(event, "/")}>Главная</a>
            <span aria-hidden="true">/</span>
            <span aria-current="page">Пример полного отчёта</span>
          </nav>

          <article className="report-example">
            <header className="report-example__hero">
              <span>Демонстрационный полный отчёт</span>
              <h1>От наблюдения к публичной работе</h1>
              <p className="report-example__lead">
                Ниже показан формат персонального разбора после оплаты: общий рисунок карты, восемь жизненных тем, профессиональный вектор и календарь периодов. В настоящем отчёте текст строится по расчёту конкретного человека.
              </p>
              <p className="report-example__notice">
                <strong>Вымышленный учебный профиль.</strong> Все положения планет, дома и даты периодов условны. Пример нужен, чтобы до оплаты оценить глубину текста и способ подачи.
              </p>
              <dl className="report-example__meta">
                <div><dt>Профиль</dt><dd>Вымышленный учебный пример</dd></div>
                <div><dt>Положения и сроки</dt><dd>Условные, для показа формата</dd></div>
                <div><dt>Состав</dt><dd>Синтез, восемь тем и периоды</dd></div>
                <div><dt>Метод подачи</dt><dd>Выводы рядом с основаниями</dd></div>
              </dl>
            </header>

            <nav className="report-example__contents" aria-label="Содержание примера отчёта">
              <a href="#example-synthesis">Общий синтез</a>
              <a href="#example-domains">Восемь тем</a>
              <a href="#example-periods">Периоды</a>
            </nav>

            <section id="example-synthesis" className="report-example__chapter">
              <span className="report-example__eyebrow">01 · Общий рисунок</span>
              <h2>Общий синтез карты</h2>
              <p>
                В этой карте наблюдение и систематизация проявлены сильнее быстрого напора. Лагна в Деве задаёт привычку сначала собрать детали, проверить порядок и только затем действовать. Луна в Близнецах связывает внутреннюю устойчивость с движением мысли: человеку легче справляться с неопределённостью, когда он может назвать происходящее, сравнить несколько версий и обсудить их с собеседником.
              </p>
              <p>
                Центральная линия карты проходит через обмен знаниями и видимый результат. Сильный десятый дом делает работу публичной частью идентичности, а связь его показателей с Меркурием усиливает способности редактора, аналитика и преподавателя. Задачи без ясного адресата быстро теряют смысл. Энергия возвращается там, где есть человек, которому можно объяснить сложное и помочь принять решение.
              </p>
              <p>
                Напряжение возникает между точностью и сроком. Стремление проверить каждую формулировку способно задерживать выпуск работы, хотя карта лучше раскрывается через короткие циклы: версия, обратная связь, доработка. Этот ритм сохраняет качество и не превращает подготовку в бесконечное ожидание идеального момента.
              </p>
            </section>

            <section id="example-domains" className="report-example__chapter">
              <span className="report-example__eyebrow">02 · Подробное чтение</span>
              <h2>Восемь жизненных тем</h2>
              <div className="report-example__domains">
                <article className="report-example__domain">
                  <span>Характер</span><h3>Точность перед скоростью</h3>
                  <p>Вы входите в новую задачу через наблюдение и поиск рабочего порядка. Уверенность растёт после первого проверяемого результата, поэтому маленький завершённый этап полезнее долгой подготовки.</p>
                  <small>Основание: лагна в Деве, Меркурий в 10-м доме</small>
                </article>
                <article className="report-example__domain">
                  <span>Внутренние опоры</span><h3>Ясность приходит в разговоре</h3>
                  <p>Мысль быстрее собирается во время письма или диалога. В период перегрузки помогают короткая запись фактов и разговор с человеком, который задаёт точные вопросы без давления.</p>
                  <small>Основание: Луна в Близнецах, связь с Меркурием</small>
                </article>
                <article className="report-example__domain">
                  <span>Отношения</span><h3>Близость через интеллектуальное доверие</h3>
                  <p>Вам нужен партнёр, с которым можно менять мнение и не защищать каждую прежнюю позицию. Недосказанность переживается тяжелее прямого разногласия, поэтому важные ожидания лучше проговаривать заранее.</p>
                  <small>Основание: управитель 7-го дома, показатели Луны</small>
                </article>
                <article className="report-example__domain">
                  <span>Семья и дом</span><h3>Дом как место восстановления</h3>
                  <p>В быту требуется понятный ритм и личное пространство для тишины. Частые перестановки и незавершённые бытовые дела незаметно расходуют внимание, которое затем не хватает на работу.</p>
                  <small>Основание: 4-й дом и положение его управителя</small>
                </article>
                <article className="report-example__domain">
                  <span>Работа</span><h3>Роли на стыке анализа и объяснения</h3>
                  <p>Сильнее всего подходят профессии, где нужно разбирать сложную систему и переводить её в ясные решения: аналитика, редактура, продуктовая работа, исследования и обучение. Узкая исполнительская роль без права влиять на результат быстро истощает.</p>
                  <small>Основание: 10-й дом, Меркурий и Юпитер</small>
                </article>
                <article className="report-example__domain">
                  <span>Деньги</span><h3>Доход через компетенцию и репутацию</h3>
                  <p>Денежный рост связан с дорогой экспертной работой, повторными заказами и понятной специализацией. Распыление на несвязанные услуги снижает средний чек; один доказанный профиль приносит больше, чем пять размытых предложений.</p>
                  <small>Основание: 2-й и 11-й дома, период Юпитера</small>
                </article>
                <article className="report-example__domain">
                  <span>Обучение</span><h3>Знание закрепляется через практику</h3>
                  <p>Вам полезно учиться на реальном проекте и сразу объяснять материал другому человеку. Длинная теория без применения создаёт ощущение движения, но редко меняет навык.</p>
                  <small>Основание: 5-й дом и показатели Меркурия</small>
                </article>
                <article className="report-example__domain">
                  <span>Текущий период</span><h3>Сначала укрепить основание</h3>
                  <p>Антардаша Сатурна внутри махадаши Юпитера длится до 29 августа 2028 года. Её задача связана с дисциплиной, долгими договорённостями и сборкой системы, которая выдержит будущий рост.</p>
                  <small>Основание: Вимшоттари-даша, Юпитер и Сатурн</small>
                </article>
              </div>
            </section>

            <section id="example-periods" className="report-example__chapter">
              <span className="report-example__eyebrow">03 · Время и переходы</span>
              <h2>Текущий и будущие периоды</h2>
              <p>
                Махадаша Юпитера идёт с 30 декабря 2023 года по 30 декабря 2039 года. Общий фон периода усиливает обучение, передачу опыта и работу с более широким кругом людей. Внутри него меняются антардаши, поэтому задачи ближайших лет различаются.
              </p>
              <ol className="report-example__timeline">
                <li className="is-current">
                  <div><span>Сейчас</span><strong>Юпитер · Сатурн</strong><time dateTime="2026-02-16">16.02.2026</time> по <time dateTime="2028-08-29">29.08.2028</time></div>
                  <p>Период укрепления профессии. Деньги приходят через регулярные контракты и ответственность за завершённый цикл работы. Резкие смены направления размывают накопленный эффект.</p>
                </li>
                <li>
                  <div><span>Следующий</span><strong>Юпитер · Меркурий</strong><time dateTime="2028-08-29">29.08.2028</time> по <time dateTime="2030-12-05">05.12.2030</time></div>
                  <p>Период переговоров, обучения и расширения аудитории. Подходящее время для авторского продукта, преподавания или перехода в роль, где оплачивают способность быстро разбирать информацию.</p>
                </li>
                <li>
                  <div><span>Затем</span><strong>Юпитер · Кету</strong><time dateTime="2030-12-05">05.12.2030</time> по <time dateTime="2031-11-12">12.11.2031</time></div>
                  <p>Период пересмотра нагрузки. Часть прежних задач потеряет смысл, поэтому финансовый запас и сокращение лишних обязательств лучше подготовить в предыдущую антардашу.</p>
                </li>
              </ol>
            </section>

            <section className="report-example__chapter">
              <span className="report-example__eyebrow">04 · Личное наблюдение</span>
              <h2>Три из двенадцати вопросов</h2>
              <ol className="report-example__questions">
                <li>Какой завершённый результат уже подтверждает вашу компетенцию лучше нового обучения?</li>
                <li>Где стремление к точности задерживает разговор, который давно пора провести?</li>
                <li>Какую одну профессиональную тему вы готовы развивать до августа 2028 года?</li>
              </ol>
            </section>

            <section className="report-example__cta" aria-labelledby="report-example-cta-title">
              <h2 id="report-example-cta-title">Получите разбор по своей карте</h2>
              <p>Расчёт начнётся с даты, точного времени и места рождения. Перед оплатой вы увидите первое персональное чтение.</p>
              <a href="/" onClick={(event) => follow(event, "/")}>Рассчитать свою карту</a>
            </section>
          </article>
        </main>
      </div>
    );
  }

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

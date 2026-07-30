import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const DIST = resolve("dist");
const configuredOrigin = process.env.VITE_PUBLIC_ORIGIN || process.env.VEDICWAY_PUBLIC_ORIGIN;
if (!configuredOrigin && process.env.CI) {
  throw new Error("VITE_PUBLIC_ORIGIN is required for deterministic SEO prerendering");
}
const publicOrigin = configuredOrigin || "http://localhost:5173";
const originUrl = new URL(publicOrigin);
const localDevelopmentOrigin = originUrl.protocol === "http:" && originUrl.hostname === "localhost";
if ((!localDevelopmentOrigin && originUrl.protocol !== "https:") || originUrl.pathname !== "/" || originUrl.search || originUrl.hash) {
  throw new Error("VITE_PUBLIC_ORIGIN must be an HTTPS origin without a path, query, or fragment");
}
const ORIGIN = originUrl.origin;
const template = await readFile(resolve(DIST, "index.html"), "utf8");
const metrikaCounterId = String(process.env.VITE_YANDEX_METRIKA_ID ?? "").trim();

if (metrikaCounterId && !/^[1-9][0-9]*$/.test(metrikaCounterId)) {
  throw new Error("VITE_YANDEX_METRIKA_ID must be a positive numeric counter id");
}
const entryScript = template.match(/<script\b[^>]*\bsrc="(\/assets\/[^"]+\.js)"[^>]*><\/script>/i)?.[1];
const entryStyle = template.match(/<link\b[^>]*\bhref="(\/assets\/[^"]+\.css)"[^>]*>/i)?.[1];

if (!entryScript || !entryStyle) {
  throw new Error("Vite entry assets are missing from dist/index.html");
}

await copyFile(resolve(DIST, entryScript.slice(1)), resolve(DIST, "assets/seo-entry.js"));
await copyFile(resolve(DIST, entryStyle.slice(1)), resolve(DIST, "assets/seo-entry.css"));

const faqEntries = [
  ["Что такое натальная карта и как работает сервис VedicWay?", "Натальная карта показывает положение небесных тел в момент рождения. VedicWay сопоставляет дату, точное время и координаты места с астрономическими эфемеридами, а затем строит карту и её объяснение."],
  ["Какие данные нужны для расчёта?", "Нужны дата, максимально точное время и город рождения. По городу сервис определяет координаты и исторический часовой пояс."],
  ["Можно ли получить натальную карту без времени рождения?", "Можно получить ограниченный результат, но без времени нельзя надёжно определить лагну, дома и показатели, чувствительные к минутам."],
  ["Чем ведическая астрология отличается от западной?", "VedicWay использует сидерический зодиак, аянамшу Лахири, накшатры и дома от лагны."],
  ["Насколько точен разбор?", "Положения небесных тел рассчитываются по эфемеридам, а надёжность домов зависит от точности времени рождения."]
];

const preludeStyle = `<style>.seo-prerender{min-height:100vh;padding:48px;color:#f5eee4;background:#050505;font-family:Georgia,serif}.seo-prerender nav{display:flex;gap:24px}.seo-prerender a{color:#ef7a2e}.seo-prerender h1{max-width:900px;font-size:clamp(42px,7vw,92px)}.seo-prerender p,.seo-prerender label{font-family:Arial,sans-serif;line-height:1.6}.seo-prerender form{display:grid;gap:12px;max-width:560px}.seo-prerender label{display:grid;gap:6px}.seo-prerender input,.seo-prerender button{min-height:44px}</style>`;

const pages = [
  {
    output: "index.html",
    preloadImage: "/assets/hero-space-light.avif",
    title: "Натальная карта онлайн с персональным разбором | VedicWay",
    description: "Рассчитайте натальную карту онлайн по дате, точному времени и месту рождения. Получите наглядную карту и подробное персональное объяснение VedicWay.",
    canonical: "https://vedicway.ru/",
    image: "https://vedicway.ru/assets/hero-space.png",
    body: homeBody(),
    schema: [
      {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": "https://vedicway.ru/about#organization",
        name: "VedicWay",
        url: "https://vedicway.ru/about",
        logo: "https://vedicway.ru/assets/brand-mark.png",
        email: "vedicway-ru@yandex.ru"
      },
      {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": "https://vedicway.ru/#website",
        name: "VedicWay",
        url: "https://vedicway.ru/",
        inLanguage: "ru-RU",
        publisher: { "@id": "https://vedicway.ru/about#organization" }
      }
    ]
  },
  {
    output: "guide/index.html",
    title: "Гид по ведической астрологии | VedicWay",
    description: "Практический гид по ведической астрологии с материалами о натальной карте, планетах, домах, аспектах и последовательном чтении джйотиш.",
    canonical: "https://vedicway.ru/guide",
    image: "https://vedicway.ru/assets/results-space-v2.png",
    body: guideBody(),
    schema: [
      {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        name: "Гид по астрологии",
        description: "Статьи VedicWay о натальной карте, планетах, домах и аспектах.",
        url: "https://vedicway.ru/guide",
        inLanguage: "ru-RU"
      },
      {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Главная", item: "https://vedicway.ru/" },
          { "@type": "ListItem", position: 2, name: "Гид по астрологии", item: "https://vedicway.ru/guide" }
        ]
      }
    ]
  },
  {
    output: "blog/index.html",
    title: "Блог об астрологии | VedicWay",
    description: "Редакционные статьи VedicWay о ведической астрологии, прогностике, натальных картах и практике чтения символов.",
    canonical: "https://vedicway.ru/blog",
    image: "https://vedicway.ru/assets/hero-space-light.png",
    body: blogBody(),
    schema: [
      {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        name: "Блог VedicWay",
        description: "Редакционные материалы VedicWay об астрологии и практике чтения натальной карты.",
        url: "https://vedicway.ru/blog",
        inLanguage: "ru-RU"
      },
      {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Главная", item: "https://vedicway.ru/" },
          { "@type": "ListItem", position: 2, name: "Блог", item: "https://vedicway.ru/blog" }
        ]
      }
    ]
  },
  {
    output: "access/recovery/index.html",
    title: "Восстановление доступа | VedicWay",
    description: "Запрос одноразовой ссылки на оплаченные материалы VedicWay.",
    canonical: "https://vedicway.ru/access/recovery",
    image: "https://vedicway.ru/assets/hero-space.png",
    noindex: true,
    body: `<main class="seo-prerender"><nav><a href="/">Главная</a></nav><h1>Восстановить доступ</h1><p>Укажите email, использованный при оплате. Ответ не раскрывает, связан ли адрес с заказом.</p><form><label>Email<input type="email" autocomplete="email" required></label><button type="submit">Отправить запрос</button></form></main>`,
    schema: []
  },
  {
    output: "access/confirm/index.html",
    title: "Подтверждение доступа | VedicWay",
    description: "Подтверждение одноразовой ссылки на материалы VedicWay.",
    canonical: "https://vedicway.ru/access/confirm",
    image: "https://vedicway.ru/assets/hero-space.png",
    noindex: true,
    referrerPolicy: "no-referrer",
    body: `<main class="seo-prerender"><nav><a href="/">Главная</a></nav><h1>Подтвердить доступ</h1><p>Нажмите кнопку, чтобы открыть материалы в этом браузере.</p><form action="/api/v1/magic-links/confirm" method="post"><button type="submit">Открыть материалы</button></form></main>`,
    schema: []
  },
  {
    output: "privacy/request/index.html",
    title: "Запрос по персональным данным | VedicWay",
    description: "Обращение по доступу, удалению или отзыву согласия на обработку персональных данных.",
    canonical: "https://vedicway.ru/privacy/request",
    image: "https://vedicway.ru/assets/hero-space.png",
    noindex: true,
    body: `<main class="seo-prerender"><nav><a href="/">Главная</a></nav><h1>Запрос по персональным данным</h1><p>Укажите email и предмет обращения. Исполнение начинается после проверки личности заявителя.</p></main>`,
    schema: []
  },
  {
    output: "404.html",
    title: "Страница не найдена | VedicWay",
    description: "Запрошенная страница VedicWay не найдена.",
    canonical: "https://vedicway.ru/404",
    image: "https://vedicway.ru/assets/hero-space.png",
    noindex: true,
    body: `<main class="seo-prerender"><nav><a href="/">Главная</a><a href="/guide">Гид по астрологии</a><a href="/blog">Блог</a></nav><p>404</p><h1>Страница не найдена</h1><p>Адрес мог измениться или в ссылке есть ошибка.</p></main>`,
    schema: []
  }
];

const legalPages = [
  ["offer", "Публичная оферта и пользовательское соглашение", "Условия использования VedicWay, оплаты и получения полного персонального отчёта."],
  ["privacy", "Политика обработки персональных данных", "Правила обработки и защиты персональных данных пользователей VedicWay."],
  ["user-agreement", "Публичная оферта и пользовательское соглашение", "Условия использования VedicWay, оплаты и получения полного персонального отчёта."],
  ["privacy-policy", "Политика обработки персональных данных", "Правила обработки и защиты персональных данных пользователей VedicWay."],
  ["personal-data-consent", "Согласие на обработку персональных данных", "Текст отдельного согласия пользователя на обработку данных для расчёта натальной карты."],
  ["cookies", "Политика использования cookies", "Правила использования обязательных и аналитических cookies на сайте VedicWay."]
];

const trustPages = [
  {
    slug: "about",
    title: "О сервисе VedicWay",
    description: "Кто создаёт VedicWay, как устроен сервис ведической натальной карты и где проходит граница между расчётом и интерпретацией.",
    lead: "VedicWay рассчитывает сидерическую натальную карту и помогает читать её на русском языке. За материалами и продуктовой логикой стоит редакция VedicWay.",
    sections: [
      ["Что делает сервис", "Расчёт использует дату, местное время и координаты рождения. Материалы объясняют астрологические понятия в культурном и образовательном контексте."],
      ["Кто отвечает за материалы", "Редакция VedicWay проверяет структуру статьи, внутренние ссылки, источники и соответствие видимого текста структурированным данным."]
    ]
  },
  {
    slug: "methodology",
    title: "Метод расчёта натальной карты",
    description: "Методология VedicWay: сидерический зодиак, аянамша Лахири, дома от лагны, точность времени рождения и границы интерпретации.",
    lead: "VedicWay фиксирует расчётные настройки рядом с результатом, чтобы одну карту можно было повторно проверить при тех же исходных данных.",
    sections: [
      ["Расчётные настройки", "Основная карта строится в сидерическом зодиаке с аянамшей Лахири. Дома отсчитываются от лагны, а интерфейс показывает карту в южноиндийском стиле."],
      ["Точность исходных данных", "Ошибка во времени рождения способна изменить лагну, дома и дробные карты. Исходные данные нужно сверять до трактовки показателей, чувствительных к минутам."]
    ]
  },
  {
    slug: "editorial-policy",
    title: "Редакционная политика VedicWay",
    description: "Как редакция VedicWay отбирает источники, проверяет статьи о джйотиш, исправляет ошибки и отделяет факты от трактовки.",
    lead: "Каждая статья проходит автоматическую проверку разметки и ручную редактуру до публикации.",
    sections: [
      ["Источники", "Редакция указывает внешние источники в видимом блоке статьи. Ссылки из этого блока совпадают с полем citation в Schema.org."],
      ["Контроль качества", "Материал с битой кодировкой, неизвестной внутренней ссылкой, повторяющимся предложением или пустым списком источников блокируется."]
    ]
  }
];

for (const page of trustPages) {
  pages.push({
    output: `${page.slug}/index.html`,
    title: `${page.title} | VedicWay`,
    description: page.description,
    canonical: `${ORIGIN}/${page.slug}`,
    image: `${ORIGIN}/assets/hero-space-light.png`,
    body: trustBody(page),
    schema: [{
      "@context": "https://schema.org",
      "@type": "AboutPage",
      "@id": `${ORIGIN}/${page.slug}#page`,
      name: page.title,
      url: `${ORIGIN}/${page.slug}`,
      description: page.description,
      inLanguage: "ru-RU",
      about: { "@id": `${ORIGIN}/about#organization` }
    }]
  });
}

for (const [slug, title, description] of legalPages) {
  pages.push({
    output: `legal/${slug}/index.html`,
    title: `${title} | VedicWay`,
    description,
    canonical: `${ORIGIN}/legal/${slug}`,
    image: `${ORIGIN}/assets/hero-space.png`,
    body: legalBody(title, description),
    schema: [{
      "@context": "https://schema.org",
      "@type": "WebPage",
      name: title,
      url: `${ORIGIN}/legal/${slug}`,
      description,
      inLanguage: "ru-RU"
    }]
  });
}

for (const page of pages) {
  const target = resolve(DIST, page.output);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, renderPage(page), "utf8");
}

await rewritePublicOrigin("robots.txt");
await rewritePublicOrigin("sitemap.xml");
await rewritePublicOrigin("llms.txt");

function renderPage(page) {
  let html = template;
  if (page.preloadImage) {
    html = html.replace(
      "</head>",
      `    <link rel="preload" as="image" href="${escapeHtml(page.preloadImage)}" type="image/avif" fetchpriority="high" />\n  </head>`,
    );
  }
  if (page.referrerPolicy) {
    html = html.replace(
      /<\/head>/i,
      `<meta name="referrer" content="${escapeHtml(page.referrerPolicy)}">\n  </head>`,
    );
  }
  html = html.replace(/<title>[\s\S]*?<\/title>/i, `<title>${escapeHtml(page.title)}</title>`);
  html = replaceMeta(html, "name", "description", page.description);
  html = replaceMeta(html, "name", "robots", page.noindex ? "noindex, nofollow, noarchive" : "index, follow, max-image-preview:large");
  html = replaceMeta(html, "property", "og:title", page.title);
  html = replaceMeta(html, "property", "og:description", page.description);
  html = replaceMeta(html, "property", "og:url", page.canonical);
  html = replaceMeta(html, "property", "og:image", page.image);
  html = replaceMeta(html, "name", "twitter:title", page.title);
  html = replaceMeta(html, "name", "twitter:description", page.description);
  html = replaceMeta(html, "name", "twitter:image", page.image);
  html = html.replace(/<link\s+rel="canonical"\s+href="[^"]*"\s*\/>/i, `<link rel="canonical" href="${page.canonical}" />`);
  if (metrikaCounterId) {
    html = html.replace(
      "</head>",
      `    <meta name="yandex-metrika-counter-id" content="${metrikaCounterId}" />\n  </head>`,
    );
  }
  const jsonLd = page.schema.map((value) => `<script type="application/ld+json" data-vedicway-seo-schema="prerender">${safeJson(value)}</script>`).join("\n    ");
  html = html.replace("</head>", `    ${jsonLd}\n  </head>`);
  html = html.replace('<div id="root"></div>', `<div id="root">${preludeStyle}${page.body}</div>`);
  return html.replaceAll("https://vedicway.ru", ORIGIN);
}

function replaceMeta(html, attribute, key, content) {
  const expression = new RegExp(`<meta\\s+${attribute}="${escapeRegExp(key)}"\\s+content="[^"]*"\\s*\\/>`, "i");
  const tag = `<meta ${attribute}="${key}" content="${escapeHtml(content)}" />`;
  return expression.test(html) ? html.replace(expression, tag) : html.replace("</head>", `    ${tag}\n  </head>`);
}

function homeBody() {
  return `<main class="seo-prerender" data-yandex-first-screen>
    <section>
      <nav aria-label="Основная навигация"><a href="/">Главная</a><a href="/guide">Гид по астрологии</a><a href="/blog">Блог</a></nav>
      <h1>Ведическая натальная карта онлайн</h1>
      <p>Рассчитайте сидерическую карту по дате, времени и месту рождения. Сервис покажет положения планет и объяснит их в рамках традиции джйотиш.</p>
      <p data-yandex-proof="calculation-inputs">Для расчёта нужны дата, точное время и место рождения.</p>
      <p data-yandex-proof="result-preview">До расчёта можно посмотреть интерактивный пример готовой карты, объяснений и вопросов к себе.</p>
      <form id="natal-chart-form" data-yandex-form="natal-chart-form" action="/api/v1/charts" method="post">
        <label>Дата рождения <input name="birth_date" type="date" /></label>
        <label>Время рождения <input name="birth_time" type="time" /></label>
        <label>Место рождения <input name="birth_place" /></label>
        <button data-yandex-action="natal-chart-form" type="submit">Рассчитать карту</button>
      </form>
    </section>
    <section aria-labelledby="faq-prerender-title"><h2 id="faq-prerender-title">Часто задаваемые вопросы</h2>${faqEntries.map(([q, a]) => `<details><summary>${escapeHtml(q)}</summary><p>${escapeHtml(a)}</p></details>`).join("")}</section>
  </main>`;
}

function guideBody() {
  return `<main class="seo-prerender" data-yandex-first-screen>
    <nav aria-label="Хлебные крошки"><a href="/">Главная</a><span>Гид по астрологии</span></nav>
    <h1>Гид по астрологии</h1>
    <p>Практический гид по ведической астрологии с материалами о натальной карте, планетах, домах, аспектах и последовательном чтении джйотиш.</p>
    <section data-yandex-proof="guide-topics" aria-labelledby="guide-topics-title">
      <h2 id="guide-topics-title">Четыре раздела, единая библиотека</h2>
      <p>Категория, уровень сложности и поиск помогают собрать точную подборку из 202 материалов.</p>
      <ol>
        <li><h3>Основы астрологии</h3><p>Термины, устройство сидерической карты и базовый язык джйотиша.</p></li>
        <li><h3>Планеты и дома</h3><p>Грахи, бхавы и связи внутри натальной карты.</p></li>
        <li><h3>Время и циклы</h3><p>Даши, транзиты, панчанга и расчётные правила.</p></li>
        <li><h3>Практика чтения карты</h3><p>Алгоритмы, проверка гипотез и синтез показателей.</p></li>
      </ol>
      <p>Каждая статья заранее отмечена уровнем Новичок или Эксперт.</p>
    </section>
    <a data-yandex-action="guide-calculate-link" href="/">Рассчитать карту</a>
  </main>`;
}

function blogBody() {
  return `<main class="seo-prerender" data-yandex-first-screen>
    <nav aria-label="Хлебные крошки"><a href="/">Главная</a><span>Блог</span></nav>
    <h1>Блог VedicWay</h1>
    <p>Блог о ведической астрологии с материалами о натальных картах, планетах, прогнозах и практических методах чтения джйотиш.</p>
    <section data-yandex-proof="blog-topics" aria-label="Темы блога"><h2>Редакционные материалы</h2><p>Прогностика, практика чтения натальной карты и разбор сложных астрологических приёмов.</p></section>
    <a data-yandex-action="blog-calculate-link" href="/">Рассчитать карту</a>
  </main>`;
}

function legalBody(title, description) {
  return `<main class="seo-prerender" data-legal-prerender>
    <nav aria-label="Хлебные крошки"><a href="/">Главная</a><span>${escapeHtml(title)}</span></nav>
    <h1>${escapeHtml(title)}</h1>
    <p>${escapeHtml(description)}</p>
    <p>Полный актуальный текст документа, реквизиты оператора и дата редакции доступны на этой странице после загрузки приложения.</p>
  </main>`;
}

function trustBody(page) {
  return `<main class="seo-prerender" data-yandex-first-screen>
    <nav aria-label="Хлебные крошки"><a href="/">Главная</a><span>${escapeHtml(page.title)}</span></nav>
    <article>
      <header><span>Прозрачность VedicWay</span><h1>${escapeHtml(page.title)}</h1><p>${escapeHtml(page.lead)}</p></header>
      ${page.sections.map(([title, text]) => `<section><h2>${escapeHtml(title)}</h2><p>${escapeHtml(text)}</p></section>`).join("")}
      <nav aria-label="Дополнительная информация"><a href="/about">О сервисе</a><a href="/methodology">Метод расчёта</a><a href="/editorial-policy">Редакционная политика</a></nav>
    </article>
  </main>`;
}

async function rewritePublicOrigin(filename) {
  const path = resolve(DIST, filename);
  let content = await readFile(path, "utf8");
  content = content.replaceAll("https://vedicway.ru", ORIGIN);
  if (filename === "robots.txt") {
    content = content.replace(/^Host:\s*.*$/m, `Host: ${originUrl.hostname}`);
  }
  await writeFile(path, content, "utf8");
}

function safeJson(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>\"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '\"': "&quot;" })[character]);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const DIST = resolve("dist");
const template = await readFile(resolve(DIST, "index.html"), "utf8");

const faqEntries = [
  ["Что такое натальная карта и как работает сервис VedicWay?", "Натальная карта показывает положение небесных тел в момент рождения. VedicWay сопоставляет дату, точное время и координаты места с астрономическими эфемеридами, а затем строит карту и её объяснение."],
  ["Какие данные нужны для расчёта?", "Нужны имя, дата, максимально точное время и город рождения. По городу сервис определяет координаты и исторический часовой пояс."],
  ["Можно ли получить натальную карту без времени рождения?", "Можно получить ограниченный результат, но без времени нельзя надёжно определить лагну, дома и показатели, чувствительные к минутам."],
  ["Чем ведическая астрология отличается от западной?", "VedicWay использует сидерический зодиак, айанамшу Lahiri, накшатры и дома от лагны."],
  ["Насколько точен разбор?", "Положения небесных тел рассчитываются по эфемеридам, а надёжность домов зависит от точности времени рождения."]
];

const pages = [
  {
    output: "index.html",
    title: "Натальная карта онлайн с персональным разбором | VedicWay",
    description: "Рассчитайте натальную карту онлайн по дате, точному времени и месту рождения. Получите наглядную карту и подробное персональное объяснение VedicWay.",
    canonical: "https://vedicway.ru/",
    image: "https://vedicway.ru/assets/hero-space.png",
    body: homeBody(),
    schema: [
      {
        "@context": "https://schema.org",
        "@type": "Organization",
        name: "VedicWay",
        url: "https://vedicway.ru/",
        logo: "https://vedicway.ru/assets/brand-mark.png",
        email: "support@vedicway.ru"
      },
      {
        "@context": "https://schema.org",
        "@type": "WebSite",
        name: "VedicWay",
        url: "https://vedicway.ru/",
        inLanguage: "ru-RU"
      },
      {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: faqEntries.map(([name, text]) => ({
          "@type": "Question",
          name,
          acceptedAnswer: { "@type": "Answer", text }
        }))
      }
    ]
  },
  {
    output: "guide/index.html",
    title: "Натальная карта простыми словами — гид VedicWay",
    description: "Понятные статьи о натальной карте: планеты, дома, аспекты и последовательное чтение астрологических символов в гиде VedicWay.",
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
  }
];

for (const page of pages) {
  const target = resolve(DIST, page.output);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, renderPage(page), "utf8");
}

function renderPage(page) {
  let html = template;
  html = html.replace(/<title>[\s\S]*?<\/title>/i, `<title>${escapeHtml(page.title)}</title>`);
  html = replaceMeta(html, "name", "description", page.description);
  html = replaceMeta(html, "name", "robots", "index, follow, max-image-preview:large");
  html = replaceMeta(html, "property", "og:title", page.title);
  html = replaceMeta(html, "property", "og:description", page.description);
  html = replaceMeta(html, "property", "og:url", page.canonical);
  html = replaceMeta(html, "property", "og:image", page.image);
  html = replaceMeta(html, "name", "twitter:title", page.title);
  html = replaceMeta(html, "name", "twitter:description", page.description);
  html = replaceMeta(html, "name", "twitter:image", page.image);
  html = html.replace(/<link\s+rel="canonical"\s+href="[^"]*"\s*\/>/i, `<link rel="canonical" href="${page.canonical}" />`);
  const jsonLd = page.schema.map((value) => `<script type="application/ld+json">${safeJson(value)}</script>`).join("\n    ");
  html = html.replace("</head>", `    ${jsonLd}\n  </head>`);
  html = html.replace('<div id="root"></div>', `<div id="root">${preludeStyle}${page.body}</div>`);
  return html;
}

function replaceMeta(html, attribute, key, content) {
  const expression = new RegExp(`<meta\\s+${attribute}="${escapeRegExp(key)}"\\s+content="[^"]*"\\s*\\/>`, "i");
  const tag = `<meta ${attribute}="${key}" content="${escapeHtml(content)}" />`;
  return expression.test(html) ? html.replace(expression, tag) : html.replace("</head>", `    ${tag}\n  </head>`);
}

function homeBody() {
  return `<main class="seo-prerender" data-yandex-first-screen>
    <section>
      <nav aria-label="Основная навигация"><a href="/">Главная</a><a href="/guide">Гид по астрологии</a></nav>
      <h1>ПОЗНАЙ СЕБЯ ЧЕРЕЗ КОСМОС</h1>
      <p>Натальная карта раскрывает ваш уникальный рисунок судьбы. Узнайте своё предназначение и скрытые ресурсы.</p>
      <p data-yandex-proof="calculation-inputs">Для расчёта нужны дата, точное время и место рождения.</p>
      <p data-yandex-proof="result-preview">До расчёта можно посмотреть интерактивный пример готовой карты, объяснений и вопросов к себе.</p>
      <form data-yandex-form="natal-chart-form" action="/api/v1/charts" method="post">
        <label>Имя <input name="name" autocomplete="name" /></label>
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
    <p>Спокойные и точные объяснения, которые помогают читать натальную карту по смыслу, а не заучивать отдельные символы.</p>
    <section data-yandex-proof="guide-topics" aria-label="Темы гида"><h2>Материалы о натальной карте</h2><p>Планеты, знаки, дома, аспекты и последовательное чтение карты.</p></section>
    <a data-yandex-action="guide-calculate-link" href="/">Рассчитать карту</a>
  </main>`;
}

const preludeStyle = `<style>.seo-prerender{min-height:100vh;padding:48px;color:#f5eee4;background:#050505;font-family:Georgia,serif}.seo-prerender nav{display:flex;gap:24px}.seo-prerender a{color:#ef7a2e}.seo-prerender h1{max-width:900px;font-size:clamp(42px,7vw,92px)}.seo-prerender p,.seo-prerender label{font-family:Arial,sans-serif;line-height:1.6}.seo-prerender form{display:grid;gap:12px;max-width:560px}.seo-prerender label{display:grid;gap:6px}.seo-prerender input,.seo-prerender button{min-height:44px}</style>`;

function safeJson(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>\"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '\"': "&quot;" })[character]);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

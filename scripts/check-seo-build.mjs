import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";

const ROOT = resolve(".");
const DIST = resolve(ROOT, "dist");
const ARTICLE_ROOT = resolve(ROOT, "content", "astrology-guide", "articles");
const expectedOrigin = (
  process.env.VITE_PUBLIC_ORIGIN ||
  process.env.VEDICWAY_PUBLIC_ORIGIN ||
  "http://localhost:5173"
).replace(/\/$/, "");
const publicPages = [
  ["index.html", "/", true, "Натальная карта онлайн"],
  ["guide/index.html", "/guide", false, "Гид по астрологии"],
  ["blog/index.html", "/blog", false, "Блог VedicWay"],
  ["about/index.html", "/about", true, "О сервисе VedicWay"],
  ["methodology/index.html", "/methodology", true, "Метод расчёта натальной карты"],
  ["editorial-policy/index.html", "/editorial-policy", true, "Редакционная политика VedicWay"],
  ["report-example/index.html", "/report-example", false, "Пример полного отчёта по натальной карте"],
  ["legal/offer/index.html", "/legal/offer", false, "Публичная оферта и пользовательское соглашение"],
  ["legal/privacy/index.html", "/legal/privacy", false, "Политика обработки персональных данных"],
  ["legal/personal-data-consent/index.html", "/legal/personal-data-consent", false, "Согласие на обработку персональных данных"],
  ["legal/cookies/index.html", "/legal/cookies", false, "Политика использования cookies"],
];

for (const [filename, pathname, indexable, expectedH1] of publicPages) {
  const canonical = `${expectedOrigin}${pathname}`;
  const html = await readFile(resolve(DIST, filename), "utf8");
  assert(html.match(/<title>[^<]{15,}<\/title>/i), `${filename}: пустой title`);
  assert(
    html.match(/<meta\s+name="description"\s+content="[^"]{70,}"/i),
    `${filename}: пустой или короткий description`,
  );
  assert(
    html.includes(`<link rel="canonical" href="${canonical}"`),
    `${filename}: неверный canonical`,
  );
  assert(
    html.includes(
      indexable
        ? 'content="index, follow, max-image-preview:large"'
        : 'content="noindex, follow, noarchive"',
    ),
    `${filename}: неверный robots для статического fallback`,
  );
  assert(
    (html.match(/<h1(?:\s|>)/gi) ?? []).length === 1,
    `${filename}: нужен ровно один H1`,
  );
  assert(
    html.includes(`<h1>${expectedH1}</h1>`) ||
      html.includes(`<h1 id="hero-title">\n            ${expectedH1}`),
    `${filename}: первый HTML содержит неверный H1`,
  );
  assert(
    (html.match(/name="yandex-metrika-counter-id"/gi) ?? []).length <= 1,
    `${filename}: счётчик Метрики продублирован`,
  );
  for (const match of html.matchAll(
    /<script[^>]+type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi,
  )) {
    JSON.parse(match[1]);
  }
}

for (const [filename, expectedH1] of [
  ["chart/index.html", "Личная натальная карта"],
  ["rectification/index.html", "Уточнение времени рождения"],
]) {
  const html = await readFile(resolve(DIST, filename), "utf8");
  assert(
    html.includes('content="noindex, nofollow, noarchive"'),
    `${filename}: приватная страница должна быть noindex`,
  );
  assert(
    html.includes(`<h1>${expectedH1}</h1>`),
    `${filename}: первый HTML содержит неверный H1`,
  );
  assert(
    !html.includes('<link rel="canonical"'),
    `${filename}: приватная страница не должна канонизироваться на публичный URL`,
  );
}

const robots = await readFile(resolve(DIST, "robots.txt"), "utf8");
assert(robots.includes("Disallow: /api/"), "robots.txt: API должен оставаться закрытым");
assert(robots.includes("Disallow: /chart/"), "robots.txt: приватные карты должны оставаться закрытыми");
assert(
  !robots.includes("Disallow: /access/recovery") &&
    !robots.includes("Disallow: /privacy/request"),
  "robots.txt: noindex-страницы должны оставаться доступными для обхода",
);

const sitemap = await readFile(resolve(DIST, "sitemap.xml"), "utf8");
for (const [, pathname, indexable] of publicPages) {
  const canonical = `${expectedOrigin}${pathname}`;
  assert(
    sitemap.includes(`<loc>${canonical}</loc>`) === indexable,
    `sitemap.xml: неверное присутствие ${canonical}`,
  );
}

const articleDirectories = await readdir(ARTICLE_ROOT, { withFileTypes: true });
let checkedArticles = 0;
for (const directory of articleDirectories) {
  if (!directory.isDirectory()) continue;
  const article = await readFile(resolve(ARTICLE_ROOT, directory.name, "article.html"), "utf8");
  const manifest = await readFile(resolve(ARTICLE_ROOT, directory.name, "manifest.json"), "utf8");
  assert(
    !/href=["']\/chart["']/i.test(article) && !/"\/chart"/.test(manifest),
    `${directory.name}: осталась ссылка на несуществующий /chart`,
  );
  assert(
    !/(?:Рљ|Р°|Рµ|РЅ|Рѕ|С‚|СЃ|СЏ|СЂ){3,}/.test(article),
    `${directory.name}: обнаружена битая кодировка`,
  );
  checkedArticles += 1;
}

assert(checkedArticles === 202, `ожидалось 202 статьи, найдено ${checkedArticles}`);
console.log(`SEO build contract passed: ${publicPages.length} pages, ${checkedArticles} articles.`);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

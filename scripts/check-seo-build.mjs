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
  ["index.html", "/"],
  ["guide/index.html", "/guide"],
  ["blog/index.html", "/blog"],
  ["about/index.html", "/about"],
  ["methodology/index.html", "/methodology"],
  ["editorial-policy/index.html", "/editorial-policy"],
];

for (const [filename, pathname] of publicPages) {
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
    html.includes('content="index, follow, max-image-preview:large"'),
    `${filename}: публичная страница закрыта от индексации`,
  );
  assert(
    (html.match(/<h1(?:\s|>)/gi) ?? []).length === 1,
    `${filename}: нужен ровно один H1`,
  );
  for (const match of html.matchAll(
    /<script[^>]+type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi,
  )) {
    JSON.parse(match[1]);
  }
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
for (const [, pathname] of publicPages) {
  const canonical = `${expectedOrigin}${pathname}`;
  assert(sitemap.includes(`<loc>${canonical}</loc>`), `sitemap.xml: нет ${canonical}`);
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

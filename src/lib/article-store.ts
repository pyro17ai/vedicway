export const ARTICLE_STORE_KEY = "vedicway:guide-articles:v1";

export const ARTICLE_CATEGORIES = [
  "Основы астрологии",
  "Планеты и дома",
  "Практика чтения карты",
  "Время и циклы",
] as const;

export type ArticleStatus = "draft" | "published";

export type GuideArticle = {
  id: string;
  title: string;
  slug: string;
  category: string;
  excerpt: string;
  content: string;
  seoTitle: string;
  metaDescription: string;
  focusKeyphrase: string;
  canonicalUrl: string;
  author: string;
  status: ArticleStatus;
  createdAt: string;
  updatedAt: string;
  publishedAt: string | null;
};

const transliteration: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i", й: "y",
  к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f",
  х: "h", ц: "ts", ч: "ch", ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
};

function makeId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `article-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function slugifyArticleTitle(value: string) {
  return value
    .trim()
    .toLocaleLowerCase("ru")
    .split("")
    .map((letter) => transliteration[letter] ?? letter)
    .join("")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 90);
}

export function createArticleDraft(): GuideArticle {
  const now = new Date().toISOString();
  return {
    id: makeId(),
    title: "",
    slug: "",
    category: ARTICLE_CATEGORIES[0],
    excerpt: "",
    content: "",
    seoTitle: "",
    metaDescription: "",
    focusKeyphrase: "",
    canonicalUrl: "",
    author: "Редакция VedicWay",
    status: "draft",
    createdAt: now,
    updatedAt: now,
    publishedAt: null,
  };
}

function isGuideArticle(value: unknown): value is GuideArticle {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<GuideArticle>;
  return typeof candidate.id === "string"
    && typeof candidate.title === "string"
    && typeof candidate.slug === "string"
    && (candidate.status === "draft" || candidate.status === "published");
}

export function readArticles(): GuideArticle[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(ARTICLE_STORE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isGuideArticle).sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  } catch {
    return [];
  }
}

export function writeArticle(article: GuideArticle) {
  const current = readArticles();
  const next = [article, ...current.filter((item) => item.id !== article.id)]
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  window.localStorage.setItem(ARTICLE_STORE_KEY, JSON.stringify(next));
  return next;
}

export function removeArticle(articleId: string) {
  const next = readArticles().filter((article) => article.id !== articleId);
  window.localStorage.setItem(ARTICLE_STORE_KEY, JSON.stringify(next));
  return next;
}

export function publishedArticles() {
  return readArticles()
    .filter((article) => article.status === "published")
    .sort((left, right) => (right.publishedAt ?? right.updatedAt).localeCompare(left.publishedAt ?? left.updatedAt));
}

export function articleBySlug(slug: string) {
  return publishedArticles().find((article) => article.slug === slug) ?? null;
}

export function uniqueArticleSlug(titleOrSlug: string, articleId: string, articles = readArticles()) {
  const base = slugifyArticleTitle(titleOrSlug) || "material";
  const occupied = new Set(articles.filter((article) => article.id !== articleId).map((article) => article.slug));
  if (!occupied.has(base)) return base;
  let suffix = 2;
  while (occupied.has(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}

import { beforeEach, describe, expect, it } from "vitest";

import {
  ARTICLE_STORE_KEY,
  articleBySlug,
  articleMediaToken,
  createArticleDraft,
  mediaIdFromArticleBlock,
  publishedArticles,
  readArticles,
  slugifyArticleTitle,
  uniqueArticleSlug,
  writeArticle,
} from "./article-store";

describe("article-store", () => {
  beforeEach(() => window.localStorage.removeItem(ARTICLE_STORE_KEY));

  it("создаёт читаемый латинский адрес из русского заголовка", () => {
    expect(slugifyArticleTitle("Как читать натальную карту: первый дом"))
      .toBe("kak-chitat-natalnuyu-kartu-pervyy-dom");
  });

  it("сохраняет черновик и не показывает его в публичной библиотеке", () => {
    const draft = { ...createArticleDraft(), title: "Черновик", slug: "chernovik" };
    writeArticle(draft);

    expect(readArticles()).toHaveLength(1);
    expect(publishedArticles()).toHaveLength(0);
    expect(articleBySlug("chernovik")).toBeNull();
  });

  it("публикует материал и защищает адрес от дублей", () => {
    const first = {
      ...createArticleDraft(),
      title: "Первый дом",
      slug: "pervyy-dom",
      status: "published" as const,
      publishedAt: new Date().toISOString(),
    };
    writeArticle(first);

    const second = createArticleDraft();
    expect(uniqueArticleSlug("Первый дом", second.id)).toBe("pervyy-dom-2");
    expect(articleBySlug("pervyy-dom")?.title).toBe("Первый дом");
  });

  it("мигрирует старые локальные статьи на медиамодель v2", () => {
    window.localStorage.setItem(ARTICLE_STORE_KEY, JSON.stringify([{
      ...createArticleDraft(),
      schemaVersion: undefined,
      coverImage: undefined,
      bodyMedia: undefined,
      title: "Старая статья",
    }]));

    const [article] = readArticles();
    expect(article.schemaVersion).toBe("guide-article.v2");
    expect(article.coverImage).toBeNull();
    expect(article.bodyMedia).toEqual([]);
  });

  it("создаёт и распознаёт безопасный маркер изображения", () => {
    expect(articleMediaToken("media_123-abc")).toBe("{{media:media_123-abc}}");
    expect(mediaIdFromArticleBlock("  {{media:media_123-abc}}  ")).toBe("media_123-abc");
    expect(mediaIdFromArticleBlock("<img src=x onerror=alert(1)>")).toBeNull();
  });
});

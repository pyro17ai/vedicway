import { beforeEach, describe, expect, it } from "vitest";

import {
  ARTICLE_STORE_KEY,
  articleBySlug,
  createArticleDraft,
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
});

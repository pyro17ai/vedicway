import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  addPublicComment,
  publicArticle,
  publicComments,
  type ContentArticle,
} from "../lib/content-api";
import { ArticlePage } from "./ArticlePage";

vi.mock("../lib/content-api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/content-api")>();
  return {
    ...original,
    publicArticle: vi.fn(),
    publicComments: vi.fn(),
    addPublicComment: vi.fn(),
  };
});

const related: ContentArticle["related"] = Array.from({ length: 3 }, (_, index) => ({
  id: `related-${index}`,
  section: "blog" as const,
  difficulty: index === 2 ? ("expert" as const) : ("beginner" as const),
  difficulty_label: index === 2 ? "Эксперт" : "Новичок",
  title: `Связанный материал ${index + 1}`,
  slug: `svyazannyy-material-${index + 1}`,
  category: "Практика",
  excerpt: "Короткое описание связанного материала.",
  cover_image_url: "/assets/hero-space-light.webp",
  cover_image_alt: "Космическое пространство",
  canonical_url: `https://vedicway.ru/blog/svyazannyy-material-${index + 1}`,
  author_name: "Редакция VedicWay",
  tags: ["практика"],
  updated_at: "2026-07-28T10:00:00Z",
  published_at: "2026-07-28T10:00:00Z",
  coverImage: null,
}));

const article: ContentArticle = {
  id: "blog-1",
  section: "blog",
  difficulty: "expert",
  difficulty_label: "Эксперт",
  title: "Как проверять астрологический прогноз",
  slug: "kak-proveryat-prognoz",
  category: "Практика",
  excerpt: "Проверяем прогноз по периодам и транзитам без поспешных выводов.",
  cover_image_url: "/assets/results-space-v2.png",
  cover_image_alt: "Карта прогноза",
  canonical_url: "https://vedicway.ru/blog/kak-proveryat-prognoz",
  author_name: "Редакция VedicWay",
  tags: ["прогноз", "проверка"],
  updated_at: "2026-07-28T10:00:00Z",
  published_at: "2026-07-28T10:00:00Z",
  coverImage: null,
  content_html:
    "<h2>Начните с периода</h2><p>Период задаёт контекст прогноза.</p>",
  content_sections: [
    "<h2>Начните с периода</h2><p>Период задаёт контекст прогноза.</p>",
    "<aside data-kind=\"note\"><p>Один транзит не даёт итог.</p></aside><table><tbody><tr><th>Шаг</th><td>Проверка</td></tr></tbody></table>",
  ],
  content_format: "html.v1",
  body_media_ids: [],
  seo_title: "Как проверять астрологический прогноз",
  meta_description:
    "Практический порядок проверки прогноза по периодам, транзитам и событиям.",
  focus_keyphrase: "проверка астрологического прогноза",
  schema_extra: {
    citation: ["https://example.org/source"],
  },
  status: "published",
  revision: 1,
  created_at: "2026-07-28T10:00:00Z",
  word_count: 900,
  reading_minutes: 6,
  comment_count: 0,
  cover_media_id: null,
  bodyMedia: [],
  related,
};

describe("страница статьи", () => {
  beforeEach(() => {
    vi.mocked(publicArticle).mockResolvedValue(article);
    vi.mocked(publicComments).mockResolvedValue({ items: [] });
    vi.mocked(addPublicComment).mockResolvedValue({
      id: "comment-1",
      display_name: "Анна",
      body: "Полезный порядок проверки.",
      created_at: "2026-07-28T12:00:00Z",
    });
  });

  it("выводит хлебные крошки, два CTA, прогресс, HTML-блоки и три разные рекомендации", async () => {
    render(
      <ArticlePage
        section="blog"
        slug="kak-proveryat-prognoz"
        onNavigate={vi.fn()}
      />,
    );

    expect(
      await screen.findByRole("heading", {
        name: "Как проверять астрологический прогноз",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Блог" })[1]).toHaveAttribute(
      "href",
      "/blog",
    );
    expect(screen.getAllByRole("link", { name: "Рассчитать карту" })).toHaveLength(
      2,
    );
    expect(screen.getByTestId("reading-progress")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Начните с периода" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: /Связанный материал/ }),
    ).toHaveLength(3);
    expect(screen.getAllByText("Эксперт").length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByRole("heading", { name: "Источники и редакция" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /example\.org/ })).toHaveAttribute(
      "href",
      "https://example.org/source",
    );
    const relatedImages = document.querySelectorAll(
      ".article-related__media img",
    );
    expect(relatedImages).toHaveLength(3);
    expect(
      Array.from(relatedImages).every(
        (image) => image.getAttribute("loading") === "lazy",
      ),
    ).toBe(true);
    let schema: Record<string, unknown> = {};
    await waitFor(() => {
      schema = JSON.parse(
        document.head.querySelector<HTMLScriptElement>(
          'script[data-vedicway-seo-schema]',
        )?.text ?? "{}",
      );
      expect(schema).toHaveProperty("@graph");
    });
    const graph = schema["@graph"] as Array<Record<string, unknown>>;
    expect(graph[0]).toMatchObject({
      "@type": "BlogPosting",
      wordCount: 900,
      isAccessibleForFree: true,
      commentCount: 0,
    });
  });

  it("сохраняет серверный снимок статьи при сбое повторного запроса", async () => {
    vi.mocked(publicArticle).mockRejectedValueOnce(new Error("offline"));
    vi.mocked(publicComments).mockRejectedValueOnce(new Error("offline"));

    render(
      <ArticlePage
        section="blog"
        slug="kak-proveryat-prognoz"
        onNavigate={vi.fn()}
        initialArticle={article}
        initialComments={[]}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "Как проверять астрологический прогноз",
      }),
    ).toBeInTheDocument();
    await waitFor(() => expect(publicArticle).toHaveBeenCalled());
    expect(
      screen.queryByRole("heading", { name: "Материал не найден" }),
    ).not.toBeInTheDocument();
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      "content",
      expect.stringContaining("index"),
    );
  });

  it("даёт любому читателю добавить комментарий", async () => {
    const user = userEvent.setup();
    render(
      <ArticlePage
        section="blog"
        slug="kak-proveryat-prognoz"
        onNavigate={vi.fn()}
      />,
    );

    await screen.findByRole("heading", {
      name: "Как проверять астрологический прогноз",
    });
    await user.type(screen.getByLabelText("Ваше имя"), "Анна");
    await user.type(
      screen.getByLabelText("Комментарий"),
      "Полезный порядок проверки.",
    );
    await user.click(screen.getByRole("button", { name: "Опубликовать" }));

    expect(addPublicComment).toHaveBeenCalledWith(
      "blog",
      "kak-proveryat-prognoz",
      {
        display_name: "Анна",
        body: "Полезный порядок проверки.",
        website: "",
      },
    );
    expect(
      await screen.findByText("Полезный порядок проверки."),
    ).toBeInTheDocument();
  });
});

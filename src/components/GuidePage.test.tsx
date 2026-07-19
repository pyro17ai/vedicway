import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { publicArticles, type ContentArticle } from "../lib/admin-api";
import { GuidePage } from "./GuidePage";

vi.mock("../lib/admin-api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/admin-api")>();
  return { ...original, publicArticles: vi.fn() };
});

const article: ContentArticle = {
  id: "article-1",
  title: "Как читать первый дом",
  slug: "kak-chitat-pervyy-dom",
  category: "Основы астрологии",
  excerpt: "Последовательное объяснение первого дома натальной карты.",
  content: "Первый дом описывает способ проявления человека.",
  cover_media_id: null,
  body_media_ids: [],
  cover_image_url: null,
  cover_image_alt: "",
  seo_title: "Как читать первый дом",
  meta_description: "Подробное объяснение первого дома натальной карты.",
  focus_keyphrase: "первый дом",
  canonical_url: "https://vedicway.ru/guide/kak-chitat-pervyy-dom",
  author_name: "Редакция VedicWay",
  status: "published",
  revision: 1,
  created_at: "2026-07-19T10:00:00Z",
  updated_at: "2026-07-19T10:00:00Z",
  published_at: "2026-07-19T10:00:00Z",
  coverImage: null,
  bodyMedia: [],
};

describe("GuidePage", () => {
  beforeEach(() => {
    vi.mocked(publicArticles).mockResolvedValue({ items: [article] });
  });

  it("выдаёт опубликованным материалам обычные индексируемые ссылки", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(<GuidePage onNavigate={onNavigate} />);

    const cover = await screen.findByRole("link", { name: `Открыть: ${article.title}` });
    const read = screen.getByRole("link", { name: `Читать: ${article.title}` });

    expect(cover).toHaveAttribute("href", `/guide/${article.slug}`);
    expect(read).toHaveAttribute("href", `/guide/${article.slug}`);

    await user.click(read);
    expect(onNavigate).toHaveBeenCalledWith(`/guide/${article.slug}`);
  });
});

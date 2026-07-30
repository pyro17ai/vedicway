import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  publicArticles,
  type ContentArticleSummary,
} from "../lib/content-api";
import { BlogPage } from "./BlogPage";
import { GuidePage } from "./GuidePage";

vi.mock("../lib/content-api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/content-api")>();
  return { ...original, publicArticles: vi.fn() };
});

const articles: ContentArticleSummary[] = [
  {
    id: "article-1",
    section: "guide",
    difficulty: "beginner",
    difficulty_label: "Новичок",
    title: "Как читать первый дом",
    slug: "kak-chitat-natalnuyu-kartu",
    category: "Основы астрологии",
    excerpt: "Последовательное объяснение первого дома натальной карты.",
    cover_image_url: "/assets/results-space-v2.png",
    cover_image_alt: "Натальная карта",
    canonical_url: "https://vedicway.ru/guide/kak-chitat-natalnuyu-kartu",
    author_name: "Редакция VedicWay",
    tags: ["дома", "основы"],
    updated_at: "2026-07-28T10:00:00Z",
    published_at: "2026-07-28T10:00:00Z",
    coverImage: null,
  },
  {
    id: "article-2",
    section: "guide",
    difficulty: "expert",
    difficulty_label: "Эксперт",
    title: "Сила управителя лагны",
    slug: "sila-upravitelya-lagny",
    category: "Практика чтения карты",
    excerpt: "Продвинутая проверка силы управителя первого дома.",
    cover_image_url: "/assets/hero-space-light.webp",
    cover_image_alt: "Космическая карта",
    canonical_url: "https://vedicway.ru/guide/sila-upravitelya-lagny",
    author_name: "Редакция VedicWay",
    tags: ["лагна"],
    updated_at: "2026-07-28T10:00:00Z",
    published_at: "2026-07-28T10:00:00Z",
    coverImage: null,
  },
];

describe("контентные разделы", () => {
  beforeEach(() => {
    vi.mocked(publicArticles).mockResolvedValue({
      items: articles,
      total: articles.length,
    });
  });

  it("ищет материалы, фильтрует уровень и сохраняет обычные индексируемые ссылки", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(<GuidePage onNavigate={onNavigate} />);

    expect(
      await screen.findByRole("heading", { name: "Как читать первый дом" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Библиотека знаний VedicWay")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Практический гид по ведической астрологии с материалами о натальной карте, планетах, домах, аспектах и последовательном чтении джйотиш.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Четыре раздела, единая библиотека",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(
        "Четыре раздела гида и два уровня сложности",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "Опубликованные статьи гида",
      }),
    ).toHaveAttribute("aria-valuenow", "2");
    expect(
      screen.getByRole("button", {
        name: "Показать раздел: Основы астрологии",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Планеты и дома").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Время и циклы").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Практика чтения карты").length).toBeGreaterThan(0);
    const schemas = Array.from(
      document.head.querySelectorAll<HTMLScriptElement>(
        'script[data-vedicway-seo-schema]',
      ),
      (element) => JSON.parse(element.text),
    );
    expect(
      schemas.find((value) => value["@type"] === "CollectionPage")?.mainEntity,
    ).toMatchObject({
      "@type": "ItemList",
      numberOfItems: 2,
    });
    expect(screen.getAllByText("Новичок").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Эксперт").length).toBeGreaterThanOrEqual(2);

    await user.click(
      screen.getByRole("button", {
        name: "Показать раздел: Основы астрологии",
      }),
    );
    expect(
      screen.queryByRole("heading", { name: "Сила управителя лагны" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Эксперт" }));
    expect(
      screen.queryByRole("heading", { name: "Как читать первый дом" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Совпадений нет" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Все уровни" }));
    await user.click(screen.getByRole("button", { name: "Все разделы" }));
    await user.type(
      screen.getByRole("searchbox", { name: "Поиск по статьям" }),
      "первый дом",
    );
    const read = screen.getByRole("link", {
      name: "Читать: Как читать первый дом",
    });
    expect(read).toHaveAttribute(
      "href",
      "/guide/kak-chitat-natalnuyu-kartu",
    );
    await user.click(read);
    expect(onNavigate).toHaveBeenCalledWith(
      "/guide/kak-chitat-natalnuyu-kartu",
    );
  });

  it("показывает отдельный индексируемый хаб блога", async () => {
    vi.mocked(publicArticles).mockResolvedValue({ items: [], total: 0 });
    render(<BlogPage onNavigate={vi.fn()} />);

    expect(
      await screen.findByRole("heading", { name: "Блог VedicWay" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "Четыре раздела, единая библиотека",
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Блог о ведической астрологии с материалами о натальных картах, планетах, прогнозах и практических методах чтения джйотиш.",
      ),
    ).toBeInTheDocument();
    expect(publicArticles).toHaveBeenCalledWith("blog");
    expect(
      screen.getByText("Первый материал уже можно публиковать"),
    ).toBeInTheDocument();
  });

  it("сохраняет серверный список статей при недоступном API", async () => {
    vi.mocked(publicArticles).mockRejectedValueOnce(new Error("offline"));
    render(<GuidePage onNavigate={vi.fn()} initialArticles={articles} />);

    expect(
      screen.getByText("Как читать первый дом"),
    ).toBeInTheDocument();
    await waitFor(() => expect(publicArticles).toHaveBeenCalledWith("guide"));
    expect(
      screen.queryByRole("heading", { name: "Библиотека временно недоступна" }),
    ).not.toBeInTheDocument();
  });
});

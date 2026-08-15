import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import {
  ArrowLeft,
  ArrowUpRight,
  Clock3,
  MessageCircle,
  Sparkles,
} from "lucide-react";
import {
  type FormEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  addPublicComment,
  publicArticle,
  publicComments,
  type ContentArticle,
  type ContentComment,
  type ContentSection,
} from "../lib/content-api";
import { applySeo, publicOrigin } from "../lib/seo";
import { ArticleMedia } from "./ArticleMedia";
import { SiteHeader } from "./SiteHeader";

gsap.registerPlugin(useGSAP, ScrollTrigger);

type ArticlePageProps = {
  section: ContentSection;
  slug: string;
  onNavigate: (path: string) => void;
  initialArticle?: ContentArticle;
  initialComments?: ContentComment[];
};

function plainLeftClick(event: MouseEvent<HTMLAnchorElement>) {
  return (
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
}

function absoluteImage(article: ContentArticle) {
  const source = article.coverImage?.url || article.cover_image_url;
  return source ? new URL(source, publicOrigin()).href : undefined;
}

function articleCitations(article: ContentArticle) {
  const value = article.schema_extra.citation;
  if (!Array.isArray(value)) return [];
  return value.filter(
    (citation): citation is string =>
      typeof citation === "string" && /^https?:\/\//i.test(citation),
  );
}

function citationLabel(value: string) {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function CalculateChartCta({
  position,
  onNavigate,
}: {
  position: "middle" | "end";
  onNavigate: (path: string) => void;
}) {
  const content =
    position === "middle"
      ? {
          kicker: "Проверьте на своей карте",
          title: "Посмотрите, как символы соединяются именно у вас",
          text: "Расчёт даст опорную схему, с которой статья перестанет быть отвлечённой теорией.",
        }
      : {
          kicker: "Следующий шаг",
          title: "Перейдите от чтения к собственной натальной карте",
          text: "Введите данные рождения и получите расчёт, к которому удобно возвращаться во время разбора.",
        };

  return (
    <aside className={`article-cta article-cta--${position}`}>
      <span className="article-cta__mark" aria-hidden="true">
        <Sparkles />
      </span>
      <div>
        <span>{content.kicker}</span>
        <h2>{content.title}</h2>
        <p>{content.text}</p>
      </div>
      <a
        href="/"
        onClick={(event) => {
          if (!plainLeftClick(event)) return;
          event.preventDefault();
          onNavigate("/");
        }}
      >
        Рассчитать карту
        <ArrowUpRight aria-hidden="true" />
      </a>
    </aside>
  );
}

function ReadingProgress({ value }: { value: number }) {
  return (
    <div
      className="article-reading-progress"
      data-testid="reading-progress"
      aria-hidden="true"
    >
      <span style={{ transform: `scaleX(${value})` }} />
    </div>
  );
}

export function ArticlePage({
  section,
  slug,
  onNavigate,
  initialArticle,
  initialComments,
}: ArticlePageProps) {
  const root = useRef<HTMLDivElement>(null);
  const [article, setArticle] = useState<ContentArticle | null>(
    () => initialArticle ?? null,
  );
  const [comments, setComments] = useState<ContentComment[]>(
    () => initialComments ?? [],
  );
  const [loading, setLoading] = useState(() => !initialArticle);
  const [progress, setProgress] = useState(0);
  const [displayName, setDisplayName] = useState("");
  const [commentBody, setCommentBody] = useState("");
  const [website, setWebsite] = useState("");
  const [commentPending, setCommentPending] = useState(false);
  const [commentError, setCommentError] = useState("");

  const hubPath = `/${section}`;
  const articlePath = `${hubPath}/${slug}`;
  const hubName = section === "blog" ? "Блог" : "Гид по астрологии";

  useEffect(() => {
    let active = true;
    const hasServerSnapshot = Boolean(initialArticle);
    setLoading(!hasServerSnapshot);
    Promise.all([
      publicArticle(section, slug),
      publicComments(section, slug).catch(() => ({ items: [] })),
    ])
      .then(([value, commentList]) => {
        if (!active) return;
        setArticle(value);
        setComments(commentList.items);
      })
      .catch(() => {
        if (active && !hasServerSnapshot) {
          setArticle(null);
          setComments([]);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [initialArticle, section, slug]);

  useEffect(() => {
    if (loading) return;
    if (!article) {
      return applySeo({
        title: "Материал не найден | VedicWay",
        description: "Запрошенная статья VedicWay не найдена.",
        path: articlePath,
        noindex: true,
      });
    }
    const canonical =
      article.canonical_url || `${publicOrigin()}${articlePath}`;
    const articleType = section === "blog" ? "BlogPosting" : "Article";
    const rawTitle = article.seo_title || article.title;
    const brandedTitle = rawTitle.includes("VedicWay")
      ? rawTitle
      : `${rawTitle} | VedicWay`;
    return applySeo({
      title: brandedTitle.length <= 60 ? brandedTitle : rawTitle,
      description: article.meta_description || article.excerpt,
      path: articlePath,
      canonicalUrl: canonical,
      image: absoluteImage(article),
      type: "article",
      structuredData: [
        {
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": articleType,
              "@id": `${canonical}#article`,
              headline: article.title,
              description: article.meta_description || article.excerpt,
              image: absoluteImage(article),
              url: canonical,
              inLanguage: "ru-RU",
              datePublished: article.published_at ?? article.updated_at,
              dateModified: article.updated_at,
              educationalLevel:
                article.difficulty === "expert" ? "Advanced" : "Beginner",
              articleSection: article.category,
              keywords:
                article.tags.length > 0
                  ? article.tags
                  : [article.focus_keyphrase].filter(Boolean),
              wordCount: article.word_count,
              isAccessibleForFree: true,
              author: {
                "@type": "Organization",
                "@id": `${publicOrigin()}/about#organization`,
                name: article.author_name,
                url: `${publicOrigin()}/about`,
              },
              publisher: {
                "@type": "Organization",
                "@id": `${publicOrigin()}/about#organization`,
                name: "VedicWay",
                url: publicOrigin(),
                logo: {
                  "@type": "ImageObject",
                  url: `${publicOrigin()}/assets/brand-mark.png`,
                },
              },
              mainEntityOfPage: {
                "@type": "WebPage",
                "@id": canonical,
              },
              commentCount: comments.length,
              interactionStatistic: {
                "@type": "InteractionCounter",
                interactionType: { "@type": "CommentAction" },
                userInteractionCount: comments.length,
              },
              ...article.schema_extra,
            },
            {
              "@type": "BreadcrumbList",
              itemListElement: [
                {
                  "@type": "ListItem",
                  position: 1,
                  name: "Главная",
                  item: `${publicOrigin()}/`,
                },
                {
                  "@type": "ListItem",
                  position: 2,
                  name: hubName,
                  item: `${publicOrigin()}${hubPath}`,
                },
                {
                  "@type": "ListItem",
                  position: 3,
                  name: article.title,
                  item: canonical,
                },
              ],
            },
          ],
        },
      ],
    });
  }, [
    article,
    articlePath,
    comments.length,
    hubName,
    hubPath,
    loading,
    section,
  ]);

  useEffect(() => {
    if (!article) return;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const reading = root.current?.querySelector<HTMLElement>(
          ".article-reading",
        );
        if (!reading) {
          setProgress(0);
          return;
        }
        const bounds = reading.getBoundingClientRect();
        const start = bounds.top + window.scrollY;
        const distance = Math.max(
          1,
          bounds.height - window.innerHeight,
        );
        setProgress(
          Math.min(1, Math.max(0, (window.scrollY - start) / distance)),
        );
      });
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [article]);

  useGSAP(
    () => {
      if (
        !article ||
        !root.current ||
        typeof window.matchMedia !== "function" ||
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ) {
        return;
      }
      gsap.utils
        .toArray<HTMLElement>(
          ".article-rich > *, .article-cta, [data-related-card]",
        )
        .forEach((element) => {
          gsap.fromTo(
            element,
            { autoAlpha: 0, y: 22 },
            {
              autoAlpha: 1,
              y: 0,
              duration: 0.56,
              ease: "power2.out",
              scrollTrigger: {
                trigger: element,
                start: "top 90%",
                once: true,
              },
            },
          );
        });
    },
    {
      scope: root,
      dependencies: [article?.id],
      revertOnUpdate: true,
    },
  );

  const follow = (event: MouseEvent<HTMLAnchorElement>, path: string) => {
    if (!plainLeftClick(event)) return;
    event.preventDefault();
    onNavigate(path);
  };

  const submitComment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (commentPending) return;
    setCommentPending(true);
    setCommentError("");
    try {
      const created = await addPublicComment(section, slug, {
        display_name: displayName.trim(),
        body: commentBody.trim(),
        website,
      });
      if (created.body) setComments((current) => [...current, created]);
      setCommentBody("");
      setWebsite("");
    } catch (error) {
      setCommentError(
        error instanceof Error
          ? error.message
          : "Комментарий не отправлен. Повторите попытку.",
      );
    } finally {
      setCommentPending(false);
    }
  };

  return (
    <div className="content-site" ref={root}>
      <ReadingProgress value={progress} />
      <SiteHeader active={section} onNavigate={onNavigate} />
      <main className="article-page">
        {loading ? (
          <section className="article-state" role="status">
            <span className="content-state__pulse" aria-hidden="true" />
            <p>Загружаем материал…</p>
          </section>
        ) : !article ? (
          <section className="article-state article-state--missing">
            <span>404</span>
            <h1>Материал не найден</h1>
            <p>Адрес мог измениться или публикация ещё не вышла.</p>
            <button type="button" onClick={() => onNavigate(hubPath)}>
              <ArrowLeft aria-hidden="true" />
              Вернуться в {section === "blog" ? "блог" : "гид"}
            </button>
          </section>
        ) : (
          <>
            <nav className="content-breadcrumbs" aria-label="Хлебные крошки">
              <a href="/" onClick={(event) => follow(event, "/")}>
                Главная
              </a>
              <span aria-hidden="true">/</span>
              <a
                href={hubPath}
                onClick={(event) => follow(event, hubPath)}
              >
                {hubName}
              </a>
              <span aria-hidden="true">/</span>
              <span aria-current="page">{article.title}</span>
            </nav>

            <article className="article-reading">
              <header className="article-reading__header">
                <div className="article-reading__meta">
                  <span
                    className={`difficulty-badge difficulty-badge--${article.difficulty}`}
                  >
                    {article.difficulty_label}
                  </span>
                  <span>{article.category}</span>
                </div>
                <h1>{article.title}</h1>
                <p>{article.excerpt}</p>
                <div className="article-reading__byline">
                  <a
                    href="/about"
                    onClick={(event) => follow(event, "/about")}
                  >
                    {article.author_name}
                  </a>
                  <time
                    dateTime={article.published_at ?? article.updated_at}
                  >
                    {formatDate(
                      article.published_at ?? article.updated_at,
                    )}
                  </time>
                  <span>
                    <Clock3 aria-hidden="true" />
                    {article.reading_minutes} мин
                  </span>
                </div>
              </header>

              {article.coverImage ? (
                <ArticleMedia
                  asset={article.coverImage}
                  className="article-reading__cover"
                  sizes="(max-width: 820px) calc(100vw - 32px), 920px"
                  loading="eager"
                />
              ) : article.cover_image_url ? (
                <figure className="article-reading__cover">
                  <img
                    src={article.cover_image_url}
                    alt={article.cover_image_alt}
                    loading="eager"
                    decoding="async"
                    fetchPriority="high"
                  />
                </figure>
              ) : null}

              <div className="article-reading__layout">
                <aside
                  className="article-reading__rail"
                  aria-label="О материале"
                >
                  <span>В материале</span>
                  <p>{article.category}</p>
                  <div>
                    {article.tags.slice(0, 4).map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                </aside>

                <div className="article-reading__content">
                  <section
                    className="article-rich"
                    // Сервер пропускает HTML через nh3 allow-list до сохранения.
                    dangerouslySetInnerHTML={{
                      __html: article.content_sections[0] ?? "",
                    }}
                  />
                  <CalculateChartCta
                    position="middle"
                    onNavigate={onNavigate}
                  />
                  <section
                    className="article-rich"
                    dangerouslySetInnerHTML={{
                      __html: article.content_sections[1] ?? "",
                    }}
                  />
                  <CalculateChartCta position="end" onNavigate={onNavigate} />
                </div>
              </div>
            </article>

            <section
              className="article-sources"
              aria-labelledby="article-sources-title"
            >
              <header>
                <span>Проверяемость материала</span>
                <h2 id="article-sources-title">Источники и редакция</h2>
                <p>
                  Редакция отделяет расчётные данные от трактовки и указывает
                  внешние материалы, на которых основана статья.
                </p>
              </header>
              {articleCitations(article).length > 0 ? (
                <ol>
                  {articleCitations(article).map((citation) => (
                    <li key={citation}>
                      <a href={citation} target="_blank" rel="noopener noreferrer">
                        {citationLabel(citation)}
                        <ArrowUpRight aria-hidden="true" />
                      </a>
                    </li>
                  ))}
                </ol>
              ) : (
                <p>Внешние источники для этой редакции ещё не указаны.</p>
              )}
              <a
                className="article-sources__policy"
                href="/editorial-policy"
                onClick={(event) => follow(event, "/editorial-policy")}
              >
                Как редакция проверяет материалы
                <ArrowUpRight aria-hidden="true" />
              </a>
            </section>

            <section
              className="article-related"
              aria-labelledby="article-related-title"
            >
              <header>
                <span>Продолжить чтение</span>
                <h2 id="article-related-title">Читать далее</h2>
              </header>
              {article.related.length > 0 ? (
                <div className="article-related__grid">
                  {article.related.map((item, index) => {
                    const path = `/${section}/${item.slug}`;
                    return (
                      <a
                        href={path}
                        key={item.id}
                        data-related-card
                        aria-label={item.title}
                        onClick={(event) => follow(event, path)}
                      >
                        {item.coverImage ? (
                          <ArticleMedia
                            asset={item.coverImage}
                            className="article-related__media"
                            sizes="(max-width: 720px) calc(100vw - 32px), (max-width: 1100px) 50vw, 360px"
                            loading="lazy"
                          />
                        ) : item.cover_image_url ? (
                          <span className="article-related__media is-ready">
                            <img
                              src={item.cover_image_url}
                              alt={item.cover_image_alt}
                              loading="lazy"
                              decoding="async"
                            />
                          </span>
                        ) : (
                          <span
                            className="article-related__media article-related__media--empty"
                            aria-hidden="true"
                          >
                            ✦
                          </span>
                        )}
                        <span className="article-related__index">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <div>
                          <small>{item.difficulty_label}</small>
                          <h3>{item.title}</h3>
                          <p>{item.excerpt}</p>
                        </div>
                        <ArrowUpRight aria-hidden="true" />
                      </a>
                    );
                  })}
                </div>
              ) : (
                <p className="article-related__empty">
                  Следующие материалы появятся после публикации.
                </p>
              )}
            </section>

            <section
              className="article-comments"
              aria-labelledby="article-comments-title"
            >
              <header>
                <span>
                  <MessageCircle aria-hidden="true" />
                  Открытое обсуждение
                </span>
                <h2 id="article-comments-title">Комментарии</h2>
                <p>
                  Авторизация не нужна. Имя и текст появятся сразу после
                  отправки.
                </p>
              </header>

              <form onSubmit={submitComment}>
                <label>
                  Ваше имя
                  <input
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    minLength={2}
                    maxLength={80}
                    autoComplete="name"
                    required
                  />
                </label>
                <label>
                  Комментарий
                  <textarea
                    value={commentBody}
                    onChange={(event) => setCommentBody(event.target.value)}
                    minLength={8}
                    maxLength={3000}
                    rows={5}
                    required
                  />
                </label>
                <label className="comment-honeypot" aria-hidden="true">
                  Сайт
                  <input
                    value={website}
                    onChange={(event) => setWebsite(event.target.value)}
                    tabIndex={-1}
                    autoComplete="off"
                  />
                </label>
                <div>
                  <span>{commentBody.length}/3000</span>
                  <button type="submit" disabled={commentPending}>
                    {commentPending ? "Публикуем…" : "Опубликовать"}
                  </button>
                </div>
                {commentError && <p role="alert">{commentError}</p>}
              </form>

              {comments.length > 0 ? (
                <ol className="article-comments__list">
                  {comments.map((comment) => (
                    <li key={comment.id}>
                      <div>
                        <span>{comment.display_name.slice(0, 1)}</span>
                        <div>
                          <strong>{comment.display_name}</strong>
                          <time dateTime={comment.created_at}>
                            {formatDate(comment.created_at)}
                          </time>
                        </div>
                      </div>
                      <p>{comment.body}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="article-comments__empty">
                  Здесь пока тихо. Начните обсуждение первым.
                </p>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}

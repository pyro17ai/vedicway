import { type MouseEvent, useEffect, useState } from "react";
import { ArrowRight, BookOpenText, Compass, Sparkles } from "lucide-react";

import { publicArticles, type ContentArticle } from "../lib/admin-api";
import { ARTICLE_CATEGORIES } from "../lib/article-store";
import { applySeo } from "../lib/seo";
import { ArticleMedia } from "./ArticleMedia";
import { SiteHeader } from "./SiteHeader";

type GuidePageProps = {
  onNavigate: (path: string) => void;
};

function formatDate(value: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(new Date(value));
}

function followInternalLink(
  event: MouseEvent<HTMLAnchorElement>,
  path: string,
  onNavigate: (path: string) => void,
) {
  if (
    event.defaultPrevented
    || event.button !== 0
    || event.metaKey
    || event.ctrlKey
    || event.shiftKey
    || event.altKey
  ) return;
  event.preventDefault();
  onNavigate(path);
}

export function GuidePage({ onNavigate }: GuidePageProps) {
  const [articles, setArticles] = useState<ContentArticle[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    publicArticles().then(({ items }) => setArticles(items)).catch(() => setArticles([])).finally(() => setLoading(false));
    return applySeo({
      title: "Гид по ведической астрологии | VedicWay",
      description: "Понятный гид VedicWay по натальным картам, планетам, домам и практике чтения астрологических символов.",
      path: "/guide",
      structuredData: [{
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        name: "Гид по ведической астрологии",
        description: "Материалы VedicWay о чтении натальной карты и ведической астрологии.",
      }],
    });
  }, []);

  return (
    <div className="guide-site">
      <SiteHeader active="guide" onNavigate={onNavigate} />
      <main className="guide-page">
        <section className="guide-hero" aria-labelledby="guide-title">
          <div className="guide-hero__copy">
            <span className="guide-kicker"><Compass aria-hidden="true" /> Библиотека VedicWay</span>
            <h1 id="guide-title">Гид по астрологии</h1>
            <p>Спокойные и точные объяснения, которые помогают читать натальную карту по смыслу, а не заучивать отдельные символы.</p>
          </div>
          <div className="guide-hero__orb" aria-hidden="true"><Sparkles /></div>
        </section>

        <section className="guide-categories" aria-label="Разделы гида">
          {ARTICLE_CATEGORIES.map((category, index) => (
            <div key={category}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{category}</p>
            </div>
          ))}
        </section>

        <section className="guide-library" aria-labelledby="guide-library-title">
          <header>
            <div>
              <span className="guide-kicker"><BookOpenText aria-hidden="true" /> Материалы</span>
              <h2 id="guide-library-title">Читайте с самого начала или выбирайте нужную тему</h2>
            </div>
          </header>

          {loading ? <div className="guide-loading" role="status">Загружаем библиотеку…</div> : articles.length === 0 ? (
            <div className="guide-empty" role="status">
              <span aria-hidden="true">✦</span>
              <h3>Первые материалы готовятся</h3>
              <p>Здесь появятся последовательные разборы основ астрологии и практические руководства по чтению карты.</p>
            </div>
          ) : (
            <div className="guide-article-grid">
              {articles.map((article) => (
                <article className="guide-article-card" key={article.id}>
                  <a className="guide-article-card__cover" href={`/guide/${article.slug}`} onClick={(event) => followInternalLink(event, `/guide/${article.slug}`, onNavigate)} aria-label={`Открыть: ${article.title}`}>
                    {article.coverImage ? <ArticleMedia asset={article.coverImage} sizes="(max-width: 560px) calc(100vw - 30px), (max-width: 820px) 50vw, 380px" /> : article.cover_image_url ? <img src={article.cover_image_url} alt={article.cover_image_alt} loading="lazy" /> : <span aria-hidden="true">✦</span>}
                  </a>
                  <div className="guide-article-card__content">
                    <span>{article.category}</span>
                    <h3>{article.title}</h3>
                    <p>{article.excerpt}</p>
                    <footer>
                      <time dateTime={article.published_at ?? article.updated_at}>{formatDate(article.published_at ?? article.updated_at)}</time>
                      <a className="guide-article-card__read" href={`/guide/${article.slug}`} onClick={(event) => followInternalLink(event, `/guide/${article.slug}`, onNavigate)} aria-label={`Читать: ${article.title}`}>
                        Читать <ArrowRight aria-hidden="true" />
                      </a>
                    </footer>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

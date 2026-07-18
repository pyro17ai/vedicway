import { useEffect, useState } from "react";
import { ArrowRight, BookOpenText, Compass, PenLine, Sparkles } from "lucide-react";

import { ARTICLE_CATEGORIES, publishedArticles, type GuideArticle } from "../lib/article-store";
import { SiteHeader } from "./SiteHeader";

type GuidePageProps = {
  onNavigate: (path: string) => void;
};

function formatDate(value: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(new Date(value));
}

export function GuidePage({ onNavigate }: GuidePageProps) {
  const [articles, setArticles] = useState<GuideArticle[]>([]);

  useEffect(() => {
    setArticles(publishedArticles());
    document.title = "Гид по астрологии — VedicWay";
    const description = "Понятный гид VedicWay по натальным картам, планетам, домам и практике чтения астрологических символов.";
    let meta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.name = "description";
      document.head.append(meta);
    }
    meta.content = description;

    let canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.append(canonical);
    }
    canonical.href = `${window.location.origin}/guide`;
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
            {import.meta.env.DEV && (
              <button className="guide-editor-link" type="button" onClick={() => onNavigate("/guide/editor")}>
                <PenLine aria-hidden="true" /> Редактор статей
              </button>
            )}
          </header>

          {articles.length === 0 ? (
            <div className="guide-empty" role="status">
              <span aria-hidden="true">✦</span>
              <h3>Первые материалы готовятся</h3>
              <p>Здесь появятся последовательные разборы основ астрологии и практические руководства по чтению карты.</p>
              {import.meta.env.DEV && (
                <button type="button" onClick={() => onNavigate("/guide/editor")}>Создать первую статью <ArrowRight aria-hidden="true" /></button>
              )}
            </div>
          ) : (
            <div className="guide-article-grid">
              {articles.map((article) => (
                <article className="guide-article-card" key={article.id}>
                  <span>{article.category}</span>
                  <h3>{article.title}</h3>
                  <p>{article.excerpt}</p>
                  <footer>
                    <time dateTime={article.publishedAt ?? article.updatedAt}>{formatDate(article.publishedAt ?? article.updatedAt)}</time>
                    <button type="button" onClick={() => onNavigate(`/guide/${article.slug}`)} aria-label={`Читать: ${article.title}`}>
                      Читать <ArrowRight aria-hidden="true" />
                    </button>
                  </footer>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

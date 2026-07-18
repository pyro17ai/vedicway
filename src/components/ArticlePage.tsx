import { useEffect } from "react";
import { ArrowLeft, Clock3 } from "lucide-react";

import { articleBySlug } from "../lib/article-store";
import { SiteHeader } from "./SiteHeader";

type ArticlePageProps = {
  slug: string;
  onNavigate: (path: string) => void;
};

function readingMinutes(content: string) {
  return Math.max(1, Math.ceil(content.trim().split(/\s+/).filter(Boolean).length / 180));
}

function ArticleBody({ content }: { content: string }) {
  return content.split(/\n{2,}/).filter(Boolean).map((block, index) => {
    const value = block.trim();
    if (value.startsWith("## ")) return <h2 key={`${index}-${value}`}>{value.slice(3)}</h2>;
    if (value.startsWith("### ")) return <h3 key={`${index}-${value}`}>{value.slice(4)}</h3>;
    if (value.startsWith("- ")) {
      return <ul key={`${index}-${value}`}>{value.split("\n").map((line) => <li key={line}>{line.replace(/^-\s*/, "")}</li>)}</ul>;
    }
    return <p key={`${index}-${value}`}>{value}</p>;
  });
}

export function ArticlePage({ slug, onNavigate }: ArticlePageProps) {
  const article = articleBySlug(slug);

  useEffect(() => {
    document.title = article ? `${article.seoTitle || article.title} — VedicWay` : "Материал не найден — VedicWay";
    if (!article) return;
    let meta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.name = "description";
      document.head.append(meta);
    }
    meta.content = article.metaDescription || article.excerpt;

    let canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.append(canonical);
    }
    canonical.href = article.canonicalUrl || `${window.location.origin}/guide/${article.slug}`;

    const structuredData = document.createElement("script");
    structuredData.id = "vedicway-article-jsonld";
    structuredData.type = "application/ld+json";
    structuredData.text = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Article",
      headline: article.title,
      description: article.metaDescription || article.excerpt,
      datePublished: article.publishedAt,
      dateModified: article.updatedAt,
      author: { "@type": "Organization", name: article.author },
      mainEntityOfPage: canonical.href,
    });
    document.getElementById(structuredData.id)?.remove();
    document.head.append(structuredData);

    return () => structuredData.remove();
  }, [article]);

  return (
    <div className="guide-site">
      <SiteHeader active="guide" onNavigate={onNavigate} />
      <main className="article-page">
        {!article ? (
          <section className="article-not-found">
            <span>404</span>
            <h1>Материал не найден</h1>
            <p>Статья могла остаться в черновиках или получить другой адрес.</p>
            <button type="button" onClick={() => onNavigate("/guide")}><ArrowLeft aria-hidden="true" /> Вернуться в гид</button>
          </section>
        ) : (
          <article className="article-reading">
            <button className="article-back" type="button" onClick={() => onNavigate("/guide")}><ArrowLeft aria-hidden="true" /> Все материалы</button>
            <header>
              <span>{article.category}</span>
              <h1>{article.title}</h1>
              <p>{article.excerpt}</p>
              <div><span>{article.author}</span><time dateTime={article.publishedAt ?? article.updatedAt}>{new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(new Date(article.publishedAt ?? article.updatedAt))}</time><span><Clock3 aria-hidden="true" /> {readingMinutes(article.content)} мин</span></div>
            </header>
            <div className="article-reading__body"><ArticleBody content={article.content} /></div>
          </article>
        )}
      </main>
    </div>
  );
}

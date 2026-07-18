import { useEffect, useState } from "react";
import { ArrowLeft, Clock3 } from "lucide-react";

import { publicArticle, type ContentArticle, type ContentMediaAsset } from "../lib/admin-api";
import { SiteHeader } from "./SiteHeader";

type ArticlePageProps = {
  slug: string;
  onNavigate: (path: string) => void;
};

function readingMinutes(content: string) {
  return Math.max(1, Math.ceil(content.trim().split(/\s+/).filter(Boolean).length / 180));
}

function ArticleBody({ content, media }: { content: string; media: ContentMediaAsset[] }) {
  return content.split(/\n{2,}/).filter(Boolean).map((block, index) => {
    const value = block.trim();
    const mediaId = /^\{\{media:([A-Za-z0-9_-]+)\}\}$/.exec(value)?.[1];
    if (mediaId) {
      const asset = media.find((item) => item.id === mediaId);
      return asset ? <figure key={`${index}-${asset.id}`}><img src={asset.url} srcSet={asset.sources.map((source) => `${source.url} ${source.width}w`).join(", ")} sizes="(max-width: 820px) calc(100vw - 30px), 780px" alt={asset.alt} loading="lazy" />{asset.caption && <figcaption>{asset.caption}</figcaption>}</figure> : null;
    }
    if (value.startsWith("## ")) return <h2 key={`${index}-${value}`}>{value.slice(3)}</h2>;
    if (value.startsWith("### ")) return <h3 key={`${index}-${value}`}>{value.slice(4)}</h3>;
    if (value.startsWith("- ")) {
      return <ul key={`${index}-${value}`}>{value.split("\n").map((line) => <li key={line}>{line.replace(/^-\s*/, "")}</li>)}</ul>;
    }
    const image = value.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (image) {
      const src = image[2].startsWith("/media/articles/") || image[2].startsWith("https://") ? image[2] : "";
      return src ? <figure key={`${index}-${src}`}><img src={src} alt={image[1]} loading="lazy" /><figcaption>{image[1]}</figcaption></figure> : null;
    }
    return <p key={`${index}-${value}`}>{value}</p>;
  });
}

export function ArticlePage({ slug, onNavigate }: ArticlePageProps) {
  const [article, setArticle] = useState<ContentArticle | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    publicArticle(slug).then((value) => active && setArticle(value)).catch(() => active && setArticle(null)).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [slug]);

  useEffect(() => {
    document.title = article ? `${article.seo_title || article.title} — VedicWay` : "Материал не найден — VedicWay";
    if (!article) return;
    let meta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.name = "description";
      document.head.append(meta);
    }
    meta.content = article.meta_description || article.excerpt;

    let canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.append(canonical);
    }
    canonical.href = article.canonical_url || `${window.location.origin}/guide/${article.slug}`;

    const structuredData = document.createElement("script");
    structuredData.id = "vedicway-article-jsonld";
    structuredData.type = "application/ld+json";
    structuredData.text = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Article",
      headline: article.title,
      description: article.meta_description || article.excerpt,
      image: article.cover_image_url ? new URL(article.cover_image_url, window.location.origin).href : undefined,
      datePublished: article.published_at,
      dateModified: article.updated_at,
      author: { "@type": "Organization", name: article.author_name },
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
        {loading ? <section className="article-not-found"><p>Загружаем материал…</p></section> : !article ? (
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
              {article.cover_image_url && <figure className="article-cover"><img src={article.cover_image_url} alt={article.cover_image_alt} /></figure>}
              <span>{article.category}</span>
              <h1>{article.title}</h1>
              <p>{article.excerpt}</p>
              <div><span>{article.author_name}</span><time dateTime={article.published_at ?? article.updated_at}>{new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(new Date(article.published_at ?? article.updated_at))}</time><span><Clock3 aria-hidden="true" /> {readingMinutes(article.content)} мин</span></div>
            </header>
            <div className="article-reading__body"><ArticleBody content={article.content} media={article.bodyMedia} /></div>
          </article>
        )}
      </main>
    </div>
  );
}

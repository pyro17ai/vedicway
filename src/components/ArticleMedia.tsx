import { useEffect, useMemo, useState } from "react";

import { resolveArticleMediaUrl, safeArticleMediaUrl } from "../lib/article-media";
import type { ArticleMediaAsset } from "../lib/article-store";

type ArticleMediaProps = {
  asset: ArticleMediaAsset;
  className?: string;
  sizes?: string;
  loading?: "eager" | "lazy";
  decorative?: boolean;
};

export function ArticleMedia({ asset, className = "", sizes = "100vw", loading = "lazy", decorative = false }: ArticleMediaProps) {
  const [source, setSource] = useState(asset.url);

  useEffect(() => {
    let alive = true;
    let revoke = false;
    let resolvedUrl = "";
    setSource(asset.url);
    void resolveArticleMediaUrl(asset).then((resolved) => {
      if (!alive) {
        if (resolved.revoke) URL.revokeObjectURL(resolved.url);
        return;
      }
      resolvedUrl = resolved.url;
      revoke = resolved.revoke;
      setSource(resolved.url);
    }).catch(() => setSource(""));
    return () => {
      alive = false;
      if (revoke && resolvedUrl) URL.revokeObjectURL(resolvedUrl);
    };
  }, [asset.provider, asset.storageKey, asset.url]);

  const srcSet = useMemo(() => asset.sources
    .map((candidate) => ({ ...candidate, url: safeArticleMediaUrl(candidate.url) }))
    .filter((candidate) => candidate.url)
    .map((candidate) => `${candidate.url} ${candidate.width}w`)
    .join(", "), [asset.sources]);

  return (
    <span className={`article-media${source ? " is-ready" : " is-pending"}${className ? ` ${className}` : ""}`}>
      {source && (
        <img
          src={source}
          srcSet={srcSet || undefined}
          sizes={srcSet ? sizes : undefined}
          width={asset.width || undefined}
          height={asset.height || undefined}
          alt={decorative ? "" : asset.alt}
          title={asset.title || undefined}
          loading={loading}
          decoding="async"
        />
      )}
      {!source && <span className="article-media__placeholder" aria-label="Изображение загружается" />}
    </span>
  );
}

export function ArticleMediaFigure({ asset }: { asset: ArticleMediaAsset }) {
  return (
    <figure className="article-body-media">
      <ArticleMedia asset={asset} sizes="(max-width: 820px) calc(100vw - 30px), 780px" />
      {asset.caption && <figcaption>{asset.caption}</figcaption>}
    </figure>
  );
}

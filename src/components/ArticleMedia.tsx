import { useMemo } from "react";

import type { ContentMediaAsset } from "../lib/content-api";

type ArticleMediaProps = {
  asset: ContentMediaAsset;
  className?: string;
  sizes?: string;
  loading?: "eager" | "lazy";
  decorative?: boolean;
};

function safeMediaUrl(value: string) {
  const trimmed = value.trim();
  if (trimmed.startsWith("/media/articles/")) return trimmed;
  if (/^https:\/\/[^/]+\/media\/articles\//i.test(trimmed)) return trimmed;
  return "";
}

export function ArticleMedia({
  asset,
  className = "",
  sizes = "100vw",
  loading = "lazy",
  decorative = false,
}: ArticleMediaProps) {
  const source = safeMediaUrl(asset.url);
  const srcSet = useMemo(
    () =>
      asset.sources
        .map((candidate) => ({
          ...candidate,
          url: safeMediaUrl(candidate.url),
        }))
        .filter((candidate) => candidate.url)
        .map((candidate) => `${candidate.url} ${candidate.width}w`)
        .join(", "),
    [asset.sources],
  );

  return (
    <span
      className={`article-media${source ? " is-ready" : " is-pending"}${className ? ` ${className}` : ""}`}
    >
      {source ? (
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
          fetchPriority={loading === "eager" ? "high" : "auto"}
        />
      ) : (
        <span
          className="article-media__placeholder"
          aria-label="Изображение недоступно"
        />
      )}
    </span>
  );
}

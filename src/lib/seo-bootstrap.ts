import type {
  ContentArticle,
  ContentArticleSummary,
  ContentComment,
  ContentSection,
} from "./content-api";

export type SeoBootstrap =
  | {
      kind: "article";
      section: ContentSection;
      slug: string;
      article: ContentArticle;
      comments: ContentComment[];
    }
  | {
      kind: "hub";
      section: ContentSection;
      articles: ContentArticleSummary[];
    };

export function readSeoBootstrap(): SeoBootstrap | null {
  const node = document.getElementById("vedicway-seo-bootstrap");
  if (!node?.textContent) return null;
  try {
    const value = JSON.parse(node.textContent) as SeoBootstrap;
    if (value.kind === "article" && value.article && Array.isArray(value.comments)) {
      return value;
    }
    if (value.kind === "hub" && Array.isArray(value.articles)) {
      return value;
    }
  } catch {
    return null;
  }
  return null;
}

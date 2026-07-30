import type { NavigateHandler } from "./ContentHubPage";
import { ContentHubPage } from "./ContentHubPage";
import type { ContentArticleSummary } from "../lib/content-api";

export function BlogPage({
  onNavigate,
  initialArticles,
}: {
  onNavigate: NavigateHandler;
  initialArticles?: ContentArticleSummary[];
}) {
  return <ContentHubPage section="blog" onNavigate={onNavigate} initialArticles={initialArticles} />;
}

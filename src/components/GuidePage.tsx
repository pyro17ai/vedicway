import type { NavigateHandler } from "./ContentHubPage";
import { ContentHubPage } from "./ContentHubPage";
import type { ContentArticleSummary } from "../lib/content-api";

export function GuidePage({
  onNavigate,
  initialArticles,
}: {
  onNavigate: NavigateHandler;
  initialArticles?: ContentArticleSummary[];
}) {
  return <ContentHubPage section="guide" onNavigate={onNavigate} initialArticles={initialArticles} />;
}

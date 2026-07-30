import type { NavigateHandler } from "./ContentHubPage";
import { ContentHubPage } from "./ContentHubPage";

export function BlogPage({ onNavigate }: { onNavigate: NavigateHandler }) {
  return <ContentHubPage section="blog" onNavigate={onNavigate} />;
}

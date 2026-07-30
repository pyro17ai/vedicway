import type { NavigateHandler } from "./ContentHubPage";
import { ContentHubPage } from "./ContentHubPage";

export function GuidePage({ onNavigate }: { onNavigate: NavigateHandler }) {
  return <ContentHubPage section="guide" onNavigate={onNavigate} />;
}

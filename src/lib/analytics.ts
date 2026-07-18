type AnalyticsPayload = Record<string, string | number | boolean | null | undefined>;

export function trackWorkspaceEvent(name: string, payload: AnalyticsPayload = {}) {
  window.dispatchEvent(new CustomEvent("vedicway:analytics", { detail: { name, payload } }));
}

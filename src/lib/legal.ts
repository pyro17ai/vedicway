export const LEGAL_DOCUMENT_VERSIONS = {
  terms: "2026-07-30",
  privacy: "2026-07-30",
  personalDataConsent: "2026-07-30",
  cookies: "2026-07-19",
} as const;

export type CookiePreferences = {
  version: string;
  necessary: true;
  analytics: boolean;
  decidedAt: string;
};

const COOKIE_PREFERENCES_KEY = "vedicway:cookie-preferences:v1";

export function readCookiePreferences(): CookiePreferences | null {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(COOKIE_PREFERENCES_KEY) ?? "null") as Partial<CookiePreferences> | null;
    if (!parsed || parsed.version !== LEGAL_DOCUMENT_VERSIONS.cookies || typeof parsed.analytics !== "boolean") return null;
    return { version: parsed.version, necessary: true, analytics: parsed.analytics, decidedAt: parsed.decidedAt ?? "" };
  } catch {
    return null;
  }
}

export function writeCookiePreferences(analytics: boolean): CookiePreferences {
  const preferences: CookiePreferences = {
    version: LEGAL_DOCUMENT_VERSIONS.cookies,
    necessary: true,
    analytics,
    decidedAt: new Date().toISOString(),
  };
  window.localStorage.setItem(COOKIE_PREFERENCES_KEY, JSON.stringify(preferences));
  window.dispatchEvent(new CustomEvent("vedicway:cookie-preferences", { detail: preferences }));
  return preferences;
}

declare global {
  interface Window {
    ym?: (...args: unknown[]) => void;
    [key: `disableYaCounter${string}`]: boolean | undefined;
  }
}

let metrikaLoaded = false;
let analyticsEnabled = false;
let analyticsBridgeInstalled = false;

const GOAL_NAMES = new Set([
  "chart_create_accepted",
  "chart_create_failed",
  "payment_returned",
  "payment_server_confirmed",
  "payment_cancelled",
  "payment_failed",
  "payment_timeout",
  "result_tab_opened",
  "domain_detail_requested",
  "checkout_started",
  "rectification_checkout_opened",
  "question_saved",
  "question_status_changed",
  "pdf_requested",
  "pdf_downloaded",
]);

const SAFE_GOAL_FIELDS = new Set([
  "time_accuracy",
  "code",
  "tab",
  "domain",
  "access",
  "price_minor",
  "saved",
  "reflection_status",
  "status",
  "varga",
  "mode",
]);

function sanitizedGoalName(value: unknown) {
  if (typeof value !== "string") return null;
  const name = value.trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_").slice(0, 64);
  return GOAL_NAMES.has(name) ? name : null;
}

function safeGoalPayload(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const safe: Record<string, string | number | boolean> = {};
  for (const [key, item] of Object.entries(value)) {
    if (!SAFE_GOAL_FIELDS.has(key)) continue;
    if (typeof item === "boolean" || typeof item === "number") safe[key] = item;
    else if (typeof item === "string" && /^[\p{L}\p{N}_.:-]{1,64}$/u.test(item)) safe[key] = item;
  }
  return safe;
}

function safePagePath(value: unknown) {
  if (typeof value !== "string") return "/404";
  let pathname: string;
  try {
    pathname = new URL(value, window.location.origin).pathname;
  } catch {
    return "/404";
  }
  if (/^\/chart\/[^/]+$/.test(pathname)) return "/chart/:id";
  if (/^\/rectification\/[^/]+$/.test(pathname)) return "/rectification/:id";
  if (/^\/(?:guide|blog)\/[a-z0-9-]+$/.test(pathname)) return pathname;
  if ([
    "/",
    "/guide",
    "/blog",
    "/legal/offer",
    "/legal/privacy",
    "/legal/user-agreement",
    "/legal/privacy-policy",
    "/legal/personal-data-consent",
    "/legal/cookies",
  ].includes(pathname)) return pathname;
  return "/404";
}

function installAnalyticsBridge(counterId: number) {
  if (analyticsBridgeInstalled) return;
  analyticsBridgeInstalled = true;
  window.addEventListener("vedicway:analytics", (event) => {
    if (!analyticsEnabled) return;
    const detail = (event as CustomEvent).detail as { name?: unknown; payload?: unknown } | undefined;
    const name = sanitizedGoalName(detail?.name);
    if (!name) return;
    window.ym?.(counterId, "reachGoal", name, safeGoalPayload(detail?.payload));
  });
  window.addEventListener("vedicway:analytics-pageview", (event) => {
    if (!analyticsEnabled) return;
    const detail = (event as CustomEvent).detail as { pathname?: unknown } | undefined;
    window.ym?.(counterId, "hit", safePagePath(detail?.pathname));
  });
}

export function applyAnalyticsPreference(enabled: boolean) {
  const counterId = String(import.meta.env.VITE_YANDEX_METRIKA_ID ?? "").trim();
  if (!counterId) return;
  const numericCounterId = Number(counterId);
  if (!Number.isSafeInteger(numericCounterId) || numericCounterId <= 0) return;
  analyticsEnabled = enabled;
  window[`disableYaCounter${counterId}`] = !enabled;
  if (!enabled) return;
  installAnalyticsBridge(numericCounterId);
  if (metrikaLoaded) {
    window.ym?.(numericCounterId, "hit", safePagePath(window.location.pathname));
    return;
  }
  metrikaLoaded = true;
  if (!window.ym) {
    const queued = ((...args: unknown[]) => { queued.a.push(args); }) as unknown as ((...args: unknown[]) => void) & { a: unknown[] };
    queued.a = [];
    window.ym = queued;
  }
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://mc.yandex.ru/metrika/tag.js";
  script.dataset.consentControlled = "true";
  document.head.append(script);
  window.ym?.(numericCounterId, "init", {
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
    webvisor: false,
    defer: true,
  });
  window.ym?.(numericCounterId, "hit", safePagePath(window.location.pathname));
}

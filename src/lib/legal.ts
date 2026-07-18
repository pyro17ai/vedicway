export const LEGAL_DOCUMENT_VERSIONS = {
  terms: "2026-07-19",
  privacy: "2026-07-19",
  personalDataConsent: "2026-07-19",
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

export function applyAnalyticsPreference(enabled: boolean) {
  const counterId = String(import.meta.env.VITE_YANDEX_METRIKA_ID ?? "").trim();
  if (!counterId) return;
  window[`disableYaCounter${counterId}`] = !enabled;
  if (!enabled || metrikaLoaded) return;
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
  script.onload = () => window.ym?.(Number(counterId), "init", {
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
    webvisor: false,
  });
  document.head.append(script);
}

export type StructuredData = Record<string, unknown>;

export type SeoPage = {
  title: string;
  description: string;
  path: string;
  canonicalUrl?: string;
  image?: string;
  type?: "website" | "article";
  noindex?: boolean;
  structuredData?: StructuredData[];
};

const PRODUCTION_ORIGIN = "https://vedicway.ru";
const DEFAULT_IMAGE = "/assets/hero-space.png";

export function publicOrigin() {
  const configured = import.meta.env.VITE_PUBLIC_ORIGIN?.trim().replace(/\/$/, "");
  if (configured) return configured;
  if (import.meta.env.DEV && typeof window !== "undefined") return window.location.origin;
  return PRODUCTION_ORIGIN;
}

export function applySeo(page: SeoPage) {
  const origin = publicOrigin();
  const canonical = page.canonicalUrl || `${origin}${normalizedPath(page.path)}`;
  const image = absoluteUrl(page.image || DEFAULT_IMAGE, origin);
  const robots = page.noindex
    ? "noindex, nofollow, noarchive"
    : "index, follow, max-image-preview:large";

  document.title = page.title;
  setMeta("name", "description", page.description);
  setMeta("name", "robots", robots);
  setMeta("property", "og:locale", "ru_RU");
  setMeta("property", "og:type", page.type || "website");
  setMeta("property", "og:site_name", "VedicWay");
  setMeta("property", "og:title", page.title);
  setMeta("property", "og:description", page.description);
  setMeta("property", "og:url", canonical);
  setMeta("property", "og:image", image);
  setMeta("name", "twitter:card", "summary_large_image");
  setMeta("name", "twitter:title", page.title);
  setMeta("name", "twitter:description", page.description);
  setMeta("name", "twitter:image", image);
  setCanonical(canonical);

  document.querySelectorAll("script[data-vedicway-seo-schema]").forEach((node) => node.remove());
  const scripts = (page.structuredData || []).map((value) => {
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.dataset.vedicwaySeoSchema = "true";
    script.text = JSON.stringify(value).replace(/</g, "\\u003c");
    document.head.append(script);
    return script;
  });

  return () => scripts.forEach((script) => script.remove());
}

function normalizedPath(path: string) {
  if (!path || path === "/") return "/";
  return path.startsWith("/") ? path : `/${path}`;
}

function absoluteUrl(value: string, origin: string) {
  if (/^https?:\/\//i.test(value)) return value;
  return `${origin}${normalizedPath(value)}`;
}

function setMeta(attribute: "name" | "property", key: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attribute, key);
    document.head.append(element);
  }
  element.content = content;
}

function setCanonical(href: string) {
  let element = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!element) {
    element = document.createElement("link");
    element.rel = "canonical";
    document.head.append(element);
  }
  element.href = href;
}

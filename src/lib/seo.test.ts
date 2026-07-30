import { afterEach, describe, expect, it } from "vitest";

import { applySeo } from "./seo";

describe("applySeo", () => {
  afterEach(() => {
    document.head.innerHTML = "";
  });

  it("sets a single canonical and replaces route metadata", () => {
    applySeo({
      title: "Страница — VedicWay",
      description: "Описание страницы",
      path: "/guide",
      image: "/assets/results-space-v2.png",
    });
    applySeo({
      title: "Другая страница — VedicWay",
      description: "Новое описание",
      path: "/guide/article",
    });

    expect(document.title).toBe("Другая страница — VedicWay");
    expect(document.querySelectorAll('link[rel="canonical"]')).toHaveLength(1);
    expect(document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href).toContain("/guide/article");
    expect(document.querySelector<HTMLMetaElement>('meta[name="description"]')?.content).toBe("Новое описание");
  });

  it("marks private routes noindex and emits only the current schemas", () => {
    const cleanup = applySeo({
      title: "Восстановление доступа — VedicWay",
      description: "Служебная страница",
      path: "/access/recovery",
      noindex: true,
      structuredData: [{ "@context": "https://schema.org", "@type": "WebPage" }],
    });

    expect(document.querySelector<HTMLMetaElement>('meta[name="robots"]')?.content).toContain("noindex");
    expect(document.querySelectorAll("script[data-vedicway-seo-schema]")).toHaveLength(1);
    cleanup();
    expect(document.querySelectorAll("script[data-vedicway-seo-schema]")).toHaveLength(0);
  });
});

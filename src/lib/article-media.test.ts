import { describe, expect, it, vi } from "vitest";

import { readAdminCsrfToken, safeArticleMediaUrl, uploadArticleMedia, validateArticleMediaFile } from "./article-media";

describe("article-media", () => {
  it("читает production и dev CSRF cookie без доступа к HttpOnly session", () => {
    expect(readAdminCsrfToken("other=1; __Host-vedicway-csrf=prod-token")).toBe("prod-token");
    expect(readAdminCsrfToken("vw_admin_csrf=dev%20token")).toBe("dev token");
  });

  it("не пропускает data, javascript и protocol-relative URL в публичный img", () => {
    expect(safeArticleMediaUrl("data:image/svg+xml,<svg/>")).toBe("");
    expect(safeArticleMediaUrl("javascript:alert(1)")).toBe("");
    expect(safeArticleMediaUrl("//evil.example/image.webp")).toBe("");
    expect(safeArticleMediaUrl("/media/image.webp")).toBe("/media/image.webp");
  });

  it("отклоняет исполняемые и слишком большие файлы до отправки", () => {
    expect(() => validateArticleMediaFile(new File(["x"], "payload.svg", { type: "image/svg+xml" })))
      .toThrow("JPEG, PNG, WebP и AVIF");
    const oversized = new File([new Uint8Array(12 * 1024 * 1024 + 1)], "huge.webp", { type: "image/webp" });
    expect(() => validateArticleMediaFile(oversized)).toThrow("не больше 12 МБ");
  });

  it("отправляет multipart в защищённый media API и нормализует responsive sources", async () => {
    document.cookie = "vw_admin_csrf=csrf-test; path=/";
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe("POST");
      expect(init?.credentials).toBe("same-origin");
      expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("csrf-test");
      expect(init?.body).toBeInstanceOf(FormData);
      return {
        ok: true,
        json: async () => ({ asset: {
          id: "asset-1",
          storageKey: "articles/asset-1/original.webp",
          url: "/media/articles/asset-1/1600.webp",
          sources: [
            { url: "/media/articles/asset-1/1280.webp", width: 1280, mimeType: "image/webp" },
            { url: "/media/articles/asset-1/640.webp", width: 640, mimeType: "image/webp" },
          ],
          width: 1600,
          height: 900,
          mimeType: "image/webp",
          sizeBytes: 1200,
          alt: "Натальная карта",
          createdAt: "2026-07-19T00:00:00Z",
        } }),
      } as Response;
    });

    const asset = await uploadArticleMedia({
      file: new File(["image"], "cover.webp", { type: "image/webp" }),
      purpose: "cover",
      alt: "Натальная карта",
    }, fetcher as typeof fetch);

    expect(asset.provider).toBe("remote");
    expect(asset.sources.map((source) => source.width)).toEqual([640, 1280]);
    expect(fetcher).toHaveBeenCalledWith("/api/v1/admin/media", expect.any(Object));
  });
});

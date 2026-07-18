import { afterEach, describe, expect, it, vi } from "vitest";

import { reportDownloadUrl, startPdf } from "./chart-api";

describe("startPdf", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("снимает выбранные настройки карты в тело одного PDF-запроса", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => ({
      ok: true,
      json: async () => ({
        job_id: "job-1",
        render_request_id: "pdfreq-1",
        status: "generating",
        preferences: JSON.parse(String(init?.body)).preferences,
      }),
    } as Response));
    vi.stubGlobal("fetch", fetcher);

    const preferences = {
      schema_version: "pdf-render-preferences.v1" as const,
      varga: "D24",
      mode: "expert" as const,
      chart_style: "south_indian" as const,
    };
    const response = await startPdf("chart/unsafe", preferences);

    expect(response.render_request_id).toBe("pdfreq-1");
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("/api/v1/charts/chart%2Funsafe/reports/pdf");
    expect(JSON.parse(String(init?.body))).toEqual({ preferences });
    expect(reportDownloadUrl("chart/unsafe", response.render_request_id)).toBe(
      "/api/v1/charts/chart%2Funsafe/reports/pdf?render_request_id=pdfreq-1",
    );
  });
});

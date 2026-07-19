import { beforeEach, describe, expect, it, vi } from "vitest";

describe("Яндекс.Метрика с согласием", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("VITE_YANDEX_METRIKA_ID", "12345678");
    document.querySelectorAll('script[data-consent-controlled="true"]').forEach((node) => node.remove());
    delete window.ym;
  });

  it("не загружает счётчик до согласия, фильтрует события и останавливается после отзыва", async () => {
    const { applyAnalyticsPreference } = await import("./legal");

    window.dispatchEvent(new CustomEvent("vedicway:analytics", {
      detail: { name: "checkout_started", payload: { price_minor: 99000 } },
    }));
    expect(document.querySelector('script[src*="mc.yandex.ru/metrika/tag.js"]')).toBeNull();
    expect(window.ym).toBeUndefined();

    const ym = vi.fn();
    window.ym = ym;
    applyAnalyticsPreference(true);
    expect(document.querySelector('script[src*="mc.yandex.ru/metrika/tag.js"]')).not.toBeNull();

    window.dispatchEvent(new CustomEvent("vedicway:analytics", {
      detail: {
        name: "checkout started",
        payload: {
          price_minor: 99000,
          mode: "plain",
          email: "person@example.org",
          chart_id: "chart-secret",
          question_text: "Личный вопрос",
        },
      },
    }));
    expect(ym).toHaveBeenCalledWith(12345678, "reachGoal", "checkout_started", {
      price_minor: 99000,
      mode: "plain",
    });

    window.dispatchEvent(new CustomEvent("vedicway:analytics-pageview", {
      detail: { pathname: "/chart/chart-secret?email=person@example.org" },
    }));
    expect(ym).toHaveBeenCalledWith(12345678, "hit", "/chart/:id");

    const callsBeforeRevoke = ym.mock.calls.length;
    applyAnalyticsPreference(false);
    window.dispatchEvent(new CustomEvent("vedicway:analytics", {
      detail: { name: "payment_returned", payload: {} },
    }));
    expect(ym).toHaveBeenCalledTimes(callsBeforeRevoke);
    expect(window.disableYaCounter12345678).toBe(true);
  });
});

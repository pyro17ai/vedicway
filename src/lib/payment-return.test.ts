import { afterEach, describe, expect, it, vi } from "vitest";

import { createPurchase, type PurchaseResource } from "./chart-api";
import {
  clearPaymentReturnState,
  pollPurchase,
  readPaymentReturnState,
  savePaymentReturnState,
} from "./payment-return";


function purchase(status: PurchaseResource["status"]): PurchaseResource {
  return {
    purchase_id: "pur_123",
    chart_id: "chart_123",
    product_code: "full_report_v1",
    status,
    checkout_url: status === "pending" ? "https://yoomoney.ru/checkout/token" : null,
    price_minor: 99_000,
    currency: "RUB",
    retryable: status === "pending" || status === "unknown" || status === "created",
  };
}


afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});


describe("purchase API", () => {
  it("sends email and the accepted offer without accepting a browser amount", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(purchase("pending")), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await createPurchase("chart_123", {
      email: "buyer@example.com",
      offerVersion: "2026-07-18",
    });

    expect(result.status).toBe("pending");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      product_code: "full_report_v1",
      email: "buyer@example.com",
      offer_accepted: true,
      offer_version: "2026-07-18",
    });
    expect(String(init.body)).not.toContain("amount");
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toMatch(/^purchase-/);
  });

  it("keeps stable backend error details for recovery UI", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "OFFER_VERSION_MISMATCH",
              message: "Оферта обновилась",
              recoverable: true,
              trace_id: "trace-1",
              detail: { offer_version: "2026-07-18" },
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(
      createPurchase("chart_123", { email: "buyer@example.com", offerVersion: "old" }),
    ).rejects.toMatchObject({
      code: "OFFER_VERSION_MISMATCH",
      traceId: "trace-1",
      detail: { offer_version: "2026-07-18" },
    });
  });
});


describe("payment return state", () => {
  it("stores only internal purchase context and validates the return query", () => {
    savePaymentReturnState(window.sessionStorage, {
      purchaseId: "pur_123",
      chartId: "chart_123",
      domain: "relationships",
    });

    expect(JSON.parse(window.sessionStorage.getItem("vedicway:payment-return") ?? "{}")).toEqual({
      purchaseId: "pur_123",
      chartId: "chart_123",
      domain: "relationships",
    });
    expect(readPaymentReturnState(window.sessionStorage, "chart_123", "?payment_return=pur_123")).toEqual({
      purchaseId: "pur_123",
      chartId: "chart_123",
      domain: "relationships",
    });
    expect(readPaymentReturnState(window.sessionStorage, "chart_other", "?payment_return=pur_123")).toBeNull();
    expect(readPaymentReturnState(window.sessionStorage, "chart_123", "?payment_return=pur_other")).toBeNull();
  });

  it("rejects malformed state and clears completed recovery", () => {
    window.sessionStorage.setItem("vedicway:payment-return", "{broken");
    expect(readPaymentReturnState(window.sessionStorage, "chart_123", "?payment_return=pur_123")).toBeNull();
    savePaymentReturnState(window.sessionStorage, {
      purchaseId: "pur_123",
      chartId: "chart_123",
      domain: null,
    });
    clearPaymentReturnState(window.sessionStorage);
    expect(window.sessionStorage.getItem("vedicway:payment-return")).toBeNull();
  });
});


describe("purchase polling", () => {
  it("uses bounded increasing delays until server success", async () => {
    const responses = [purchase("pending"), purchase("unknown"), purchase("succeeded")];
    const fetchPurchase = vi.fn(async () => responses.shift()!);
    const delays: number[] = [];
    let now = 0;
    const result = await pollPurchase("pur_123", {
      fetchPurchase,
      now: () => now,
      timeoutMs: 60_000,
      sleep: async (delay) => {
        delays.push(delay);
        now += delay;
      },
    });

    expect(result.outcome).toBe("succeeded");
    expect(fetchPurchase).toHaveBeenCalledTimes(3);
    expect(delays).toEqual([750, 1_250]);
  });

  it("returns cancellation and timeout without treating either as success", async () => {
    const canceled = await pollPurchase("pur_123", {
      fetchPurchase: async () => purchase("cancelled"),
      sleep: async () => undefined,
    });
    let now = 0;
    const timedOut = await pollPurchase("pur_123", {
      fetchPurchase: async () => purchase("pending"),
      now: () => now,
      timeoutMs: 2_000,
      sleep: async (delay) => {
        now += delay;
      },
    });

    expect(canceled.outcome).toBe("cancelled");
    expect(timedOut.outcome).toBe("timeout");
    expect(timedOut.purchase.status).toBe("pending");
  });
});

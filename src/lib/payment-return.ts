import { getPurchase, type DomainSlug, type PurchaseResource } from "./chart-api";


const STORAGE_KEY = "vedicway:payment-return";
const DOMAIN_SLUGS = new Set<DomainSlug>([
  "character",
  "inner_support",
  "relationships",
  "family_home",
  "work",
  "money",
  "learning",
  "current_period",
]);
const INTERNAL_ID = /^[A-Za-z0-9_-]{4,200}$/;

export type PaymentReturnState = {
  purchaseId: string;
  chartId: string;
  domain: DomainSlug | null;
};

export function savePaymentReturnState(storage: Storage, state: PaymentReturnState) {
  storage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function clearPaymentReturnState(storage: Storage) {
  storage.removeItem(STORAGE_KEY);
}

export function readPaymentReturnState(
  storage: Storage,
  expectedChartId: string,
  search: string,
): PaymentReturnState | null {
  const returnedPurchaseId = new URLSearchParams(search).get("payment_return");
  if (!returnedPurchaseId || !INTERNAL_ID.test(returnedPurchaseId)) return null;
  try {
    const raw = JSON.parse(storage.getItem(STORAGE_KEY) ?? "null") as Partial<PaymentReturnState> | null;
    if (!raw || typeof raw.purchaseId !== "string" || typeof raw.chartId !== "string") return null;
    if (!INTERNAL_ID.test(raw.purchaseId) || !INTERNAL_ID.test(raw.chartId)) return null;
    if (raw.purchaseId !== returnedPurchaseId || raw.chartId !== expectedChartId) return null;
    const domain = raw.domain === null || raw.domain === undefined
      ? null
      : DOMAIN_SLUGS.has(raw.domain as DomainSlug)
        ? raw.domain as DomainSlug
        : null;
    if (raw.domain !== null && raw.domain !== undefined && domain === null) return null;
    return { purchaseId: raw.purchaseId, chartId: raw.chartId, domain };
  } catch {
    return null;
  }
}

type PollOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
  fetchPurchase?: (purchaseId: string, signal?: AbortSignal) => Promise<PurchaseResource>;
  sleep?: (delayMs: number, signal?: AbortSignal) => Promise<void>;
  now?: () => number;
  onUpdate?: (purchase: PurchaseResource) => void;
};

export type PurchasePollResult = {
  outcome: "succeeded" | "cancelled" | "failed" | "timeout" | "aborted";
  purchase: PurchaseResource;
};

function defaultSleep(delayMs: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = window.setTimeout(resolve, delayMs);
    signal?.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

export async function pollPurchase(purchaseId: string, options: PollOptions = {}): Promise<PurchasePollResult> {
  const fetchPurchase = options.fetchPurchase ?? getPurchase;
  const sleep = options.sleep ?? defaultSleep;
  const now = options.now ?? Date.now;
  const timeoutMs = options.timeoutMs ?? 60_000;
  const delays = [750, 1_250, 2_000, 3_000, 5_000];
  const startedAt = now();
  let attempt = 0;
  let latest: PurchaseResource | null = null;

  try {
    while (!options.signal?.aborted) {
      if (latest && now() - startedAt >= timeoutMs) {
        return { outcome: "timeout", purchase: latest };
      }
      latest = await fetchPurchase(purchaseId, options.signal);
      options.onUpdate?.(latest);
      if (latest.status === "succeeded") return { outcome: "succeeded", purchase: latest };
      if (latest.status === "cancelled" || latest.status === "refunded") {
        return { outcome: "cancelled", purchase: latest };
      }
      if (latest.status === "failed") return { outcome: "failed", purchase: latest };
      const elapsed = now() - startedAt;
      if (elapsed >= timeoutMs) return { outcome: "timeout", purchase: latest };
      const delay = Math.min(delays[Math.min(attempt, delays.length - 1)], timeoutMs - elapsed);
      attempt += 1;
      await sleep(delay, options.signal);
    }
  } catch (error) {
    if (options.signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) {
      if (latest) return { outcome: "aborted", purchase: latest };
    }
    throw error;
  }
  if (!latest) throw new DOMException("Aborted", "AbortError");
  return { outcome: "aborted", purchase: latest };
}

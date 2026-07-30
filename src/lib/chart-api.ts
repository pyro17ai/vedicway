import { LEGAL_DOCUMENT_VERSIONS } from "./legal";

export type SectionStatus = "queued" | "running" | "ready" | "partial" | "error" | "unavailable";
export type AccessLevel = "free_summary" | "paid_full";
export type Coverage = "multiple_factors" | "single_factor" | "insufficient";
export type DomainSlug =
  | "character"
  | "inner_support"
  | "relationships"
  | "family_home"
  | "work"
  | "money"
  | "learning"
  | "current_period";

export type PlaceOption = {
  place_id: string;
  display_name: string;
  country_code: string;
  latitude: number;
  longitude: number;
  tzid: string;
};

export type PlanetPosition = {
  planet_code: string;
  label: string;
  short_label: string;
  classical: boolean;
  sign_index: number;
  sign_label: string;
  house_number: number;
  longitude_in_sign: number;
  total_longitude: number;
  nakshatra: string;
  pada?: number | null;
  retrograde?: boolean | null;
  source_path: string;
};

export type ChartCell = {
  sign_index: number;
  sign_code: string;
  sign_label: string;
  house_number: number;
  is_lagna: boolean;
  planets: PlanetPosition[];
};

export type ChartSection = {
  section: string;
  status: SectionStatus;
  data?: Record<string, unknown> | null;
  error?: { code: string; message: string; recoverable: boolean } | null;
};

export type EvidenceFact = {
  id: string;
  kind: string;
  subject: string;
  chart: string;
  sign?: string | null;
  house?: number | null;
  value: Record<string, unknown>;
  human_label_ru: string;
  domains: DomainSlug[];
  source_paths: string[];
};

export type DomainCard = {
  slug: DomainSlug;
  section_label: string;
  title: string;
  summary: string;
  evidence_ids: string[];
  coverage: Coverage;
  limitations: string[];
  paragraphs: string[];
  manifestations: string[];
  reflection_prompts: string[];
};

export type ReflectionQuestion = {
  id: string;
  domain: DomainSlug;
  text: string;
  rationale: string;
  evidence_ids: string[];
};

export type InterpretationBundle = {
  schema_version: "interpretation.free.v1" | "interpretation.paid.v1";
  snapshot_id: string;
  locale: "ru-RU";
  overview: DomainCard;
  domains: DomainCard[];
  questions: ReflectionQuestion[];
  global_limitations: string[];
  synthesis: string[];
};

export type ChartResource = {
  chart_id: string;
  status: string;
  birth: {
    local_date: string;
    local_time: string;
    place: string;
    tzid: string;
    utc_offset_seconds: number;
    time_accuracy: "exact" | "approximate_15m" | "approximate_hour" | "unknown";
  };
  snapshot_id: string | null;
  sections: Record<string, SectionStatus>;
  interpretation: InterpretationBundle | null;
  evidence?: { facts: EvidenceFact[]; packets: unknown[] } | null;
  entitlement: {
    report_full: boolean;
    report_ready: boolean;
  };
  pdf: {
    status: "locked" | "generating" | "ready" | "failed";
    pages?: number | null;
    size_bytes?: number | null;
    error_code?: string | null;
    render_request_id?: string | null;
    render_preferences?: PdfRenderPreferences | null;
  };
};

export type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
    recoverable?: boolean;
    trace_id?: string;
    detail?: Record<string, unknown>;
  };
};

export class ApiError extends Error {
  status: number;
  code?: string;
  recoverable?: boolean;
  traceId?: string;
  detail?: Record<string, unknown>;

  constructor(status: number, payload?: ApiErrorPayload) {
    super(payload?.error?.message || "Не удалось выполнить запрос");
    this.name = "ApiError";
    this.status = status;
    this.code = payload?.error?.code;
    this.recoverable = payload?.error?.recoverable;
    this.traceId = payload?.error?.trace_id;
    this.detail = payload?.error?.detail;
  }
}

function randomKey(prefix: string) {
  const fallback = Math.random().toString(36).slice(2);
  return `${prefix}-${globalThis.crypto?.randomUUID?.() ?? fallback}`;
}

async function request<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    credentials: "same-origin",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let payload: ApiErrorPayload | undefined;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      // The status still carries enough context for the fallback error.
    }
    throw new ApiError(response.status, payload);
  }
  return (await response.json()) as T;
}

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<PlaceOption[]> {
  const normalized = query.trim();
  if (normalized.length < 2) return [];
  const url = new URL("/api/v1/places/search", window.location.origin);
  url.searchParams.set("q", normalized);
  const payload = await request<{ items: PlaceOption[] }>(url, { signal });
  return payload.items;
}

export async function createChart(input: {
  localDate: string;
  localTime: string;
  placeId: string;
  place: {
    displayName: string;
    countryCode: string;
    latitude: number;
    longitude: number;
    timezone: string;
  };
  timeAccuracy: ChartResource["birth"]["time_accuracy"];
  personalDataConsent: boolean;
  termsAccepted: boolean;
}): Promise<{ chart_id: string }> {
  return request("/api/v1/charts", {
    method: "POST",
    headers: { "Idempotency-Key": randomKey("chart") },
    body: JSON.stringify({
      local_date: input.localDate,
      local_time: input.localTime,
      place_id: input.placeId,
      place: {
        place_id: input.placeId,
        display_name: input.place.displayName,
        country_code: input.place.countryCode,
        latitude: input.place.latitude,
        longitude: input.place.longitude,
        tzid: input.place.timezone,
      },
      time_accuracy: input.timeAccuracy,
      legal: {
        personal_data: input.personalDataConsent,
        personal_data_version: LEGAL_DOCUMENT_VERSIONS.personalDataConsent,
        terms: input.termsAccepted,
        terms_version: LEGAL_DOCUMENT_VERSIONS.terms,
      },
    }),
  });
}

export function getChart(chartId: string): Promise<ChartResource> {
  return request(`/api/v1/charts/${encodeURIComponent(chartId)}`);
}

export function getSection(chartId: string, section: string): Promise<ChartSection> {
  return request(`/api/v1/charts/${encodeURIComponent(chartId)}/sections/${encodeURIComponent(section)}`);
}

export function getVarga(chartId: string, varga: string): Promise<ChartSection> {
  return request(`/api/v1/charts/${encodeURIComponent(chartId)}/vargas/${encodeURIComponent(varga)}`);
}

export type PurchaseStatus =
  | "created"
  | "pending"
  | "unknown"
  | "succeeded"
  | "cancelled"
  | "failed"
  | "partially_refunded"
  | "refunded";

export type ProductCode = "full_report_v1" | "birth_time_rectification_v1";

export type PurchaseResource = {
  purchase_id: string;
  chart_id: string;
  product_code: ProductCode;
  status: PurchaseStatus;
  checkout_url: string | null;
  price_minor: number;
  currency: string;
  retryable: boolean;
};

export type PaymentPublicConfig = {
  product_code: ProductCode;
  title: string;
  price_minor: number;
  currency: string;
  offer_version: string;
  offer_url: string;
  privacy_url: string;
};

export function getPaymentConfig(productCode: ProductCode = "full_report_v1"): Promise<PaymentPublicConfig> {
  const url = new URL("/api/v1/payments/config", window.location.origin);
  url.searchParams.set("product_code", productCode);
  return request(url);
}

export async function createPurchase(
  chartId: string,
  input: { email: string; offerVersion: string; productCode?: ProductCode },
): Promise<PurchaseResource> {
  return request(`/api/v1/charts/${encodeURIComponent(chartId)}/purchases`, {
    method: "POST",
    headers: { "Idempotency-Key": randomKey("purchase") },
    body: JSON.stringify({
      product_code: input.productCode ?? "full_report_v1",
      email: input.email,
      offer_accepted: true,
      offer_version: input.offerVersion,
    }),
  });
}

export type RectificationEventType =
  | "education"
  | "career"
  | "marriage"
  | "childbirth"
  | "relocation"
  | "property"
  | "accident";

export type RectificationResult = {
  selected_time: string;
  confidence: "low" | "medium" | "high";
  uncertainty_minutes: number;
  score_percent: number;
  candidate_count_expected: number;
  candidate_count_scored: number;
  fit_event_count: number;
  holdout_event_count: number;
  holdout_supported: boolean;
  lagna: string;
  alternatives: Array<{ time: string; lagna: string; score_percent: number }>;
  algorithm_version: "rectification.v1";
  disclaimer: string;
};

export type RectificationResource = {
  chart_id: string;
  status: "awaiting_answers" | "queued" | "running" | "ready" | "failed";
  birth_date: string;
  birth_place: string;
  result: RectificationResult | null;
  error: string | null;
};

export function getRectification(chartId: string, signal?: AbortSignal): Promise<RectificationResource> {
  return request(`/api/v1/charts/${encodeURIComponent(chartId)}/rectification`, { signal });
}

export function submitRectification(
  chartId: string,
  input: {
    timeWindow: "unknown" | "night" | "morning" | "day" | "evening";
    events: Array<{ eventType: RectificationEventType; year: number; month: number | null }>;
  },
): Promise<RectificationResource> {
  return request(`/api/v1/charts/${encodeURIComponent(chartId)}/rectification`, {
    method: "POST",
    body: JSON.stringify({
      time_window: input.timeWindow,
      events: input.events.map((event) => ({
        event_type: event.eventType,
        year: event.year,
        month: event.month,
      })),
    }),
  });
}

export function getPurchase(purchaseId: string, signal?: AbortSignal): Promise<PurchaseResource> {
  return request(`/api/v1/purchases/${encodeURIComponent(purchaseId)}`, { signal });
}

export function confirmTestPurchase(purchaseId: string) {
  return request<{ purchase_id: string; status: string }>(
    `/api/v1/test/purchases/${encodeURIComponent(purchaseId)}/confirm`,
    { method: "POST" },
  );
}

export type ReflectionStatus = "saved" | "thinking" | "return_later";

export type PdfRenderPreferences = {
  schema_version: "pdf-render-preferences.v1";
  varga: string;
  mode: "plain" | "expert";
  chart_style: "south_indian";
};

export type SavedQuestion = {
  question_id: string;
  saved: boolean;
  reflection_status: ReflectionStatus;
  note: string | null;
};

export function saveQuestion(chartId: string, questionId: string, saved: boolean, note: string | null = null, reflectionStatus: ReflectionStatus = "saved") {
  return request(`/api/v1/charts/${encodeURIComponent(chartId)}/questions/${encodeURIComponent(questionId)}`, {
    method: "PUT",
    body: JSON.stringify({ saved, note, reflection_status: reflectionStatus }),
  });
}

export function getSavedQuestions(chartId: string): Promise<{ items: SavedQuestion[] }> {
  return request(`/api/v1/charts/${encodeURIComponent(chartId)}/questions/saved`);
}

export function startPdf(chartId: string, preferences: PdfRenderPreferences) {
  return request<{
    job_id: string;
    render_request_id: string;
    status: string;
    preferences: PdfRenderPreferences;
  }>(`/api/v1/charts/${encodeURIComponent(chartId)}/reports/pdf`, {
    method: "POST",
    body: JSON.stringify({ preferences }),
  });
}

export function getPdfRenderStatus(chartId: string, renderRequestId: string) {
  return request<{
    status: "queued" | "generating" | "ready" | "failed";
    render_request_id: string;
    preferences: PdfRenderPreferences;
    pages: number | null;
    size_bytes: number | null;
    error_code: string | null;
  }>(`/api/v1/charts/${encodeURIComponent(chartId)}/reports/pdf/requests/${encodeURIComponent(renderRequestId)}`);
}

export function reportDownloadUrl(chartId: string, renderRequestId: string) {
  const query = new URLSearchParams({ render_request_id: renderRequestId });
  return `/api/v1/charts/${encodeURIComponent(chartId)}/reports/pdf?${query.toString()}`;
}

export function subscribeToChartEvents(
  chartId: string,
  handlers: {
    onEvent: (event: { type: string; data: Record<string, unknown>; id: string }) => void;
    onError: () => void;
  },
) {
  const source = new EventSource(`/api/v1/charts/${encodeURIComponent(chartId)}/events`);
  const knownEvents = [
    "chart.accepted", "calculation.started", "d1.ready", "calculation.partial", "evidence.ready",
    "interpretation.started", "interpretation.validating", "interpretation.ready", "questions.ready",
    "payment.pending", "entitlement.granted", "report.started", "report.section_ready", "report.ready", "pdf.started", "pdf.ready", "job.failed",
  ];
  for (const name of knownEvents) {
    source.addEventListener(name, (event) => {
      const message = event as MessageEvent<string>;
      try {
        handlers.onEvent({ type: name, data: JSON.parse(message.data) as Record<string, unknown>, id: message.lastEventId });
      } catch {
        handlers.onEvent({ type: name, data: {}, id: message.lastEventId });
      }
    });
  }
  source.onerror = handlers.onError;
  return () => source.close();
}

import {
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowLeft,
  Bookmark,
  Check,
  ChevronLeft,
  ChevronRight,
  Clipboard,
  Download,
  Info,
  LockKeyhole,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";

import {
  type ChartResource,
  type ChartSection,
  type DomainCard,
  type DomainSlug,
  type EvidenceFact,
  type ReflectionQuestion,
  type ReflectionStatus,
  type PaymentPublicConfig,
  createPurchase,
  getChart,
  getPaymentConfig,
  getPdfRenderStatus,
  getSavedQuestions,
  getSection,
  getVarga,
  reportDownloadUrl,
  retryChartJob,
  saveQuestion,
  startPdf,
  subscribeToChartEvents,
} from "../lib/chart-api";
import { trackWorkspaceEvent } from "../lib/analytics";
import {
  clearPaymentReturnState,
  pollPurchase,
  readPaymentReturnState,
  savePaymentReturnState,
  type PaymentReturnState,
} from "../lib/payment-return";
import { PaymentPaywall } from "./PaymentPaywall";
import { CalculationLoader } from "./CalculationLoader";
import { SouthIndianChart, formatChartDegree } from "./SouthIndianChart";

type TabId = "chart" | "explanation" | "questions";

type RouteState = {
  tab: TabId;
  varga: string;
  domain: DomainSlug | null;
  detail: boolean;
  question: string | null;
};

type ChartWorkspaceProps = {
  chartId: string;
  onBackToLanding: () => void;
};

type SavedQuestionState = {
  saved: boolean;
  reflectionStatus: ReflectionStatus;
  note: string | null;
};

type PaymentRecovery = {
  state: "checking" | "preparing" | "timeout" | "cancelled" | "failed";
  message: string;
};

type PaidAccessState = "locked" | "preparing" | "ready";

const reflectionStatusLabels: Record<ReflectionStatus, string> = {
  saved: "Сохранено",
  thinking: "Обдумываю",
  return_later: "Вернуться позже",
};

const domainLabels: Record<DomainSlug, string> = {
  character: "Характер",
  inner_support: "Внутренние опоры",
  relationships: "Отношения",
  family_home: "Семья и дом",
  work: "Работа",
  money: "Деньги",
  learning: "Обучение",
  current_period: "Текущий период",
};

const vargas = ["D1", "D2", "D4", "D9", "D10", "D12", "D24"];

function readRouteState(): RouteState {
  const params = new URLSearchParams(window.location.search);
  const rawTab = params.get("tab");
  const rawDomain = params.get("domain") as DomainSlug | null;
  return {
    tab: rawTab === "explanation" || rawTab === "questions"
      ? rawTab
      : params.has("payment_return")
        ? "explanation"
        : "chart",
    varga: vargas.includes(params.get("varga") ?? "") ? params.get("varga")! : "D1",
    domain: rawDomain && rawDomain in domainLabels ? rawDomain : null,
    detail: params.get("detail") === "open",
    question: params.get("question"),
  };
}

function russianDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(new Date(year, month - 1, day));
}

function utcOffset(seconds: number) {
  const sign = seconds >= 0 ? "+" : "−";
  const total = Math.abs(seconds) / 3600;
  return `UTC${sign}${Number.isInteger(total) ? total : total.toFixed(1)}`;
}

type DashaPeriod = { lord?: string; start?: string; end?: string };

export function currentDashaIndex(periods: DashaPeriod[], now = new Date()) {
  const timestamp = now.getTime();
  return periods.findIndex((period) => {
    const start = period.start ? Date.parse(period.start) : Number.NaN;
    const end = period.end ? Date.parse(period.end) : Number.NaN;
    return Number.isFinite(start) && Number.isFinite(end) && start <= timestamp && timestamp < end;
  });
}

export async function downloadReportFile(url: string, filename: string) {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw new Error("Сервер не отдал готовый PDF. Повторите загрузку.");

  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}

function statusText(resource: ChartResource | null, connection: "live" | "reconnecting" | "offline") {
  if (connection === "offline") return "Нет соединения. Готовые данные остаются доступными.";
  if (connection === "reconnecting") return "Восстанавливаем соединение";
  if (!resource) return "Проверяем данные";
  if (resource.sections.d1 !== "ready") return "Строим основную карту";
  if (["error", "unavailable"].includes(resource.sections.interpretation)) {
    return "Объяснение не подготовилось. Запустите его ещё раз";
  }
  if (!resource.interpretation) return "Карта готова. Готовим объяснение";
  if (resource.entitlement.report_full && !resource.entitlement.report_ready) {
    return "Оплата подтверждена. Готовим полный отчёт";
  }
  if (resource.interpretation.schema_version === "interpretation.free.v1") return "Карта и первое чтение готовы";
  if (resource.pdf.status === "generating") return "Открываем подробные разделы. PDF готовится";
  return "Полный отчёт готов";
}

function paidAccessState(resource: ChartResource | null): PaidAccessState {
  if (!resource?.entitlement.report_full) return "locked";
  if (
    resource.entitlement.report_ready
    && resource.interpretation?.schema_version === "interpretation.paid.v1"
  ) {
    return "ready";
  }
  return "preparing";
}

function useRouteState() {
  const [route, setRoute] = useState<RouteState>(() => readRouteState());
  useEffect(() => {
    const onPopState = () => setRoute(readRouteState());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);
  const update = useCallback((next: Partial<RouteState>, replace = false) => {
    const current = readRouteState();
    const merged = { ...current, ...next };
    const params = new URLSearchParams();
    params.set("tab", merged.tab);
    if (merged.tab === "chart") {
      params.set("varga", merged.varga);
    }
    if (merged.domain) params.set("domain", merged.domain);
    if (merged.detail) params.set("detail", "open");
    if (merged.question) params.set("question", merged.question);
    const target = `${window.location.pathname}?${params.toString()}`;
    window.history[replace ? "replaceState" : "pushState"]({}, "", target);
    setRoute(merged);
  }, []);
  return [route, update] as const;
}

function Modal({ children, titleId, onClose, className = "" }: { children: ReactNode; titleId: string; onClose: () => void; className?: string }) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const timer = window.setTimeout(() => dialog?.querySelector<HTMLElement>("[data-autofocus], button, [href], input")?.focus(), 0);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const targets = Array.from(dialog.querySelectorAll<HTMLElement>("button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"));
      if (!targets.length) return;
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(timer);
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      previousFocus.current?.focus();
    };
  }, [onClose]);
  return (
    <div className="workspace-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div ref={dialogRef} className={`workspace-modal ${className}`} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        {children}
      </div>
    </div>
  );
}

function EvidenceChips({ evidenceIds, facts }: { evidenceIds: string[]; facts: Map<string, EvidenceFact> }) {
  const [opened, setOpened] = useState<string | null>(null);
  return (
    <div className="evidence-chips">
      {evidenceIds.map((id) => {
        const fact = facts.get(id);
        if (!fact) return null;
        const active = opened === id;
        return (
          <div key={id} className="evidence-chip-wrap">
            <button type="button" className="evidence-chip" aria-expanded={active} onClick={() => setOpened(active ? null : id)}>
              <Info aria-hidden="true" /> {fact.human_label_ru}
            </button>
            {active && <p className="evidence-chip__detail">Факт карты: {fact.sign ?? ""}{fact.house ? ` · дом ${fact.house}` : ""}</p>}
          </div>
        );
      })}
    </div>
  );
}

function DomainCardView({ domain, facts, access, onOpen }: { domain: DomainCard; facts: Map<string, EvidenceFact>; access: PaidAccessState; onOpen: () => void }) {
  const coverageCopy = domain.coverage === "multiple_factors" ? "Подтверждено несколькими положениями" : domain.coverage === "single_factor" ? "Один расчётный ориентир" : "Нужно больше расчётных данных";
  return (
    <article
      className={`domain-card domain-card--${domain.coverage}`}
      id={`domain-card-${domain.slug}`}
      tabIndex={-1}
    >
      <div className="domain-card__topline"><span>{domain.section_label}</span><small>{coverageCopy}</small></div>
      <h3>{domain.title}</h3>
      <p>{domain.summary}</p>
      {domain.limitations.length > 0 && <p className="domain-card__limit">{domain.limitations[0]}</p>}
      <EvidenceChips evidenceIds={domain.evidence_ids} facts={facts} />
      <button type="button" className="text-action" onClick={onOpen} disabled={domain.coverage === "insufficient" || access === "preparing"}>
        {access === "locked"
          ? <><LockKeyhole aria-hidden="true" /> Открыть полный текст</>
          : access === "preparing"
            ? <><Sparkles aria-hidden="true" /> Готовим полный текст</>
            : <>Читать полностью <ChevronRight aria-hidden="true" /></>}
      </button>
    </article>
  );
}

function LockedReportPanel({ config, onOpen }: { config: PaymentPublicConfig | null; onOpen: () => void }) {
  const price = config ? `${Math.round(config.price_minor / 100).toLocaleString("ru-RU")} ₽` : null;
  return (
    <div className="locked-report__paywall" role="region" aria-label="Доступ к полному разбору">
      <LockKeyhole aria-hidden="true" />
      <span>Полный персональный разбор</span>
      <h2>Продолжите первое чтение вашей карты</h2>
      <p>Выше уже показаны персональные выводы по вашим исходным данным. Полная версия раскрывает каждую связь и собирает темы в единый разбор.</p>
      <ul>
        <li><Check aria-hidden="true" /><span>8 тем, включая профессиональные направления и способы заработка</span></li>
        <li><Check aria-hidden="true" /><span>Текущий и будущие периоды Вимшоттари с точными границами</span></li>
        <li><Check aria-hidden="true" /><span>Общий синтез, 12 вопросов и персональный PDF</span></li>
      </ul>
      <p className="locked-report__ready">Доступ откроется после подтверждения оплаты.</p>
      <div className="locked-report__actions">
        <button type="button" className="primary-button" onClick={onOpen} disabled={!config}>
          {price ? `Открыть полный разбор · ${price}` : "Загружаем условия оплаты"}
        </button>
        <a className="secondary-button" href="/report-example" target="_blank" rel="noreferrer">
          Посмотреть пример полного отчёта
        </a>
      </div>
      <a href="#workspace-panel-explanation">Вернуться к первому чтению</a>
    </div>
  );
}

export function DomainDetail({ domain, facts, index, total, onClose, onPrevious, onNext }: { domain: DomainCard; facts: Map<string, EvidenceFact>; index: number; total: number; onClose: () => void; onPrevious: () => void; onNext: () => void }) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const previousDomain = useRef(domain.slug);

  useLayoutEffect(() => {
    if (previousDomain.current === domain.slug) return;
    previousDomain.current = domain.slug;
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
    headingRef.current?.focus({ preventScroll: true });
  }, [domain.slug]);

  return (
    <Modal titleId="domain-detail-title" onClose={onClose} className="workspace-modal--detail">
      <header className="workspace-modal__header">
        <div><span className="workspace-modal__kicker">{domain.section_label} · {index + 1}/{total}</span><h2 ref={headingRef} id="domain-detail-title" tabIndex={-1} data-autofocus>{domain.title}</h2></div>
        <button type="button" className="icon-button" aria-label="Закрыть подробный текст" onClick={onClose}><X aria-hidden="true" /></button>
      </header>
      <div ref={bodyRef} className="domain-detail__body">
        <p className="domain-detail__summary">{domain.summary}</p>
        {domain.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
        {domain.manifestations.length > 0 && <><h3>Что наблюдать</h3><ul>{domain.manifestations.map((item) => <li key={item}>{item}</li>)}</ul></>}
        <h3>На чём основано</h3>
        <EvidenceChips evidenceIds={domain.evidence_ids} facts={facts} />
        {domain.reflection_prompts.length > 0 && <><h3>Вопрос к себе</h3><p>{domain.reflection_prompts[0]}</p></>}
      </div>
      <footer className="workspace-modal__footer"><button type="button" className="secondary-button" onClick={onPrevious}><ChevronLeft aria-hidden="true" /> Предыдущая</button><button type="button" className="secondary-button" onClick={onNext}>Следующая <ChevronRight aria-hidden="true" /></button></footer>
    </Modal>
  );
}

function QuestionCard({ question, index, facts, saved, reflectionStatus, storedNote, onSave, onSetStatus, onSaveNote, onFocus }: { question: ReflectionQuestion; index: number; facts: Map<string, EvidenceFact>; saved: boolean; reflectionStatus: ReflectionStatus; storedNote: string | null; onSave: () => void; onSetStatus: (status: ReflectionStatus) => void; onSaveNote: (note: string) => void; onFocus: () => void }) {
  const [why, setWhy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [statusMenuOpen, setStatusMenuOpen] = useState(false);
  const [note, setNote] = useState(storedNote ?? "");
  useEffect(() => setNote(storedNote ?? ""), [question.id, storedNote]);
  function updateNote(value: string) {
    setNote(value);
  }
  async function copyQuestion() {
    try {
      await navigator.clipboard.writeText(question.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }
  return (
    <article id={`question-${question.id}`} className="question-card" onFocus={onFocus} tabIndex={-1}>
      <header><span>{String(index + 1).padStart(2, "0")}</span><small>{domainLabels[question.domain]}</small></header>
      <h3>{question.text}</h3>
      <div className="question-card__actions"><button type="button" onClick={onSave}><Bookmark aria-hidden="true" /> {saved ? "Сохранено" : "Сохранить"}</button>{saved && <div className="question-card__status"><button type="button" aria-expanded={statusMenuOpen} aria-controls={`question-status-${question.id}`} onClick={() => setStatusMenuOpen((current) => !current)}>{reflectionStatusLabels[reflectionStatus]}</button>{statusMenuOpen && <div id={`question-status-${question.id}`} className="question-status-menu" role="group" aria-label="Статус вопроса">{(Object.keys(reflectionStatusLabels) as ReflectionStatus[]).map((status) => <button key={status} type="button" className={status === reflectionStatus ? "is-active" : ""} onClick={() => { onSetStatus(status); setStatusMenuOpen(false); }}>{reflectionStatusLabels[status]}</button>)}</div>}</div>}<button type="button" aria-expanded={why} onClick={() => setWhy((current) => !current)}><Info aria-hidden="true" /> Почему этот вопрос</button><button type="button" onClick={copyQuestion}><Clipboard aria-hidden="true" /> {copied ? "Скопировано" : "Копировать"}</button></div>
      {why && <div className="question-card__why"><p>{question.rationale}</p><EvidenceChips evidenceIds={question.evidence_ids} facts={facts} /></div>}
      {saved && <label className="question-card__note">Моя заметка<textarea value={note} onChange={(event) => updateNote(event.target.value)} onBlur={() => onSaveNote(note)} placeholder="Сохранится в этой карте" /></label>}
    </article>
  );
}

export function ChartWorkspace({ chartId, onBackToLanding }: ChartWorkspaceProps) {
  const [route, updateRoute] = useRouteState();
  const [resource, setResource] = useState<ChartResource | null>(null);
  const [d1, setD1] = useState<ChartSection | null>(null);
  const [activeVarga, setActiveVarga] = useState<ChartSection | null>(null);
  const [panchanga, setPanchanga] = useState<ChartSection | null>(null);
  const [dashas, setDashas] = useState<ChartSection | null>(null);
  const [savedQuestions, setSavedQuestions] = useState<Map<string, SavedQuestionState>>(new Map());
  const [selectedSign, setSelectedSign] = useState<number | null>(null);
  const [detailDomain, setDetailDomain] = useState<DomainSlug | null>(null);
  const [paywallDomain, setPaywallDomain] = useState<DomainSlug | null>(null);
  const [networkState, setNetworkState] = useState<"live" | "reconnecting" | "offline">("live");
  const [error, setError] = useState<string | null>(null);
  const [questionFilter, setQuestionFilter] = useState<"all" | "saved">("all");
  const [paymentConfig, setPaymentConfig] = useState<PaymentPublicConfig | null>(null);
  const [paymentRecovery, setPaymentRecovery] = useState<PaymentRecovery | null>(null);
  const [recoveryAttempt, setRecoveryAttempt] = useState(0);
  const [interpretationRetrying, setInterpretationRetrying] = useState(false);
  const [pdfDownloading, setPdfDownloading] = useState(false);
  const reconnectTimer = useRef<number | null>(null);
  const recoveryRun = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await getChart(chartId);
      setResource(next);
      setError(null);
      return next;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обновить карту");
      return null;
    }
  }, [chartId]);

  const clearReturnLocation = useCallback(() => {
    const params = new URLSearchParams(window.location.search);
    params.delete("payment_return");
    const search = params.toString();
    window.history.replaceState({}, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
  }, []);

  const recoverReturnedPayment = useCallback(async (saved: PaymentReturnState, signal: AbortSignal) => {
    setPaymentRecovery({ state: "checking", message: "Проверяем платёж по данным YooKassa" });
    trackWorkspaceEvent("payment_returned");
    const result = await pollPurchase(saved.purchaseId, { signal });
    if (signal.aborted || result.outcome === "aborted") return;
    if (result.outcome === "succeeded") {
      trackWorkspaceEvent("payment_server_confirmed");
      let accessConfirmed = false;
      for (let attempt = 0; attempt < 60 && !signal.aborted; attempt += 1) {
        const next = await refresh();
        if (next?.entitlement.report_full) {
          if (!accessConfirmed) {
            accessConfirmed = true;
            setPaywallDomain(null);
            setDetailDomain(null);
            if (saved.domain) {
              updateRoute({ tab: "explanation", domain: saved.domain, detail: true }, true);
            } else {
              updateRoute({ tab: "explanation", domain: null, detail: false }, true);
            }
          }
          if (
            next.entitlement.report_ready
            && next.interpretation?.schema_version === "interpretation.paid.v1"
          ) {
            clearPaymentReturnState(window.sessionStorage);
            setPaymentRecovery(null);
            if (saved.domain) setDetailDomain(saved.domain);
            return;
          }
          setPaymentRecovery({
            state: "preparing",
            message: "Оплата подтверждена. Готовим полный отчёт. Он откроется автоматически.",
          });
        }
        await new Promise<void>((resolve) => window.setTimeout(resolve, 500));
      }
      if (accessConfirmed) {
        setPaymentRecovery({
          state: "preparing",
          message: "Оплата подтверждена. Готовим полный отчёт. Он откроется автоматически.",
        });
        return;
      }
      setPaymentRecovery({
        state: "timeout",
        message: "Платёж подтверждён, но доступ ещё не появился. Проверку можно продолжить.",
      });
      return;
    }
    if (result.outcome === "cancelled" || result.outcome === "failed") {
      clearPaymentReturnState(window.sessionStorage);
      clearReturnLocation();
      if (saved.domain) setPaywallDomain(saved.domain);
      const cancelled = result.outcome === "cancelled";
      setPaymentRecovery({
        state: cancelled ? "cancelled" : "failed",
        message: cancelled
          ? "Оплата отменена. Списание не подтверждено, можно попробовать ещё раз."
          : "YooKassa не подтвердила платёж. Попробуйте создать новую оплату.",
      });
      trackWorkspaceEvent(cancelled ? "payment_cancelled" : "payment_failed");
      return;
    }
    setPaymentRecovery({
      state: "timeout",
      message: "Платёж ещё проверяется. Деньги повторно не списываются.",
    });
    trackWorkspaceEvent("payment_timeout");
  }, [clearReturnLocation, refresh, updateRoute]);

  useEffect(() => {
    void getPaymentConfig().then(setPaymentConfig).catch(() => {
      setPaymentRecovery({ state: "failed", message: "Не удалось загрузить условия оплаты. Обновите страницу." });
    });
  }, []);

  useEffect(() => {
    if (!new URLSearchParams(window.location.search).has("payment_return")) return;
    const saved = readPaymentReturnState(window.sessionStorage, chartId, window.location.search);
    if (!saved) {
      setPaymentRecovery({
        state: "failed",
        message: "Не удалось безопасно восстановить платёж. Откройте оплату из этой карты ещё раз.",
      });
      return;
    }
    const runKey = `${saved.purchaseId}:${recoveryAttempt}`;
    if (recoveryRun.current === runKey) return;
    recoveryRun.current = runKey;
    const controller = new AbortController();
    void recoverReturnedPayment(saved, controller.signal).catch((reason) => {
      if (controller.signal.aborted) return;
      setPaymentRecovery({
        state: "timeout",
        message: reason instanceof Error ? reason.message : "Не удалось проверить платёж. Повторите проверку.",
      });
    });
    return () => {
      controller.abort();
      if (recoveryRun.current === runKey) recoveryRun.current = null;
    };
  }, [chartId, recoverReturnedPayment, recoveryAttempt]);

  useEffect(() => {
    let alive = true;
    void refresh();
    const close = typeof EventSource === "undefined" ? () => undefined : subscribeToChartEvents(chartId, {
      onEvent: (event) => {
        if (!alive) return;
        setNetworkState("live");
        if (["d1.ready", "evidence.ready", "interpretation.ready", "questions.ready", "entitlement.granted", "report.ready", "pdf.ready", "job.failed"].includes(event.type)) void refresh();
      },
      onError: () => {
        if (!alive) return;
        setNetworkState("reconnecting");
        if (reconnectTimer.current !== null) window.clearTimeout(reconnectTimer.current);
        reconnectTimer.current = window.setTimeout(() => setNetworkState("offline"), 10_000);
      },
    });
    return () => {
      alive = false;
      close();
      if (reconnectTimer.current !== null) window.clearTimeout(reconnectTimer.current);
    };
  }, [chartId, refresh]);

  useEffect(() => {
    void getSection(chartId, "d1").then(setD1).catch(() => undefined);
  }, [chartId, resource?.sections.d1]);
  useEffect(() => {
    void Promise.all([getSection(chartId, "panchanga"), getSection(chartId, "dashas")])
      .then(([panchangaSection, dashasSection]) => {
        setPanchanga(panchangaSection);
        setDashas(dashasSection);
      })
      .catch(() => undefined);
  }, [chartId, resource?.sections.panchanga, resource?.sections.dashas]);
  useEffect(() => {
    void getSavedQuestions(chartId)
      .then((value) => setSavedQuestions(new Map(value.items.map((item) => [item.question_id, { saved: item.saved, reflectionStatus: item.reflection_status, note: item.note }]))))
      .catch(() => undefined);
  }, [chartId]);
  useEffect(() => {
    if (route.varga === "D1") {
      setActiveVarga(d1);
      return;
    }
    void getVarga(chartId, route.varga).then(setActiveVarga).catch(() => setActiveVarga(null));
  }, [chartId, d1, resource?.sections[route.varga], route.varga]);

  useEffect(() => {
    if (!resource?.interpretation || !route.domain || !route.detail) return;
    const domain = resource.interpretation.domains.find((item) => item.slug === route.domain);
    if (!domain) return;
    const access = paidAccessState(resource);
    if (access === "ready" && domain.paragraphs.length) {
      setPaywallDomain(null);
      setDetailDomain(domain.slug);
      clearPaymentReturnState(window.sessionStorage);
      setPaymentRecovery((current) => (
        current?.state === "checking" || current?.state === "preparing" ? null : current
      ));
    } else if (access === "preparing") {
      setPaywallDomain(null);
      setDetailDomain(null);
      setPaymentRecovery((current) => (
        current?.state === "preparing"
          ? current
          : {
              state: "preparing",
              message: "Оплата подтверждена. Готовим полный отчёт. Он откроется автоматически.",
            }
      ));
    } else {
      setDetailDomain(null);
      updateRoute({ tab: "explanation", domain: null, detail: false, question: null }, true);
    }
  }, [resource, route.detail, route.domain]);

  useEffect(() => {
    if (paidAccessState(resource) !== "ready") return;
    clearPaymentReturnState(window.sessionStorage);
    setPaymentRecovery((current) => (
      current?.state === "checking" || current?.state === "preparing" ? null : current
    ));
  }, [resource]);

  useEffect(() => {
    window.sessionStorage.removeItem(`vedicway:profile:${chartId}`);
  }, [chartId]);

  useEffect(() => {
    if (route.tab === "chart") return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`workspace-panel-${route.tab}`)?.scrollIntoView({
        behavior: new URLSearchParams(window.location.search).has("payment_return")
          || window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        block: "start",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [route.tab]);

  const bundle = resource?.interpretation ?? null;
  const interpretationFailed = resource
    ? ["error", "unavailable"].includes(resource.sections.interpretation)
    : false;
  const facts = useMemo(() => new Map((resource?.evidence?.facts ?? []).map((fact) => [fact.id, fact])), [resource?.evidence?.facts]);
  const domains = bundle?.domains ?? [];
  const accessState = paidAccessState(resource);
  const reportLocked = Boolean(bundle) && accessState === "locked";
  const currentDomain = route.domain ? domains.find((domain) => domain.slug === route.domain) ?? null : null;
  const selectedDetail = detailDomain ? domains.find((domain) => domain.slug === detailDomain) ?? null : null;
  const selectedPaywall = paywallDomain ? domains.find((domain) => domain.slug === paywallDomain) ?? null : null;

  const applyTab = (tab: TabId) => {
    updateRoute({ tab, detail: false, question: null });
    trackWorkspaceEvent("result_tab_opened", { tab });
  };

  const retryInterpretation = async () => {
    setInterpretationRetrying(true);
    setError(null);
    try {
      await retryChartJob(chartId, "interpretation_free_v1");
      await refresh();
      trackWorkspaceEvent("interpretation_retry_requested");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось повторно запустить объяснение");
    } finally {
      setInterpretationRetrying(false);
    }
  };
  const showPaywall = (domain: DomainCard) => {
    setDetailDomain(null);
    setPaywallDomain(domain.slug);
    updateRoute({ tab: "explanation", domain: null, detail: false, question: null }, true);
  };

  const openDomain = (domain: DomainCard) => {
    if (accessState === "ready" && domain.paragraphs.length) {
      updateRoute({ tab: "explanation", domain: domain.slug, detail: true });
      setPaywallDomain(null);
      setDetailDomain(domain.slug);
    } else if (accessState === "preparing") {
      updateRoute({ tab: "explanation", domain: domain.slug, detail: true });
      setPaywallDomain(null);
      setDetailDomain(null);
      setPaymentRecovery({
        state: "preparing",
        message: "Оплата подтверждена. Готовим полный отчёт. Он откроется автоматически.",
      });
    } else {
      showPaywall(domain);
    }
    trackWorkspaceEvent("domain_detail_requested", { domain: domain.slug, access: accessState });
  };

  const selectDomain = (domain: DomainCard | null) => {
    updateRoute({ tab: "explanation", domain: domain?.slug ?? null, detail: false });
    const targetId = domain ? `domain-card-${domain.slug}` : "workspace-explanation-overview";
    window.requestAnimationFrame(() => {
      const target = document.getElementById(targetId);
      target?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "center",
      });
      target?.focus({ preventScroll: true });
    });
    trackWorkspaceEvent("explanation_domain_selected", { domain: domain?.slug ?? "all" });
  };

  const openSynthesis = () => {
    window.requestAnimationFrame(() => {
      const target = document.getElementById("workspace-explanation-synthesis");
      const heading = document.getElementById("workspace-explanation-synthesis-title");
      target?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
      heading?.focus({ preventScroll: true });
    });
    trackWorkspaceEvent("report_synthesis_opened");
  };

  const buyFullReport = async (email: string) => {
    if (!paymentConfig) throw new Error("Условия оплаты ещё загружаются. Повторите через несколько секунд.");
    const purchase = await createPurchase(chartId, {
      email,
      offerVersion: paymentConfig.offer_version,
    });
    trackWorkspaceEvent("checkout_started", { price_minor: purchase.price_minor });
    savePaymentReturnState(window.sessionStorage, {
      purchaseId: purchase.purchase_id,
      chartId,
      domain: paywallDomain,
    });
    if (!purchase.checkout_url) {
      throw new Error("Платёж создан, но YooKassa ещё не вернула ссылку. Повторите запрос через несколько секунд.");
    }
    window.location.assign(purchase.checkout_url);
  };

  const toggleSavedQuestion = async (questionId: string) => {
    const previous = savedQuestions.get(questionId) ?? { saved: false, reflectionStatus: "saved" as const, note: null };
    const next = { ...previous, saved: !previous.saved };
    setSavedQuestions((current) => new Map(current).set(questionId, next));
    try {
      await saveQuestion(chartId, questionId, next.saved, next.note, next.reflectionStatus);
      trackWorkspaceEvent("question_saved", { saved: next.saved });
    } catch {
      setSavedQuestions((current) => new Map(current).set(questionId, previous));
    }
  };

  const updateQuestionStatus = async (questionId: string, reflectionStatus: ReflectionStatus) => {
    const previous = savedQuestions.get(questionId) ?? { saved: true, reflectionStatus: "saved" as const, note: null };
    const next = { ...previous, saved: true, reflectionStatus };
    setSavedQuestions((current) => new Map(current).set(questionId, next));
    try {
      await saveQuestion(chartId, questionId, true, next.note, reflectionStatus);
      trackWorkspaceEvent("question_status_changed", { reflection_status: reflectionStatus });
    } catch {
      setSavedQuestions((current) => new Map(current).set(questionId, previous));
    }
  };

  const saveQuestionNote = async (questionId: string, note: string) => {
    const previous = savedQuestions.get(questionId);
    if (!previous?.saved) return;
    const next = { ...previous, note };
    setSavedQuestions((current) => new Map(current).set(questionId, next));
    try {
      await saveQuestion(chartId, questionId, true, note, next.reflectionStatus);
    } catch {
      setSavedQuestions((current) => new Map(current).set(questionId, previous));
    }
  };

  const downloadPdf = async () => {
    if (!resource?.entitlement.report_full) {
      const fallback = domains[0];
      if (fallback) showPaywall(fallback);
      return;
    }
    setPdfDownloading(true);
    setError(null);
    const preferences = {
      schema_version: "pdf-render-preferences.v1" as const,
      varga: route.varga,
      mode: "plain" as const,
      chart_style: "south_indian" as const,
    };
    trackWorkspaceEvent("pdf_requested", { status: resource.pdf.status, varga: route.varga, mode: "plain" });
    try {
      const reusableRequestId = resource.pdf.status === "ready"
        && resource.pdf.render_request_id
        && resource.pdf.render_preferences?.varga === preferences.varga
        && resource.pdf.render_preferences?.mode === preferences.mode
        ? resource.pdf.render_request_id
        : null;
      let renderRequestId = reusableRequestId;

      if (!renderRequestId) {
        const render = await startPdf(chartId, preferences);
        renderRequestId = render.render_request_id;
        for (let retry = 0; retry < 40; retry += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 250));
          const status = await getPdfRenderStatus(chartId, renderRequestId);
          if (status.status === "ready") break;
          if (status.status === "failed") {
            throw new Error("Не удалось подготовить PDF. Карта и текст остаются доступны.");
          }
          if (retry === 39) {
            throw new Error("PDF ещё готовится. Повторите загрузку через несколько секунд.");
          }
        }
      }

      await downloadReportFile(
        reportDownloadUrl(chartId, renderRequestId),
        `vedicway-${chartId.replace(/[^a-zA-Z0-9_-]/g, "") || "report"}.pdf`,
      );
      trackWorkspaceEvent("pdf_downloaded", { varga: preferences.varga, mode: preferences.mode });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось запросить PDF");
    } finally {
      setPdfDownloading(false);
    }
  };

  const renderChartTab = () => {
    const data = activeVarga?.data as { cells?: Array<{ planets: Array<{ planet_code: string; label: string; sign_label: string; longitude_in_sign: number; classical: boolean }> }> } | undefined;
    const planets = (data?.cells ?? []).flatMap((cell) => cell.planets).filter((planet, index, all) => all.findIndex((item) => item.planet_code === planet.planet_code) === index);
    const panchangaData = panchanga?.data as Record<string, { name?: string; end?: { local_time?: string; local_date?: string } }> | undefined;
    const dashasData = dashas?.data as { maha_dashas?: DashaPeriod[] } | undefined;
    const dashaPeriods = dashasData?.maha_dashas ?? [];
    const activeDasha = currentDashaIndex(dashaPeriods);
    const visibleDashas = activeDasha >= 0
      ? dashaPeriods.slice(Math.max(0, Math.min(activeDasha - 1, dashaPeriods.length - 3)), Math.max(3, activeDasha + 2))
      : dashaPeriods.slice(0, 3);
    return <section className="workspace-panel workspace-section workspace-chart-panel" id="workspace-panel-chart" aria-labelledby="workspace-heading-chart">
      <WorkspaceHeader resource={resource} headingId="workspace-heading-chart" primary title="Натальная карта" kicker="Ваша карта" controls={<label className="workspace-select"><span>Варга</span><select value={route.varga} onChange={(event) => updateRoute({ varga: event.target.value })}>{vargas.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>} />
      <div className="chart-scene-grid">
        <section className="chart-visual-panel"><SouthIndianChart section={activeVarga} varga={route.varga} selectedSign={selectedSign} onSelectSign={(sign) => setSelectedSign((current) => current === sign ? null : sign)} /></section>
        <aside className="chart-insight-panel">
          <section className="insight-card"><span className="insight-card__eyebrow">С чего начать</span><h3>Сначала посмотрите на лагну и Луну</h3><p>Лагна задаёт отсчёт домов, а Луна помогает заметить эмоциональную опору. Выберите знак в квадрате, чтобы увидеть точные положения.</p><button type="button" className="text-action" onClick={() => applyTab("explanation")}>Перейти к объяснениям <ChevronRight aria-hidden="true" /></button></section>
          <section className="position-table"><h3>Ключевые положения</h3>{planets.length ? <ul>{planets.filter((planet) => planet.classical).map((planet) => <li key={planet.planet_code}><span>{planet.label}</span><span>{planet.sign_label}</span><b>{formatChartDegree(planet.longitude_in_sign)}</b></li>)}</ul> : <div className="lines-skeleton" />}</section>
        </aside>
      </div>
      <div className="chart-lower-grid">
        <section className="data-strip"><h3>Панчанг</h3><dl>{["tithi", "nakshatra", "yoga"].map((key) => <div key={key}><dt>{key === "tithi" ? "Титхи" : key === "nakshatra" ? "Накшатра" : "Йога"}</dt><dd>{panchangaData?.[key]?.name ?? "Подготавливаем"}</dd></div>)}<div><dt>Ваара</dt><dd>{(panchanga?.data as Record<string, string> | undefined)?.vaara ?? "Подготавливаем"}</dd></div></dl></section>
        <section className="data-strip"><h3>Периоды Вимшоттари</h3>{visibleDashas.length ? <ol>{visibleDashas.map((period) => { const current = dashaPeriods.indexOf(period) === activeDasha; return <li className={current ? "is-current" : undefined} key={`${period.lord}-${period.start}`}><b>{period.lord}</b><span>{period.start?.slice(0, 10)} — {period.end?.slice(0, 10) ?? ""}{current && <small>текущий период</small>}</span></li>; })}</ol> : <p>Периоды готовятся отдельно от основной карты.</p>}</section>
        <section className="data-strip"><h3>Метод</h3><p>Сидерический зодиак · айанамша Лахири · дома от лагны. Положения рассчитаны для указанного времени и места рождения.</p></section>
      </div>
    </section>;
  };

  const renderExplanationTab = () => {
    const filtered = currentDomain ? domains.filter((domain) => domain.slug === currentDomain.slug) : domains;
    return <section className="workspace-panel workspace-section workspace-explanation-panel" id="workspace-panel-explanation" aria-labelledby="workspace-heading-explanation">
      <WorkspaceHeader resource={resource} headingId="workspace-heading-explanation" title="Объяснение карты" kicker="Первое чтение" controls={<div className="domain-filter" aria-label="Темы первого чтения"><button type="button" className={!route.domain ? "is-active" : ""} aria-pressed={!route.domain} onClick={() => selectDomain(null)}>Все темы</button>{domains.map((domain) => <button type="button" key={domain.slug} className={route.domain === domain.slug ? "is-active" : ""} aria-pressed={route.domain === domain.slug} onClick={() => selectDomain(domain)}>{domain.section_label}</button>)}</div>} />
      {bundle ? <>
        <section className="overview-card" id="workspace-explanation-overview" tabIndex={-1}><div><span className="overview-card__eyebrow">Ваш первый персональный вывод</span><h3>{bundle.overview.title}</h3><p>{bundle.overview.summary}</p></div>{accessState === "ready" && bundle.synthesis.length > 0 && <button type="button" className="text-action" onClick={openSynthesis}>Читать общий синтез <ChevronRight aria-hidden="true" /></button>}</section>
        {accessState === "ready" && bundle.synthesis.length > 0 && <section className="report-synthesis" id="workspace-explanation-synthesis" aria-labelledby="workspace-explanation-synthesis-title"><span className="overview-card__eyebrow">Полный персональный разбор</span><h3 id="workspace-explanation-synthesis-title" tabIndex={-1}>Общий синтез карты</h3>{bundle.synthesis.map((paragraph, index) => <p key={`${index}-${paragraph}`}>{paragraph}</p>)}</section>}
        <section className="domain-grid" aria-label="Восемь жизненных тем">{filtered.map((domain) => <DomainCardView key={domain.slug} domain={domain} facts={facts} access={accessState} onOpen={() => openDomain(domain)} />)}</section>
      </> : interpretationFailed ? <section className="overview-card" role="alert"><div><span className="overview-card__eyebrow">Объяснение остановилось</span><h3>Карта рассчитана, текст можно запустить повторно</h3><p>Предыдущая попытка завершилась с ошибкой. Расчёт карты и введённые данные сохранены.</p></div><button type="button" className="text-action" onClick={() => void retryInterpretation()} disabled={interpretationRetrying}>{interpretationRetrying ? "Запускаем" : "Повторить объяснение"} <RefreshCw aria-hidden="true" /></button></section> : <CalculationLoader variant="explanation" />}
    </section>;
  };

  const renderQuestionsTab = () => {
    const questions = bundle?.questions ?? [];
    const savedCount = Array.from(savedQuestions.values()).filter((item) => item.saved).length;
    const visible = questionFilter === "saved" ? questions.filter((question) => savedQuestions.get(question.id)?.saved) : questions;
    return <section className="workspace-panel workspace-section workspace-questions-panel" id="workspace-panel-questions" aria-labelledby="workspace-heading-questions">
      <WorkspaceHeader resource={resource} headingId="workspace-heading-questions" title="Вопросы к себе" kicker="Личное наблюдение" controls={<div className="question-progress"><span>{savedCount} сохранено</span><button type="button" className={questionFilter === "all" ? "is-active" : ""} onClick={() => setQuestionFilter("all")}>Все</button><button type="button" className={questionFilter === "saved" ? "is-active" : ""} onClick={() => setQuestionFilter("saved")}>Сохранённые</button></div>} />
      <p className="questions-lead">Вопросы помогают заметить, как темы карты проявляются в ваших решениях.</p>
      {questions.length ? <section className="questions-grid">{visible.map((question, index) => { const state = savedQuestions.get(question.id); return <QuestionCard key={question.id} question={question} index={index} facts={facts} saved={state?.saved ?? false} reflectionStatus={state?.reflectionStatus ?? "saved"} storedNote={state?.note ?? null} onSave={() => void toggleSavedQuestion(question.id)} onSetStatus={(status) => void updateQuestionStatus(question.id, status)} onSaveNote={(note) => void saveQuestionNote(question.id, note)} onFocus={() => updateRoute({ question: question.id }, true)} />; })}</section> : interpretationFailed ? <section className="overview-card" role="alert"><div><span className="overview-card__eyebrow">Вопросы ещё не созданы</span><h3>Сначала повторите подготовку объяснения</h3><p>Вопросы формируются вместе с текстом первого чтения.</p></div><button type="button" className="text-action" onClick={() => void retryInterpretation()} disabled={interpretationRetrying}>{interpretationRetrying ? "Запускаем" : "Повторить"} <RefreshCw aria-hidden="true" /></button></section> : <CalculationLoader variant="questions" />}
      {questionFilter === "saved" && !visible.length && <p className="workspace-notice">Сохранённых вопросов пока нет. Вернитесь к списку и отметьте те, к которым хотите вернуться.</p>}
    </section>;
  };

  const detailIndex = selectedDetail ? domains.findIndex((domain) => domain.slug === selectedDetail.slug) : -1;
  const moveDetail = (delta: number) => {
    const next = domains[(detailIndex + delta + domains.length) % domains.length];
    setDetailDomain(next.slug);
    updateRoute({ domain: next.slug, detail: true }, true);
  };

  return <main className="chart-workspace" data-od-id="chart-workspace">
    <div className="chart-workspace__background" aria-hidden="true" />
    <a className="workspace-skip-link" href="#workspace-content">Перейти к содержанию результата</a>
    <section className="workspace-main" id="workspace-content">
      <header className="workspace-topbar">
        <button type="button" className="back-link" onClick={onBackToLanding}><ArrowLeft aria-hidden="true" /> Исправить данные</button>
        <div className="workspace-topbar__summary"><strong>Ваш персональный разбор</strong><span>Карта, объяснение и вопросы на одной странице</span></div>
        <div className="workspace-topbar__actions"><span aria-live="polite"><Sparkles aria-hidden="true" /> {statusText(resource, networkState)}</span><button type="button" className="rail-pdf" aria-label={!resource?.entitlement.report_full ? "Открыть полный разбор" : pdfDownloading ? "PDF готовится" : "Скачать персональный разбор в PDF"} onClick={() => void downloadPdf()} disabled={pdfDownloading}><Download aria-hidden="true" /><span>{!resource?.entitlement.report_full ? "Открыть полный разбор" : pdfDownloading ? "PDF готовится" : "Скачать PDF"}</span>{!resource?.entitlement.report_full && <LockKeyhole aria-label="Входит в полный отчёт" />}</button></div>
      </header>
      {paymentRecovery && (
        <div
          className={`workspace-notice ${paymentRecovery.state === "failed" ? "workspace-notice--error" : paymentRecovery.state === "cancelled" ? "workspace-notice--warning" : ""}`}
          role={paymentRecovery.state === "checking" || paymentRecovery.state === "preparing" ? "status" : "alert"}
        >
          <span>{paymentRecovery.message}</span>
          {paymentRecovery.state === "timeout" && (
            <button type="button" onClick={() => setRecoveryAttempt((value) => value + 1)}>
              <RefreshCw aria-hidden="true" /> Проверить ещё раз
            </button>
          )}
        </div>
      )}
      {error && <div className="workspace-notice workspace-notice--error" role="alert"><span>{error}</span><button type="button" onClick={() => void refresh()}><RefreshCw aria-hidden="true" /> Повторить</button></div>}
      {renderChartTab()}
      <div className="workspace-report-stack locked-report">
        <div className="locked-report__content">
          {renderExplanationTab()}
          {accessState === "ready" && renderQuestionsTab()}
        </div>
        {reportLocked && <LockedReportPanel config={paymentConfig} onOpen={() => {
          const domain = currentDomain ?? domains[0];
          if (domain) showPaywall(domain);
        }} />}
      </div>
      <p className="workspace-disclaimer">Материал предназначен для самонаблюдения и знакомства с астрологической традицией. Он не заменяет медицинскую, юридическую, финансовую или психологическую помощь.</p>
    </section>
    {selectedDetail && <DomainDetail domain={selectedDetail} facts={facts} index={detailIndex} total={domains.length} onClose={() => { setDetailDomain(null); updateRoute({ tab: "explanation", domain: null, detail: false, question: null }, true); }} onPrevious={() => moveDetail(-1)} onNext={() => moveDetail(1)} />}
    {selectedPaywall && paymentConfig && accessState === "locked" && (
      <PaymentPaywall
        title={selectedPaywall.title}
        summary={selectedPaywall.summary}
        config={paymentConfig}
        evidence={<EvidenceChips evidenceIds={selectedPaywall.evidence_ids} facts={facts} />}
        initialMessage={paymentRecovery?.state === "cancelled" || paymentRecovery?.state === "failed" ? paymentRecovery.message : null}
        onClose={() => {
          setPaywallDomain(null);
          setPaymentRecovery(null);
          updateRoute({ tab: "explanation", domain: null, detail: false, question: null }, true);
        }}
        onCheckout={buyFullReport}
      />
    )}
  </main>;
}

function WorkspaceHeader({ resource, kicker, title, controls, headingId, primary = false }: { resource: ChartResource | null; kicker: string; title: string; controls: ReactNode; headingId: string; primary?: boolean }) {
  const Heading = primary ? "h1" : "h2";
  return <header className="workspace-header"><div><span className="workspace-header__kicker">{kicker}</span><Heading id={headingId}>{title}</Heading>{resource && <p>{russianDate(resource.birth.local_date)} · {resource.birth.local_time} · {resource.birth.place} · {utcOffset(resource.birth.utc_offset_seconds)}{resource.birth.time_accuracy !== "exact" ? " · время указано приблизительно" : ""}</p>}</div><div className="workspace-header__controls"><SlidersHorizontal aria-hidden="true" /> {controls}</div></header>;
}

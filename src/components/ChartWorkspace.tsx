import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import {
  ArrowLeft,
  Bookmark,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clipboard,
  Download,
  Info,
  LockKeyhole,
  Map as MapIcon,
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
  getSavedQuestions,
  getSection,
  getVarga,
  reportDownloadUrl,
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
import { SouthIndianChart, formatChartDegree } from "./SouthIndianChart";

type TabId = "chart" | "explanation" | "questions";
type ChartMode = "plain" | "expert";

type RouteState = {
  tab: TabId;
  varga: string;
  mode: ChartMode;
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
  state: "checking" | "timeout" | "cancelled" | "failed";
  message: string;
};

const reflectionStatusLabels: Record<ReflectionStatus, string> = {
  saved: "Сохранено",
  thinking: "Обдумываю",
  return_later: "Вернуться позже",
};

const tabConfig: Array<{ id: TabId; label: string; compactLabel: string; Icon: typeof MapIcon }> = [
  { id: "chart", label: "Натальная карта", compactLabel: "Карта", Icon: MapIcon },
  { id: "explanation", label: "Объяснение", compactLabel: "Объяснение", Icon: BookOpen },
  { id: "questions", label: "Вопросы к себе", compactLabel: "Вопросы", Icon: CircleHelp },
];

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
  const rawMode = params.get("mode");
  const rawDomain = params.get("domain") as DomainSlug | null;
  return {
    tab: rawTab === "explanation" || rawTab === "questions" ? rawTab : "chart",
    varga: vargas.includes(params.get("varga") ?? "") ? params.get("varga")! : "D1",
    mode: rawMode === "expert" ? "expert" : "plain",
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

function statusText(resource: ChartResource | null, connection: "live" | "reconnecting" | "offline") {
  if (connection === "offline") return "Нет соединения. Готовые данные остаются доступными.";
  if (connection === "reconnecting") return "Восстанавливаем соединение";
  if (!resource) return "Проверяем данные";
  if (resource.sections.d1 !== "ready") return "Строим основную карту";
  if (!resource.interpretation) return "Карта готова. Готовим объяснение";
  if (resource.interpretation.schema_version === "interpretation.free.v1") return "Карта и первое чтение готовы";
  if (resource.pdf.status === "generating") return "Открываем подробные разделы. PDF готовится";
  return "Полный отчёт готов";
}

function byteSize(value?: number | null) {
  if (!value) return null;
  return `${(value / 1024 / 1024).toFixed(1).replace(".", ",")} МБ`;
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
      params.set("mode", merged.mode);
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

function DomainCardView({ domain, facts, locked, onOpen }: { domain: DomainCard; facts: Map<string, EvidenceFact>; locked: boolean; onOpen: () => void }) {
  const coverageCopy = domain.coverage === "multiple_factors" ? "Подтверждено несколькими положениями" : domain.coverage === "single_factor" ? "Один расчётный ориентир" : "Нужно больше расчётных данных";
  return (
    <article className={`domain-card domain-card--${domain.coverage}`}>
      <div className="domain-card__topline"><span>{domain.section_label}</span><small>{coverageCopy}</small></div>
      <h3>{domain.title}</h3>
      <p>{domain.summary}</p>
      {domain.limitations.length > 0 && <p className="domain-card__limit">{domain.limitations[0]}</p>}
      <EvidenceChips evidenceIds={domain.evidence_ids} facts={facts} />
      <button type="button" className="text-action" onClick={onOpen} disabled={domain.coverage === "insufficient"}>
        {locked ? <><LockKeyhole aria-hidden="true" /> Подробнее</> : <>Читать полностью <ChevronRight aria-hidden="true" /></>}
      </button>
    </article>
  );
}

function DomainDetail({ domain, facts, index, total, onClose, onPrevious, onNext }: { domain: DomainCard; facts: Map<string, EvidenceFact>; index: number; total: number; onClose: () => void; onPrevious: () => void; onNext: () => void }) {
  return (
    <Modal titleId="domain-detail-title" onClose={onClose} className="workspace-modal--detail">
      <header className="workspace-modal__header">
        <div><span className="workspace-modal__kicker">{domain.section_label} · {index + 1}/{total}</span><h2 id="domain-detail-title" tabIndex={-1} data-autofocus>{domain.title}</h2></div>
        <button type="button" className="icon-button" aria-label="Закрыть подробный текст" onClick={onClose}><X aria-hidden="true" /></button>
      </header>
      <div className="domain-detail__body">
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
  const root = useRef<HTMLElement>(null);
  const tabs = useRef<Partial<Record<TabId, HTMLButtonElement>>>({});
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
      for (let attempt = 0; attempt < 60 && !signal.aborted; attempt += 1) {
        const next = await refresh();
        if (next?.entitlement.report_full) {
          clearPaymentReturnState(window.sessionStorage);
          setPaymentRecovery(null);
          if (saved.domain) {
            setPaywallDomain(null);
            setDetailDomain(saved.domain);
            updateRoute({ tab: "explanation", domain: saved.domain, detail: true }, true);
          } else {
            clearReturnLocation();
          }
          return;
        }
        await new Promise<void>((resolve) => window.setTimeout(resolve, 500));
      }
      setPaymentRecovery({
        state: "timeout",
        message: "Платёж подтверждён. Подробный отчёт ещё формируется, проверку можно продолжить.",
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
    if (resource.entitlement.report_full && domain.paragraphs.length) {
      setPaywallDomain(null);
      setDetailDomain(domain.slug);
    } else {
      setDetailDomain(null);
      setPaywallDomain(domain.slug);
    }
  }, [resource, route.detail, route.domain]);

  useGSAP(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    gsap.fromTo(".workspace-panel", { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.24, ease: "power3.out", clearProps: "transform" });
  }, { scope: root, dependencies: [route.tab] });

  const bundle = resource?.interpretation ?? null;
  const facts = useMemo(() => new Map((resource?.evidence?.facts ?? []).map((fact) => [fact.id, fact])), [resource?.evidence?.facts]);
  const domains = bundle?.domains ?? [];
  const currentDomain = route.domain ? domains.find((domain) => domain.slug === route.domain) ?? null : null;
  const selectedDetail = detailDomain ? domains.find((domain) => domain.slug === detailDomain) ?? null : null;
  const selectedPaywall = paywallDomain ? domains.find((domain) => domain.slug === paywallDomain) ?? null : null;
  const profileName = useMemo(() => {
    try { return JSON.parse(window.sessionStorage.getItem(`vedicway:profile:${chartId}`) ?? "{}").name || "Без имени"; } catch { return "Без имени"; }
  }, [chartId]);

  const applyTab = (tab: TabId) => {
    updateRoute({ tab, detail: false, question: null });
    trackWorkspaceEvent("result_tab_opened", { tab });
  };
  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, tab: TabId) => {
    const currentIndex = tabConfig.findIndex((item) => item.id === tab);
    let targetIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") targetIndex = (currentIndex + 1) % tabConfig.length;
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") targetIndex = (currentIndex - 1 + tabConfig.length) % tabConfig.length;
    if (event.key === "Home") targetIndex = 0;
    if (event.key === "End") targetIndex = tabConfig.length - 1;
    if (targetIndex !== null) { event.preventDefault(); tabs.current[tabConfig[targetIndex].id]?.focus(); }
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); applyTab(tab); }
  };

  const openDomain = (domain: DomainCard) => {
    updateRoute({ tab: "explanation", domain: domain.slug, detail: true });
    if (resource?.entitlement.report_full && domain.paragraphs.length) {
      setPaywallDomain(null);
      setDetailDomain(domain.slug);
    } else {
      setDetailDomain(null);
      setPaywallDomain(domain.slug);
    }
    trackWorkspaceEvent("domain_detail_requested", { domain: domain.slug, access: resource?.entitlement.report_full ? "paid" : "free" });
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
      if (fallback) setPaywallDomain(fallback.slug);
      return;
    }
    const preferences = {
      schema_version: "pdf-render-preferences.v1" as const,
      varga: route.varga,
      mode: route.mode,
      chart_style: "south_indian" as const,
    };
    trackWorkspaceEvent("pdf_requested", { status: resource.pdf.status, varga: route.varga, mode: route.mode });
    try {
      const render = await startPdf(chartId, preferences);
      for (let retry = 0; retry < 40; retry += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 250));
        const next = await refresh();
        if (next?.pdf.status === "ready" && next.pdf.render_request_id === render.render_request_id) {
          trackWorkspaceEvent("pdf_downloaded", { varga: preferences.varga, mode: preferences.mode });
          window.location.assign(reportDownloadUrl(chartId));
          return;
        }
        if (next?.pdf.status === "failed" && next.pdf.render_request_id === render.render_request_id) {
          setError("Не удалось подготовить PDF. Карта и текст остаются доступны.");
          return;
        }
      }
      setError("PDF ещё готовится. Повторите загрузку через несколько секунд.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось запросить PDF");
    }
  };

  const renderChartTab = () => {
    const data = activeVarga?.data as { cells?: Array<{ planets: Array<{ planet_code: string; label: string; sign_label: string; longitude_in_sign: number; classical: boolean }> }> } | undefined;
    const planets = (data?.cells ?? []).flatMap((cell) => cell.planets).filter((planet, index, all) => all.findIndex((item) => item.planet_code === planet.planet_code) === index);
    const panchangaData = panchanga?.data as Record<string, { name?: string; end?: { local_time?: string; local_date?: string } }> | undefined;
    const dashasData = dashas?.data as { maha_dashas?: Array<{ lord?: string; start?: string; end?: string }> } | undefined;
    return <div className="workspace-panel workspace-chart-panel" role="tabpanel" id="workspace-panel-chart" aria-labelledby="workspace-tab-chart">
      <WorkspaceHeader resource={resource} title="Натальная карта" kicker="Ваша карта" controls={<><label className="workspace-select"><span>Варга</span><select value={route.varga} onChange={(event) => updateRoute({ varga: event.target.value })}>{vargas.map((value) => <option key={value} value={value}>{value}</option>)}</select></label><div className="mode-switch" aria-label="Режим просмотра"><button type="button" className={route.mode === "plain" ? "is-active" : ""} onClick={() => updateRoute({ mode: "plain" })}>Понятно</button><button type="button" className={route.mode === "expert" ? "is-active" : ""} onClick={() => updateRoute({ mode: "expert" })}>Профессионально</button></div></>} />
      <div className="chart-scene-grid">
        <section className="chart-visual-panel"><SouthIndianChart section={activeVarga} varga={route.varga} mode={route.mode} selectedSign={selectedSign} onSelectSign={(sign) => setSelectedSign((current) => current === sign ? null : sign)} /></section>
        <aside className="chart-insight-panel">
          <section className="insight-card"><span className="insight-card__eyebrow">С чего начать</span><h3>Сначала посмотрите на лагну и Луну</h3><p>Лагна задаёт отсчёт домов, а Луна помогает заметить эмоциональную опору. Выберите знак в квадрате, чтобы увидеть точные положения.</p><button type="button" className="text-action" onClick={() => applyTab("explanation")}>Перейти к объяснениям <ChevronRight aria-hidden="true" /></button></section>
          <section className="position-table"><h3>Ключевые положения</h3>{planets.length ? <ul>{planets.filter((planet) => route.mode === "expert" || planet.classical).map((planet) => <li key={planet.planet_code}><span>{planet.label}</span><span>{planet.sign_label}</span><b>{formatChartDegree(planet.longitude_in_sign)}</b></li>)}</ul> : <div className="lines-skeleton" />}</section>
        </aside>
      </div>
      <div className="chart-lower-grid">
        <section className="data-strip"><h3>Панчанг</h3><dl>{["tithi", "nakshatra", "yoga"].map((key) => <div key={key}><dt>{key === "tithi" ? "Титхи" : key === "nakshatra" ? "Накшатра" : "Йога"}</dt><dd>{panchangaData?.[key]?.name ?? "Подготавливаем"}</dd></div>)}<div><dt>Ваара</dt><dd>{(panchanga?.data as Record<string, string> | undefined)?.vaara ?? "Подготавливаем"}</dd></div></dl></section>
        <section className="data-strip"><h3>Периоды Вимшоттари</h3>{dashasData?.maha_dashas?.length ? <ol>{dashasData.maha_dashas.slice(0, 3).map((period) => <li key={`${period.lord}-${period.start}`}><b>{period.lord}</b><span>{period.start?.slice(0, 10)} — {period.end?.slice(0, 10) ?? ""}</span></li>)}</ol> : <p>Периоды готовятся отдельно от основной карты.</p>}</section>
        <section className="data-strip"><h3>Метод</h3><p>Сидерический зодиак · айанамша Лахири · дома от лагны. Положения рассчитаны для указанного времени и места рождения.</p></section>
      </div>
    </div>;
  };

  const renderExplanationTab = () => {
    const filtered = currentDomain ? domains.filter((domain) => domain.slug === currentDomain.slug) : domains;
    return <div className="workspace-panel workspace-explanation-panel" role="tabpanel" id="workspace-panel-explanation" aria-labelledby="workspace-tab-explanation">
      <WorkspaceHeader resource={resource} title="Объяснение карты" kicker="Первое чтение" controls={<div className="domain-filter"><button type="button" className={!route.domain ? "is-active" : ""} onClick={() => updateRoute({ domain: null })}>Все темы</button>{domains.map((domain) => <button type="button" key={domain.slug} className={route.domain === domain.slug ? "is-active" : ""} onClick={() => updateRoute({ domain: domain.slug })}>{domain.section_label}</button>)}</div>} />
      {bundle ? <>
        <section className="overview-card"><div><span className="overview-card__eyebrow">Главный рисунок</span><h2>{bundle.overview.title}</h2><p>{bundle.overview.summary}</p></div><button type="button" className="text-action" onClick={() => domains[0] && openDomain(domains[0])}>{resource?.entitlement.report_full ? "Открыть синтез" : "Продолжить чтение"} <ChevronRight aria-hidden="true" /></button></section>
        <section className="domain-grid" aria-label="Восемь жизненных тем">{filtered.map((domain) => <DomainCardView key={domain.slug} domain={domain} facts={facts} locked={!resource?.entitlement.report_full} onOpen={() => openDomain(domain)} />)}</section>
        {!route.domain && <div className="compact-offer"><span>Полный отчёт объединяет все восемь тем · 990 ₽</span><button type="button" onClick={() => domains[0] && setPaywallDomain(domains[0].slug)}>Посмотреть состав</button></div>}
      </> : <section className="domain-grid domain-grid--skeleton" aria-label="Готовим объяснение">{Array.from({ length: 8 }).map((_, index) => <div className="domain-card" key={index}><div className="lines-skeleton" /><p>Связываем факты карты</p></div>)}</section>}
    </div>;
  };

  const renderQuestionsTab = () => {
    const questions = bundle?.questions ?? [];
    const savedCount = Array.from(savedQuestions.values()).filter((item) => item.saved).length;
    const visible = questionFilter === "saved" ? questions.filter((question) => savedQuestions.get(question.id)?.saved) : questions;
    return <div className="workspace-panel workspace-questions-panel" role="tabpanel" id="workspace-panel-questions" aria-labelledby="workspace-tab-questions">
      <WorkspaceHeader resource={resource} title="Вопросы к себе" kicker="Личное наблюдение" controls={<div className="question-progress"><span>{savedCount} сохранено</span><button type="button" className={questionFilter === "all" ? "is-active" : ""} onClick={() => setQuestionFilter("all")}>Все</button><button type="button" className={questionFilter === "saved" ? "is-active" : ""} onClick={() => setQuestionFilter("saved")}>Сохранённые</button></div>} />
      <p className="questions-lead">Вопросы помогают заметить, как темы карты проявляются в ваших решениях.</p>
      {questions.length ? <section className="questions-grid">{visible.map((question, index) => { const state = savedQuestions.get(question.id); return <QuestionCard key={question.id} question={question} index={index} facts={facts} saved={state?.saved ?? false} reflectionStatus={state?.reflectionStatus ?? "saved"} storedNote={state?.note ?? null} onSave={() => void toggleSavedQuestion(question.id)} onSetStatus={(status) => void updateQuestionStatus(question.id, status)} onSaveNote={(note) => void saveQuestionNote(question.id, note)} onFocus={() => updateRoute({ question: question.id }, true)} />; })}</section> : <section className="questions-grid questions-grid--skeleton">{Array.from({ length: 6 }).map((_, index) => <div key={index} className="question-card"><span>{String(index + 1).padStart(2, "0")}</span><p>Вопрос появится после разбора</p></div>)}</section>}
      {questionFilter === "saved" && !visible.length && <p className="workspace-notice">Сохранённых вопросов пока нет. Вернитесь к списку и отметьте те, к которым хотите вернуться.</p>}
    </div>;
  };

  const detailIndex = selectedDetail ? domains.findIndex((domain) => domain.slug === selectedDetail.slug) : -1;
  const moveDetail = (delta: number) => {
    const next = domains[(detailIndex + delta + domains.length) % domains.length];
    setDetailDomain(next.slug);
    updateRoute({ domain: next.slug, detail: true }, true);
  };

  return <main ref={root} className="chart-workspace" data-od-id="chart-workspace">
    <div className="chart-workspace__background" aria-hidden="true" />
    <a className="workspace-skip-link" href="#workspace-content">Перейти к содержанию результата</a>
    <aside className="workspace-rail">
      <button type="button" className="back-link" onClick={onBackToLanding}><ArrowLeft aria-hidden="true" /> Назад к вводу</button>
      <div className="rail-profile"><span>ВАША КАРТА</span><strong>{profileName}</strong>{resource ? <p>{russianDate(resource.birth.local_date)} · {resource.birth.local_time}<br />{resource.birth.place} · {utcOffset(resource.birth.utc_offset_seconds)}</p> : <p>Проверяем исходные данные</p>}<button type="button" className="rail-edit" onClick={onBackToLanding}>Исправить данные</button></div>
      <nav className="workspace-tabs" role="tablist" aria-label="Разделы результата">{tabConfig.map(({ id, label, compactLabel, Icon }) => <button ref={(node) => { tabs.current[id] = node ?? undefined; }} key={id} id={`workspace-tab-${id}`} type="button" role="tab" aria-selected={route.tab === id} aria-controls={`workspace-panel-${id}`} tabIndex={route.tab === id ? 0 : -1} className={route.tab === id ? "is-active" : ""} onClick={() => applyTab(id)} onKeyDown={(event) => handleTabKeyDown(event, id)}><Icon aria-hidden="true" /><span className="workspace-tabs__label"><span className="workspace-tabs__label-full">{label}</span><span className="workspace-tabs__label-compact">{compactLabel}</span></span><i aria-label={resource?.sections[id === "chart" ? "d1" : id === "explanation" ? "interpretation" : "questions"] === "ready" ? "Раздел готов" : "Раздел готовится"} /></button>)}</nav>
      <div className="rail-bottom"><p className="rail-status" aria-live="polite"><Sparkles aria-hidden="true" /> {statusText(resource, networkState)}</p><button type="button" className="rail-pdf" onClick={() => void downloadPdf()} disabled={resource?.pdf.status === "generating"}><Download aria-hidden="true" /> <span>{resource?.pdf.status === "generating" ? "PDF готовится" : "Скачать PDF"}</span>{!resource?.entitlement.report_full && <LockKeyhole aria-label="Входит в полный отчёт" />}</button><small>{resource?.pdf.status === "ready" ? `PDF · ${resource.pdf.pages ?? ""} стр. · ${byteSize(resource.pdf.size_bytes) ?? ""}` : resource?.entitlement.report_full ? "PDF войдёт в полный отчёт" : "Входит в полный отчёт"}</small></div>
    </aside>
    <section className="workspace-main" id="workspace-content">
      {paymentRecovery && (
        <div
          className={`workspace-notice ${paymentRecovery.state === "failed" ? "workspace-notice--error" : paymentRecovery.state === "cancelled" ? "workspace-notice--warning" : ""}`}
          role={paymentRecovery.state === "checking" ? "status" : "alert"}
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
      {route.tab === "chart" && renderChartTab()}
      {route.tab === "explanation" && renderExplanationTab()}
      {route.tab === "questions" && renderQuestionsTab()}
      <p className="workspace-disclaimer">Материал предназначен для самонаблюдения и знакомства с астрологической традицией. Он не заменяет медицинскую, юридическую, финансовую или психологическую помощь.</p>
    </section>
    {selectedDetail && <DomainDetail domain={selectedDetail} facts={facts} index={detailIndex} total={domains.length} onClose={() => { setDetailDomain(null); updateRoute({ detail: false }, true); }} onPrevious={() => moveDetail(-1)} onNext={() => moveDetail(1)} />}
    {selectedPaywall && paymentConfig && (
      <PaymentPaywall
        title={selectedPaywall.title}
        summary={selectedPaywall.summary}
        config={paymentConfig}
        evidence={<EvidenceChips evidenceIds={selectedPaywall.evidence_ids} facts={facts} />}
        initialMessage={paymentRecovery?.state === "cancelled" || paymentRecovery?.state === "failed" ? paymentRecovery.message : null}
        onClose={() => {
          setPaywallDomain(null);
          setPaymentRecovery(null);
          updateRoute({ detail: false }, true);
        }}
        onCheckout={buyFullReport}
      />
    )}
  </main>;
}

function WorkspaceHeader({ resource, kicker, title, controls }: { resource: ChartResource | null; kicker: string; title: string; controls: ReactNode }) {
  return <header className="workspace-header"><div><span className="workspace-header__kicker">{kicker}</span><h1>{title}</h1>{resource && <p>{russianDate(resource.birth.local_date)} · {resource.birth.local_time} · {resource.birth.place} · {utcOffset(resource.birth.utc_offset_seconds)}{resource.birth.time_accuracy !== "exact" ? " · время указано приблизительно" : ""}</p>}</div><div className="workspace-header__controls"><SlidersHorizontal aria-hidden="true" /> {controls}</div></header>;
}

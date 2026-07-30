import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  LoaderCircle,
  LockKeyhole,
} from "lucide-react";

import {
  ApiError,
  getRectification,
  submitRectification,
  type RectificationEventType,
  type RectificationResource,
} from "../lib/chart-api";
import {
  clearPaymentReturnState,
  pollPurchase,
  readPaymentReturnState,
} from "../lib/payment-return";
import { applySeo } from "../lib/seo";
import { CalculationLoader } from "./CalculationLoader";
import { SiteHeader } from "./SiteHeader";

type RectificationFlowProps = {
  chartId: string;
  onNavigate: (path: string) => void;
};

type EventQuestion = {
  type: RectificationEventType;
  title: string;
  hint: string;
};

type Step =
  | { key: "time_window"; kind: "window"; title: string; hint: string }
  | { key: string; kind: "year"; event: EventQuestion; title: string; hint: string }
  | { key: string; kind: "month"; event: EventQuestion; title: string; hint: string };

const eventQuestions: EventQuestion[] = [
  {
    type: "education",
    title: "В каком году вы окончили основное обучение?",
    hint: "Подойдёт выпуск из вуза, колледжа или завершение важной профессиональной подготовки.",
  },
  {
    type: "career",
    title: "Когда произошёл самый заметный карьерный поворот?",
    hint: "Выберите год первой устойчивой работы, крупного повышения или смены профессии.",
  },
  {
    type: "marriage",
    title: "В каком году начался официальный брак?",
    hint: "Если браков было несколько, укажите первый. Незарегистрированные отношения здесь не учитываются.",
  },
  {
    type: "childbirth",
    title: "В каком году родился первый ребёнок?",
    hint: "Если детей нет или вы не хотите отвечать, выберите соответствующий вариант.",
  },
  {
    type: "relocation",
    title: "Когда состоялся самый значимый переезд?",
    hint: "Подойдёт переезд в другой город или страну, который заметно изменил повседневную жизнь.",
  },
  {
    type: "property",
    title: "Когда вы впервые приобрели крупную недвижимость?",
    hint: "Укажите покупку квартиры, дома или участка. Аренду и переезд к родственникам не учитывайте.",
  },
  {
    type: "accident",
    title: "Когда произошла крупная операция или серьёзная травма?",
    hint: "Вопрос можно пропустить. Медицинские подробности сервис не запрашивает.",
  },
];

const windowOptions = [
  { value: "night", label: "Ночью", detail: "00:00–05:59" },
  { value: "morning", label: "Утром", detail: "06:00–11:59" },
  { value: "day", label: "Днём", detail: "12:00–17:59" },
  { value: "evening", label: "Вечером", detail: "18:00–23:59" },
  { value: "unknown", label: "Совсем неизвестно", detail: "Проверить все сутки" },
] as const;

const monthOptions = [
  "Январь",
  "Февраль",
  "Март",
  "Апрель",
  "Май",
  "Июнь",
  "Июль",
  "Август",
  "Сентябрь",
  "Октябрь",
  "Ноябрь",
  "Декабрь",
];

function clearPaymentReturnQuery() {
  const params = new URLSearchParams(window.location.search);
  params.delete("payment_return");
  const search = params.toString();
  window.history.replaceState({}, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
}

export function RectificationFlow({ chartId, onNavigate }: RectificationFlowProps) {
  const [resource, setResource] = useState<RectificationResource | null>(null);
  const [loadingMessage, setLoadingMessage] = useState("Проверяем доступ к опросу");
  const [accessError, setAccessError] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [stepIndex, setStepIndex] = useState(0);
  const [answerError, setAnswerError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => applySeo({
    title: "Восстановление времени рождения | VedicWay",
    description: "Закрытый опрос для оплаченной ректификации времени рождения.",
    path: `/rectification/${encodeURIComponent(chartId)}`,
    noindex: true,
  }), [chartId]);

  useEffect(() => {
    const controller = new AbortController();
    async function openFlow() {
      const hasReturn = new URLSearchParams(window.location.search).has("payment_return");
      if (hasReturn) {
        const saved = readPaymentReturnState(window.sessionStorage, chartId, window.location.search);
        if (saved) {
          setLoadingMessage("Проверяем платёж по данным YooKassa");
          const payment = await pollPurchase(saved.purchaseId, { signal: controller.signal });
          if (payment.outcome === "aborted") return;
          if (
            payment.outcome !== "succeeded"
            || payment.purchase.chart_id !== chartId
            || payment.purchase.product_code !== "birth_time_rectification_v1"
          ) {
            setAccessError(
              payment.outcome === "cancelled"
                ? "Оплата отменена. Опрос остался закрыт."
                : "YooKassa пока не подтвердила оплату этой услуги.",
            );
            return;
          }
          clearPaymentReturnState(window.sessionStorage);
          clearPaymentReturnQuery();
        }
      }
      setLoadingMessage("Открываем персональный опрос");
      setResource(await getRectification(chartId, controller.signal));
    }
    void openFlow().catch((error) => {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && error.status === 402) {
        setAccessError("Сервер не подтвердил оплату ректификации. Перейдите к услуге из главной формы.");
      } else {
        setAccessError(error instanceof Error ? error.message : "Не удалось открыть опрос.");
      }
    });
    return () => controller.abort();
  }, [chartId]);

  useEffect(() => {
    if (!resource || !["queued", "running"].includes(resource.status)) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      void getRectification(chartId, controller.signal)
        .then(setResource)
        .catch(() => undefined);
    }, 1200);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [chartId, resource]);

  const birthYear = resource ? Number(resource.birth_date.slice(0, 4)) : new Date().getFullYear();
  const years = useMemo(() => {
    const current = new Date().getFullYear();
    return Array.from({ length: Math.max(1, current - birthYear + 1) }, (_, index) => current - index);
  }, [birthYear]);

  const steps = useMemo<Step[]>(() => {
    const items: Step[] = [{
      key: "time_window",
      kind: "window",
      title: "Что близкие говорили о времени вашего рождения?",
      hint: "Даже примерная часть суток сокращает перебор и делает результат устойчивее.",
    }];
    for (const event of eventQuestions) {
      const yearKey = `${event.type}.year`;
      items.push({ key: yearKey, kind: "year", event, title: event.title, hint: event.hint });
      if (/^\d{4}$/.test(answers[yearKey] ?? "")) {
        items.push({
          key: `${event.type}.month`,
          kind: "month",
          event,
          title: "В каком месяце это произошло?",
          hint: "Если месяц не сохранился в памяти, расчёт учтёт только год с меньшим весом.",
        });
      }
    }
    return items;
  }, [answers]);

  const step = steps[Math.min(stepIndex, steps.length - 1)];
  const selectedAnswer = step ? answers[step.key] ?? "" : "";

  function selectAnswer(value: string) {
    setAnswers((current) => ({ ...current, [step.key]: value }));
    setAnswerError("");
  }

  async function nextStep() {
    if (!selectedAnswer) {
      setAnswerError("Выберите один вариант ответа");
      return;
    }
    if (stepIndex < steps.length - 1) {
      setStepIndex((current) => current + 1);
      setAnswerError("");
      return;
    }
    const events = eventQuestions.flatMap((event) => {
      const rawYear = answers[`${event.type}.year`];
      if (!/^\d{4}$/.test(rawYear ?? "")) return [];
      const rawMonth = answers[`${event.type}.month`];
      return [{
        eventType: event.type,
        year: Number(rawYear),
        month: /^\d{1,2}$/.test(rawMonth ?? "") ? Number(rawMonth) : null,
      }];
    });
    if (events.length < 3) {
      setAnswerError("Для расчёта нужны даты минимум трёх событий. Вернитесь и добавьте ответы.");
      return;
    }
    setSubmitting(true);
    setAnswerError("");
    try {
      const next = await submitRectification(chartId, {
        timeWindow: answers.time_window as "unknown" | "night" | "morning" | "day" | "evening",
        events,
      });
      setResource(next);
    } catch (error) {
      setAnswerError(error instanceof Error ? error.message : "Не удалось запустить расчёт.");
      setSubmitting(false);
    }
  }

  function previousStep() {
    setStepIndex((current) => Math.max(0, current - 1));
    setAnswerError("");
  }

  async function copyTime() {
    if (!resource?.result) return;
    await navigator.clipboard.writeText(resource.result.selected_time);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  let content;
  if (accessError) {
    content = (
      <section className="rectification-state rectification-state--locked">
        <LockKeyhole aria-hidden="true" />
        <span>ДОСТУП ЗАКРЫТ</span>
        <h1>Опрос доступен только после оплаты</h1>
        <p>{accessError}</p>
        <button type="button" className="rectification-primary" onClick={() => onNavigate("/")}>
          Вернуться на главную
        </button>
      </section>
    );
  } else if (!resource) {
    content = (
      <section className="rectification-state">
        <LoaderCircle className="rectification-spinner" aria-hidden="true" />
        <span>ЗАЩИЩЁННЫЙ ДОСТУП</span>
        <h1>{loadingMessage}</h1>
        <p>Страница откроется после серверной проверки заказа.</p>
      </section>
    );
  } else if (["queued", "running"].includes(resource.status)) {
    content = <CalculationLoader variant="rectification" className="rectification-calculation-loader" />;
  } else if (resource.status === "ready" && resource.result) {
    const result = resource.result;
    content = (
      <section className="rectification-result">
        <header>
          <span>НАИБОЛЕЕ СОГЛАСОВАННОЕ ВРЕМЯ</span>
          <div className="rectification-result__time">{result.selected_time}</div>
          <p>
            Диапазон уверенности ±{result.uncertainty_minutes} минут · лагна {result.lagna}
          </p>
        </header>
        <div className="rectification-result__metrics">
          <article><strong>{result.score_percent}%</strong><span>совпадение правил</span></article>
          <article><strong>{result.candidate_count_scored}</strong><span>вариантов проверено</span></article>
          <article>
            <strong>{result.confidence === "medium" ? "Средняя" : "Низкая"}</strong>
            <span>уверенность результата</span>
          </article>
        </div>
        <div className="rectification-result__validation">
          <Check aria-hidden="true" />
          <p>
            Контрольное событие {result.holdout_supported ? "поддержало выбранный вариант" : "не дало сильного подтверждения"}.
            Для основной оценки использованы {result.fit_event_count} события.
          </p>
        </div>
        {result.alternatives.length > 0 && (
          <div className="rectification-alternatives">
            <h2>Ближайшие альтернативы</h2>
            {result.alternatives.map((alternative) => (
              <div key={alternative.time}>
                <strong>{alternative.time}</strong>
                <span>{alternative.lagna}</span>
                <small>{alternative.score_percent}%</small>
              </div>
            ))}
          </div>
        )}
        <p className="rectification-disclaimer">{result.disclaimer}</p>
        <footer>
          <button type="button" className="rectification-primary" onClick={copyTime}>
            <Copy aria-hidden="true" /> {copied ? "Время скопировано" : "Скопировать время"}
          </button>
          <button type="button" className="rectification-secondary" onClick={() => onNavigate("/")}>
            Вернуться к форме карты
          </button>
        </footer>
      </section>
    );
  } else {
    content = (
      <section className="rectification-question" aria-labelledby="rectification-question-title">
        <header className="rectification-question__top">
          <div>
            <span>РЕКТИФИКАЦИЯ</span>
            <p>{resource.birth_date} · {resource.birth_place}</p>
          </div>
          <strong>{String(stepIndex + 1).padStart(2, "0")} / {String(steps.length).padStart(2, "0")}</strong>
        </header>
        <div className="rectification-progress" aria-hidden="true">
          <span style={{ width: `${((stepIndex + 1) / steps.length) * 100}%` }} />
        </div>
        <div className="rectification-question__body">
          <span>ОДИН ВАРИАНТ ОТВЕТА</span>
          <h1 id="rectification-question-title">{step.title}</h1>
          <p>{step.hint}</p>

          {step.kind === "window" ? (
            <div className="rectification-options" role="radiogroup" aria-label={step.title}>
              {windowOptions.map((option) => (
                <label key={option.value} className={selectedAnswer === option.value ? "is-selected" : ""}>
                  <input
                    type="radio"
                    name={step.key}
                    value={option.value}
                    checked={selectedAnswer === option.value}
                    onChange={() => selectAnswer(option.value)}
                  />
                  <span><strong>{option.label}</strong><small>{option.detail}</small></span>
                </label>
              ))}
            </div>
          ) : (
            <label className="rectification-select">
              <span>{step.kind === "year" ? "Выберите год" : "Выберите месяц"}</span>
              <select
                value={selectedAnswer}
                onChange={(event) => selectAnswer(event.target.value)}
                aria-label={step.kind === "year" ? "Год события" : "Месяц события"}
              >
                <option value="">Выберите вариант</option>
                {step.kind === "year" ? (
                  <>
                    {years.map((year) => <option key={year} value={year}>{year}</option>)}
                    <option value="not_happened">Такого события не было</option>
                    <option value="unknown">Не помню год</option>
                    <option value="skip">Не хочу отвечать</option>
                  </>
                ) : (
                  <>
                    {monthOptions.map((month, index) => (
                      <option key={month} value={index + 1}>{month}</option>
                    ))}
                    <option value="unknown">Не помню месяц</option>
                  </>
                )}
              </select>
            </label>
          )}
          {answerError && <p className="rectification-question__error" role="alert">{answerError}</p>}
        </div>
        <footer className="rectification-question__footer">
          <button type="button" className="rectification-secondary" onClick={previousStep} disabled={stepIndex === 0 || submitting}>
            <ChevronLeft aria-hidden="true" /> Назад
          </button>
          <button type="button" className="rectification-primary" onClick={() => void nextStep()} disabled={submitting}>
            {submitting ? "Запускаем расчёт" : stepIndex === steps.length - 1 ? "Рассчитать время" : "Далее"}
            {!submitting && <ChevronRight aria-hidden="true" />}
          </button>
        </footer>
      </section>
    );
  }

  return (
    <>
      <SiteHeader active="home" onNavigate={onNavigate} />
      <main className="rectification-page">
        <div className="rectification-page__sky" aria-hidden="true" />
        {content}
      </main>
    </>
  );
}

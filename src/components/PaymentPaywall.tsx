import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Check, LockKeyhole, X } from "lucide-react";

import type { PaymentPublicConfig } from "../lib/chart-api";


type PaymentPaywallProps = {
  title: string;
  summary: string;
  config: PaymentPublicConfig;
  evidence?: ReactNode;
  features?: string[];
  kicker?: string;
  closeLabel?: string;
  initialMessage?: string | null;
  onClose: () => void;
  onCheckout: (email: string) => Promise<void>;
};

const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function formatPrice(minor: number, currency: string) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(minor / 100);
}

export function PaymentPaywall({
  title,
  summary,
  config,
  evidence,
  features = [
    "Восемь подробных жизненных тем",
    "Общий синтез карты и двенадцать вопросов",
    "PDF с южноиндийской картой",
  ],
  kicker = "Продолжение вашей темы",
  closeLabel = "Вернуться к карте",
  initialMessage,
  onClose,
  onCheckout,
}: PaymentPaywallProps) {
  const [email, setEmail] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [state, setState] = useState<"idle" | "pending" | "error">("idle");
  const [message, setMessage] = useState(initialMessage ?? "");
  const [emailError, setEmailError] = useState("");
  const [offerError, setOfferError] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const pendingRef = useRef(false);
  pendingRef.current = state === "pending";

  useEffect(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    titleRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      const dialog = dialogRef.current;
      if (event.key === "Escape" && !pendingRef.current) {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const controls = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          "button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex='-1'])",
        ),
      );
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus.current?.focus();
    };
  }, [onClose]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state === "pending") return;
    const normalizedEmail = email.trim();
    const nextEmailError = !normalizedEmail
      ? "Укажите email для чека"
      : !EMAIL_SHAPE.test(normalizedEmail)
        ? "Проверьте адрес email"
        : "";
    const nextOfferError = accepted ? "" : "Подтвердите оферту перед оплатой";
    setEmailError(nextEmailError);
    setOfferError(nextOfferError);
    if (nextEmailError || nextOfferError) return;

    setState("pending");
    setMessage("Создаём защищённый платёж в YooKassa");
    try {
      await onCheckout(normalizedEmail);
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Не удалось открыть оплату. Повторите запрос.");
    }
  }

  const buttonLabel = state === "pending"
    ? "Создаём платёж…"
    : state === "error"
      ? "Повторить оплату"
      : `Перейти к оплате ${formatPrice(config.price_minor, config.currency)}`;

  return (
    <div
      className="workspace-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && state !== "pending") onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="workspace-modal workspace-modal--paywall"
        role="dialog"
        aria-modal="true"
        aria-labelledby="paywall-title"
      >
        <header className="workspace-modal__header">
          <div>
            <span className="workspace-modal__kicker">{kicker}</span>
            <h2 ref={titleRef} id="paywall-title" tabIndex={-1}>{title}</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label={closeLabel}
            disabled={state === "pending"}
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </button>
        </header>

        <form onSubmit={submit} noValidate>
          <div className="paywall__body">
            <p>{summary}</p>
            {evidence}
            <ul className="paywall__list">
              {features.map((feature) => (
                <li key={feature}><Check aria-hidden="true" /> {feature}</li>
              ))}
            </ul>
            <div className="paywall__price">
              <strong>{formatPrice(config.price_minor, config.currency)}</strong>
              <span>Один платёж. Без подписки и сохранения карты.</span>
            </div>

            <label className="paywall-field">
              <span>Email для чека</span>
              <input
                type="email"
                inputMode="email"
                autoComplete="email"
                value={email}
                disabled={state === "pending"}
                aria-invalid={Boolean(emailError)}
                aria-describedby={emailError ? "paywall-email-error" : undefined}
                onChange={(event) => {
                  setEmail(event.target.value);
                  if (emailError) setEmailError("");
                }}
              />
            </label>
            {emailError && <p id="paywall-email-error" className="paywall-field__error">{emailError}</p>}

            <label className="paywall-consent">
              <input
                type="checkbox"
                checked={accepted}
                disabled={state === "pending"}
                aria-invalid={Boolean(offerError)}
                aria-describedby={offerError ? "paywall-offer-error" : undefined}
                onChange={(event) => {
                  setAccepted(event.target.checked);
                  if (offerError) setOfferError("");
                }}
              />
              <span>
                Принимаю <a href={config.offer_url} target="_blank" rel="noreferrer">условия оферты</a>
                {" "}и ознакомлен с <a href={config.privacy_url} target="_blank" rel="noreferrer">политикой обработки данных</a>
              </span>
            </label>
            {offerError && <p id="paywall-offer-error" className="paywall-field__error">{offerError}</p>}

            <p className="paywall-security"><LockKeyhole aria-hidden="true" /> Реквизиты карты вводятся только на стороне YooKassa.</p>
            {message && (
              <p
                className={state === "error" ? "workspace-notice workspace-notice--error" : "paywall__status"}
                role={state === "error" ? "alert" : "status"}
              >
                {message}
              </p>
            )}
          </div>
          <footer className="workspace-modal__footer workspace-modal__footer--purchase">
            <button type="submit" className="primary-button" disabled={state === "pending"}>{buttonLabel}</button>
            <span>После нажатия откроется защищённая страница YooKassa</span>
          </footer>
        </form>
      </div>
    </div>
  );
}

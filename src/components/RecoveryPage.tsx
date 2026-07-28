import { type FormEvent, useEffect, useState } from "react";
import { ArrowLeft, ShieldCheck } from "lucide-react";

import { applySeo } from "../lib/seo";
import { SiteHeader } from "./SiteHeader";

type RecoveryPageProps = {
  kind: "privacy" | "confirm";
  onNavigate: (path: string) => void;
};

type PrivacyRequestType = "access" | "erase" | "withdraw";

function confirmationCsrfToken(): string {
  if (typeof document === "undefined") return "";
  for (const name of ["__Host-vedicway-magic-csrf", "vw_magic_csrf"]) {
    const prefix = `${name}=`;
    const value = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(prefix));
    if (value) return decodeURIComponent(value.slice(prefix.length));
  }
  return "";
}

export function RecoveryPage({ kind, onNavigate }: RecoveryPageProps) {
  const [email, setEmail] = useState("");
  const [privacyType, setPrivacyType] = useState<PrivacyRequestType>("access");
  const [state, setState] = useState<"idle" | "sending" | "accepted" | "error">("idle");

  const confirmation = kind === "confirm";
  useEffect(() => applySeo({
    title: `${confirmation ? "Подтверждение доступа" : "Запрос по персональным данным"} | VedicWay`,
    description: confirmation
      ? "Подтверждение одноразовой ссылки на материалы VedicWay."
      : "Обращение по доступу, удалению или отзыву согласия на обработку персональных данных.",
    path: confirmation ? "/access/confirm" : "/privacy/request",
    noindex: true,
  }), [confirmation]);

  useEffect(() => {
    if (!confirmation) return undefined;
    let meta = document.querySelector<HTMLMetaElement>('meta[name="referrer"]');
    const created = !meta;
    const previous = meta?.content;
    if (!meta) {
      meta = document.createElement("meta");
      meta.name = "referrer";
      document.head.append(meta);
    }
    meta.content = "no-referrer";
    return () => {
      if (created) meta?.remove();
      else if (meta && previous) meta.content = previous;
    };
  }, [confirmation]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("sending");
    try {
      const response = await fetch("/api/v1/privacy/requests", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: privacyType, email }),
        });
      if (!response.ok) throw new Error("request failed");
      setState("accepted");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="recovery-site">
      <SiteHeader active={null} onNavigate={onNavigate} />
      <main className="recovery-page">
        <button className="recovery-back" type="button" onClick={() => onNavigate("/")}>
          <ArrowLeft aria-hidden="true" /> На главную
        </button>
        <section className="recovery-card" aria-labelledby="recovery-title">
          <span className="recovery-kicker">
            <ShieldCheck aria-hidden="true" />
            {confirmation ? "Одноразовая ссылка" : "Персональные данные"}
          </span>
          <h1 id="recovery-title">
            {confirmation ? "Подтвердить доступ" : "Отправить обращение"}
          </h1>
          <p>
            {confirmation
              ? "Ссылка проверена. Нажмите кнопку, чтобы открыть материалы в этом браузере."
              : "Укажите email и предмет обращения. Сотрудник сверит право на данные перед исполнением запроса."}
          </p>

          {confirmation ? (
            <form className="recovery-form" action="/api/v1/magic-links/confirm" method="post">
              <input type="hidden" name="csrf_token" value={confirmationCsrfToken()} />
              <button type="submit">Открыть материалы</button>
            </form>
          ) : state === "accepted" ? (
            <div className="recovery-result" role="status">
              Обращение принято. Ответ придёт на указанный адрес после проверки личности заявителя.
            </div>
          ) : (
            <form className="recovery-form" onSubmit={submit}>
              <label>
                Предмет обращения
                <select
                  value={privacyType}
                  onChange={(event) => setPrivacyType(event.target.value as PrivacyRequestType)}
                >
                  <option value="access">Получить сведения о данных</option>
                  <option value="erase">Удалить персональные данные</option>
                  <option value="withdraw">Отозвать согласие</option>
                </select>
              </label>
              <label>
                Email
                <input
                  type="email"
                  name="email"
                  autoComplete="email"
                  required
                  maxLength={320}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="name@example.ru"
                />
              </label>
              <button type="submit" disabled={state === "sending"}>
                {state === "sending" ? "Отправляем..." : "Отправить запрос"}
              </button>
              {state === "error" && (
                <p className="recovery-error" role="alert">
                  Не удалось отправить запрос. Проверьте соединение и повторите.
                </p>
              )}
            </form>
          )}
        </section>
      </main>
    </div>
  );
}

import { type FormEvent, useEffect, useState } from "react";
import { ArrowLeft, Mail, ShieldCheck } from "lucide-react";

import { applySeo } from "../lib/seo";
import { SiteHeader } from "./SiteHeader";

type RecoveryPageProps = {
  kind: "access" | "privacy";
  onNavigate: (path: string) => void;
};

type PrivacyRequestType = "access" | "erase" | "withdraw";

export function RecoveryPage({ kind, onNavigate }: RecoveryPageProps) {
  const [email, setEmail] = useState("");
  const [privacyType, setPrivacyType] = useState<PrivacyRequestType>("access");
  const [state, setState] = useState<"idle" | "sending" | "accepted" | "error">("idle");

  const access = kind === "access";
  useEffect(() => applySeo({
    title: `${access ? "Восстановление доступа" : "Запрос по персональным данным"} | VedicWay`,
    description: access
      ? "Запрос одноразовой ссылки на оплаченные материалы VedicWay."
      : "Обращение по доступу, удалению или отзыву согласия на обработку персональных данных.",
    path: access ? "/access/recovery" : "/privacy/request",
    noindex: true,
  }), [access]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("sending");
    try {
      const response = await fetch(
        access ? "/api/v1/access/recovery" : "/api/v1/privacy/requests",
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(access ? { email } : { type: privacyType, email }),
        },
      );
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
            {access ? <Mail aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
            {access ? "Оплаченные материалы" : "Персональные данные"}
          </span>
          <h1 id="recovery-title">
            {access ? "Восстановить доступ" : "Отправить обращение"}
          </h1>
          <p>
            {access
              ? "Укажите email, использованный при оплате. Если с ним связан готовый разбор, мы отправим одноразовые ссылки на карту и PDF."
              : "Укажите email и предмет обращения. Сотрудник сверит право на данные перед исполнением запроса."}
          </p>

          {state === "accepted" ? (
            <div className="recovery-result" role="status">
              {access
                ? "Если заказ найден, письмо придёт на указанный адрес. Проверьте также папку со спамом."
                : "Обращение принято. Ответ придёт на указанный адрес после проверки личности заявителя."}
            </div>
          ) : (
            <form className="recovery-form" onSubmit={submit}>
              {!access && (
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
              )}
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

import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

type PublicLegalConfig = {
  operator_name: string;
  operator_address: string;
  inn: string;
  ogrn: string;
  privacy_email: string;
  configured: boolean;
};

const faqItems = [
  {
    id: "service",
    question: "Что такое натальная карта и как работает сервис VedicWay?",
    answer:
      "Натальная карта — схема положения небесных тел в момент рождения. VedicWay сопоставляет дату, точное время и координаты места с астрономическими эфемеридами, а затем применяет правила классической джйотиш-традиции. Вы получаете карту и ясное объяснение её ключевых положений.",
  },
  {
    id: "data",
    question: "Какие данные нужны для расчёта?",
    answer:
      "Нужны имя, дата, максимально точное время и город рождения. По городу сервис определяет координаты и исторический часовой пояс, а минуты рождения влияют на лагну и дома. Имя используется как подпись результата и не меняет сам астрономический расчёт.",
  },
  {
    id: "unknown-time",
    question: "Можно ли получить натальную карту без времени рождения?",
    answer:
      "Да, но результат будет ограниченным. Без времени рождения нельзя надёжно определить лагну, дома и показатели, чувствительные к минутам. VedicWay явно обозначит границы такого разбора и предложит уточнить исходные данные, вместо того чтобы выдавать предположение за точный расчёт.",
  },
  {
    id: "traditions",
    question: "Чем ведическая астрология отличается от западной?",
    answer:
      "VedicWay использует сидерический зодиак, айанамшу Lahiri, накшатры и дома от лагны. Западная традиция чаще опирается на тропический зодиак и другую систему аспектов. Поэтому одинаковые исходные данные могут дать разные названия знаков и разные акценты разбора.",
  },
  {
    id: "accuracy",
    question: "Насколько точен разбор?",
    answer:
      "Положения небесных тел рассчитываются с астрономической точностью, а надёжность домов зависит от времени рождения. Разбор описывает связи, склонности и периоды, которые стоит сопоставлять с жизненным контекстом. Он не обещает неизбежных событий и не заменяет личное решение.",
  },
] as const;

function Ornament({ position }: { position: "top" | "bottom" }) {
  return (
    <div className={`faq-ornament faq-ornament--${position}`} aria-hidden="true">
      <span />
      <img src="/assets/faq-divider-star.png" alt="" width="256" height="256" />
      <span />
    </div>
  );
}

export function FaqSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [legalConfig, setLegalConfig] = useState<PublicLegalConfig | null>(null);
  const [legalUnavailable, setLegalUnavailable] = useState(false);
  const activeItem = openIndex === null ? null : faqItems[openIndex];

  useEffect(() => {
    fetch("/api/v1/legal/config", { headers: { Accept: "application/json" } })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((value: PublicLegalConfig) => {
        if (!value.configured) throw new Error("legal config is incomplete");
        setLegalConfig(value);
      })
      .catch(() => setLegalUnavailable(true));
  }, []);

  return (
    <>
      <section
        className="faq-section"
        aria-labelledby="faq-title"
        data-od-id="faq-section"
      >
        <div className="faq-section__veil" aria-hidden="true" />

        <div className="faq-shell">
          <Ornament position="top" />

          <header className="faq-heading">
            <h2 id="faq-title">Часто задаваемые вопросы</h2>
            <p>
              Мы собрали ответы на самые важные вопросы, чтобы вы могли
              <br />
              лучше понять сервис перед тем, как воспользоваться им.
            </p>
          </header>

          <div
            className="faq-list"
            data-open-index={openIndex === null ? "none" : openIndex}
            data-testid="faq-list"
          >
            {faqItems.map((item, index) => {
              const isOpen = openIndex === index;
              const triggerId = `faq-trigger-${item.id}`;

              return (
                <article
                  className={`faq-item${isOpen ? " is-open" : ""}`}
                  key={item.id}
                  data-od-id={`faq-item-${item.id}`}
                >
                  <button
                    className="faq-item__trigger"
                    id={triggerId}
                    type="button"
                    aria-expanded={isOpen}
                    aria-controls="faq-answer-panel"
                    onClick={() => setOpenIndex((current) => (current === index ? null : index))}
                  >
                    <span className="faq-item__star" aria-hidden="true">
                      <img src="/assets/faq-item-star.png" alt="" width="256" height="256" />
                    </span>
                    <span className="faq-item__question">{item.question}</span>
                    <ChevronDown className="faq-item__chevron" aria-hidden="true" />
                  </button>
                </article>
              );
            })}
          </div>

          <div className={`faq-answer-stage${activeItem ? " is-visible" : ""}`} data-testid="faq-answer-stage">
            <div
              className="faq-answer-panel"
              id="faq-answer-panel"
              role="region"
              aria-live="polite"
              aria-labelledby={activeItem ? `faq-trigger-${activeItem.id}` : undefined}
              aria-hidden={!activeItem}
              key={activeItem?.id ?? "closed"}
            >
              {activeItem ? (
                <>
                  <span>Короткий ответ</span>
                  <p>{activeItem.answer}</p>
                </>
              ) : (
                <p className="faq-answer-panel__placeholder">Выберите вопрос, чтобы прочитать ответ.</p>
              )}
            </div>
          </div>

          <footer className="faq-footer">
            <Ornament position="bottom" />
            <p>
              Не нашли ответ? {legalConfig ? <a href={`mailto:${legalConfig.privacy_email}`}>Свяжитесь с нами <span aria-hidden="true">→</span></a> : <a href="/legal/privacy-policy">Контакты оператора <span aria-hidden="true">→</span></a>}
            </p>
          </footer>
        </div>
      </section>

      <footer className="faq-legal-footer" id="faq-legal">
        <div className="faq-legal-footer__inner">
          <div className="faq-legal-footer__brand">
            <div className="faq-legal-footer__brand-mark">
              <img src="/assets/brand-mark.png" alt="" width="34" height="34" />
              <span>VedicWay</span>
            </div>
            <p>Персональные натальные карты и понятные объяснения.</p>
          </div>

          <div className="faq-legal-footer__operator">
            <p className="faq-legal-footer__label">Реквизиты оператора</p>
            {legalConfig ? <>
              <p>{legalConfig.operator_name}</p>
              <p>ОГРН/ОГРНИП: {legalConfig.ogrn} · ИНН: {legalConfig.inn}</p>
              <p>Юридический адрес: {legalConfig.operator_address}</p>
              <p>Обращения по персональным данным: <a href={`mailto:${legalConfig.privacy_email}`}>{legalConfig.privacy_email}</a></p>
            </> : <p>{legalUnavailable ? "Реквизиты временно недоступны" : "Загружаем реквизиты…"}</p>}
          </div>

          <nav className="faq-legal-footer__links" aria-label="Правовая информация">
            <a href="/legal/user-agreement">Пользовательское соглашение</a>
            <a href="/legal/privacy-policy">Политика обработки персональных данных</a>
            <a href="/legal/personal-data-consent">Согласие на обработку персональных данных</a>
            <a href="/legal/cookies">Политика cookies</a>
            <a href="/privacy/request">Запрос по персональным данным</a>
            <button type="button" onClick={() => window.dispatchEvent(new Event("vedicway:open-cookie-settings"))}>Настроить cookies</button>
            {legalConfig ? <a href={`mailto:${legalConfig.privacy_email}`}>Контакты</a> : <a href="/legal/privacy-policy">Контакты</a>}
          </nav>

          <p className="faq-legal-footer__copyright">© 2026 VedicWay · Материал предназначен для самонаблюдения и знакомства с астрологической традицией.</p>
        </div>
      </footer>
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

const CONTACT_EMAIL = "vedciway-ru@yandex.ru";

export const faqItems = [
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
      "Нужны дата, максимально точное время и город рождения. По городу сервис определяет координаты и исторический часовой пояс, а минуты рождения влияют на лагну и дома.",
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
      <img src="/assets/faq-divider-star-light.png" alt="" width="256" height="256" />
      <span />
    </div>
  );
}

function ContactPopover({ label }: { label: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeWithEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeWithEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeWithEscape);
    };
  }, [open]);

  return (
    <span className="contact-popover" ref={root}>
      <button type="button" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
        {label}
      </button>
      {open && (
        <span className="contact-popover__panel" role="status">
          <strong>Напишите нам</strong>
          <span>По всем вопросам обращайтесь на почту:</span>
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
        </span>
      )}
    </span>
  );
}

export function FaqSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

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
              const answerId = `faq-answer-${item.id}`;

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
                    aria-controls={answerId}
                    onClick={() => setOpenIndex((current) => (current === index ? null : index))}
                  >
                    <span className="faq-item__star" aria-hidden="true">
                      <img src="/assets/faq-item-star-light.png" alt="" width="256" height="256" />
                    </span>
                    <span className="faq-item__question">{item.question}</span>
                    <ChevronDown className="faq-item__chevron" aria-hidden="true" />
                  </button>
                  {isOpen && (
                    <div
                      className="faq-item__answer"
                      id={answerId}
                      role="region"
                      aria-labelledby={triggerId}
                    >
                      <div className="faq-item__answer-inner">
                        <span>Короткий ответ</span>
                        <p>{item.answer}</p>
                      </div>
                    </div>
                  )}
                </article>
              );
            })}
          </div>

          <footer className="faq-footer">
            <Ornament position="bottom" />
            <div className="faq-footer__contact-line">
              Не нашли ответ? <ContactPopover label="Свяжитесь с нами →" />
            </div>
          </footer>
        </div>
      </section>

      <footer className="faq-legal-footer" id="faq-legal">
        <div className="faq-legal-footer__inner">
          <div className="faq-legal-footer__brand">
            <div className="faq-legal-footer__brand-mark">
              <img src="/assets/brand-mark-light-80.webp" alt="" width="34" height="34" />
              <span>VedicWay</span>
            </div>
            <p>Персональные натальные карты и понятные объяснения.</p>
          </div>

          <nav className="faq-legal-footer__sections" aria-label="Разделы сайта">
            <span>Разделы сайта</span>
            <a href="/blog">Блог</a>
            <a href="/methodology">Метод</a>
          </nav>

          <nav className="faq-legal-footer__links" aria-label="Правовая информация">
            <a href="/legal/offer">Публичная оферта</a>
            <a href="/legal/privacy">Политика обработки персональных данных</a>
            <a href="/legal/personal-data-consent">Согласие на обработку персональных данных</a>
            <a href="/legal/cookies">Политика cookies</a>
            <a href="/privacy/request">Запрос по персональным данным</a>
            <button type="button" onClick={() => window.dispatchEvent(new Event("vedicway:open-cookie-settings"))}>Настроить cookies</button>
            <ContactPopover label="Контакты" />
          </nav>

          <p className="faq-legal-footer__copyright">© 2026 VedicWay · Материал предназначен для самонаблюдения и знакомства с астрологической традицией.</p>
        </div>
      </footer>
    </>
  );
}

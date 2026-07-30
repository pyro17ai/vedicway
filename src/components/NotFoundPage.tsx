import { useEffect } from "react";
import { ArrowLeft } from "lucide-react";

import { applySeo } from "../lib/seo";
import { SiteHeader } from "./SiteHeader";

type NotFoundPageProps = {
  onNavigate: (path: string) => void;
};

export function NotFoundPage({ onNavigate }: NotFoundPageProps) {
  useEffect(() => applySeo({
    title: "Страница не найдена | VedicWay",
    description: "Запрошенная страница VedicWay не найдена.",
    path: window.location.pathname,
    noindex: true,
  }), []);

  return (
    <div className="guide-site">
      <SiteHeader active="home" onNavigate={onNavigate} />
      <main className="article-page">
        <section className="article-state article-state--missing" aria-labelledby="not-found-title">
          <span aria-hidden="true">404</span>
          <h1 id="not-found-title">Страница не найдена</h1>
          <p>Адрес мог измениться или в ссылке есть ошибка.</p>
          <button type="button" onClick={() => onNavigate("/")}>
            <ArrowLeft aria-hidden="true" /> Вернуться на главную
          </button>
        </section>
      </main>
    </div>
  );
}

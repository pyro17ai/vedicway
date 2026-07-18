import type { MouseEvent } from "react";

type SiteHeaderProps = {
  active: "home" | "guide";
  onNavigate: (path: string) => void;
  variant?: "overlay" | "solid";
};

function isPlainLeftClick(event: MouseEvent<HTMLAnchorElement>) {
  return event.button === 0
    && !event.metaKey
    && !event.ctrlKey
    && !event.shiftKey
    && !event.altKey;
}

export function SiteHeader({ active, onNavigate, variant = "solid" }: SiteHeaderProps) {
  const follow = (event: MouseEvent<HTMLAnchorElement>, path: string) => {
    if (!isPlainLeftClick(event)) return;
    event.preventDefault();
    onNavigate(path);
  };

  return (
    <header className={`site-header site-header--${variant}`} data-od-id="site-header">
      <div className="site-header__inner">
        <a className="site-header__brand" href="/" onClick={(event) => follow(event, "/")} aria-label="VedicWay, главная">
          <img className="site-header__brand-mark" src="/assets/brand-mark.png" alt="" width="40" height="40" />
          <span>VedicWay</span>
        </a>

        <nav className="site-header__nav" aria-label="Основная навигация">
          <a className={active === "home" ? "is-active" : ""} href="/" aria-current={active === "home" ? "page" : undefined} onClick={(event) => follow(event, "/")}>
            Главная
          </a>
          <a className={active === "guide" ? "is-active" : ""} href="/guide" aria-current={active === "guide" ? "page" : undefined} onClick={(event) => follow(event, "/guide")}>
            Гид по астрологии
          </a>
        </nav>
      </div>
    </header>
  );
}

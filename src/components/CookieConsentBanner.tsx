import { useEffect, useState } from "react";
import { Cookie, Settings2, X } from "lucide-react";

import { applyAnalyticsPreference, readCookiePreferences, writeCookiePreferences } from "../lib/legal";

export function CookieConsentBanner() {
  const [visible, setVisible] = useState(() => readCookiePreferences() === null);
  const [settings, setSettings] = useState(false);
  const [analytics, setAnalytics] = useState(() => readCookiePreferences()?.analytics ?? false);

  useEffect(() => {
    const preferences = readCookiePreferences();
    if (preferences) applyAnalyticsPreference(preferences.analytics);
    const reopen = () => {
      setAnalytics(readCookiePreferences()?.analytics ?? false);
      setSettings(true);
      setVisible(true);
    };
    window.addEventListener("vedicway:open-cookie-settings", reopen);
    return () => window.removeEventListener("vedicway:open-cookie-settings", reopen);
  }, []);

  const save = (allowAnalytics: boolean) => {
    writeCookiePreferences(allowAnalytics);
    applyAnalyticsPreference(allowAnalytics);
    setAnalytics(allowAnalytics);
    setVisible(false);
    setSettings(false);
  };

  if (!visible) return null;

  return (
    <aside
      className="cookie-consent"
      role="dialog"
      aria-labelledby="cookie-title"
      onKeyDown={(event) => {
        if (event.key === "Escape") save(false);
      }}
    >
      <button className="cookie-consent__close" type="button" aria-label="Отклонить необязательные cookies" onClick={() => save(false)}><X /></button>
      <div className="cookie-consent__icon" aria-hidden="true"><Cookie /></div>
      <div className="cookie-consent__copy">
        <h2 id="cookie-title">Настройки cookies</h2>
        <p>Технические cookies нужны для работы расчёта и безопасной сессии. Яндекс.Метрика загрузится только после вашего согласия на аналитические cookies. <a href="/legal/cookies">Подробнее</a></p>
        {settings && (
          <div className="cookie-consent__settings">
            <label><span><strong>Необходимые</strong><small>Сессия, безопасность и сохранение выбора</small></span><input type="checkbox" checked disabled /></label>
            <label><span><strong>Аналитические</strong><small>Яндекс.Метрика, без рекламной персонализации</small></span><input type="checkbox" checked={analytics} onChange={(event) => setAnalytics(event.target.checked)} /></label>
          </div>
        )}
      </div>
      <div className="cookie-consent__actions">
        {settings ? (
          <button className="cookie-consent__primary" type="button" onClick={() => save(analytics)}>Сохранить выбор</button>
        ) : (
          <button type="button" onClick={() => setSettings(true)}><Settings2 /> Настроить</button>
        )}
        <button type="button" onClick={() => save(false)}>Отклонить необязательные</button>
        <button className="cookie-consent__primary" type="button" onClick={() => save(true)}>Принять все</button>
      </div>
    </aside>
  );
}

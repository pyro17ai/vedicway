import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowLeft,
  CalendarDays,
  Clock3,
  LoaderCircle,
  LockKeyhole,
  Mail,
  MapPin,
} from "lucide-react";

import { ApiError, createChart } from "../lib/chart-api";
import { trackWorkspaceEvent } from "../lib/analytics";
import { searchCities, type CityOption } from "../lib/city-search";

type FieldName = "birthDate" | "birthTime" | "birthPlace";

type FormValues = {
  birthDate: string;
  birthTime: string;
};

type Errors = Partial<Record<FieldName, string>>;
type SearchState = "idle" | "loading" | "ready" | "empty" | "error";

type BirthChartFormProps = {
  onChartCreated?: (chartId: string) => void;
  initialMode?: "calculate" | "recovery";
};

const initialValues: FormValues = {
  birthDate: "",
  birthTime: "",
};

const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function errorForField(
  field: FieldName,
  values: FormValues,
  selectedCity: CityOption | null,
) {
  if (field === "birthDate" && !values.birthDate) return "Укажите дату рождения";
  if (field === "birthDate" && values.birthDate > new Date().toISOString().slice(0, 10)) {
    return "Дата рождения должна быть в прошлом";
  }
  if (field === "birthTime" && !values.birthTime) return "Укажите время рождения";
  if (field === "birthPlace" && !selectedCity) return "Выберите город из списка";
  return "";
}

export function BirthChartForm({ onChartCreated, initialMode = "calculate" }: BirthChartFormProps) {
  const [values, setValues] = useState(initialValues);
  const [mode, setMode] = useState(initialMode);
  const [errors, setErrors] = useState<Errors>({});
  const [touched, setTouched] = useState<Partial<Record<FieldName, boolean>>>({});
  const [cityQuery, setCityQuery] = useState("");
  const [selectedCity, setSelectedCity] = useState<CityOption | null>(null);
  const [cityOptions, setCityOptions] = useState<CityOption[]>([]);
  const [searchState, setSearchState] = useState<SearchState>("idle");
  const [isCityOpen, setIsCityOpen] = useState(false);
  const [activeCityIndex, setActiveCityIndex] = useState(-1);
  const [retryNonce, setRetryNonce] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitMessage, setSubmitMessage] = useState("");
  const [timeAccuracy, setTimeAccuracy] = useState<"exact" | "approximate_15m" | "approximate_hour" | "unknown">("exact");
  const [personalDataConsent, setPersonalDataConsent] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [recoveryState, setRecoveryState] = useState<"idle" | "sending" | "accepted" | "error">("idle");
  const [recoveryError, setRecoveryError] = useState("");

  const birthDateRef = useRef<HTMLInputElement>(null);
  const birthTimeRef = useRef<HTMLInputElement>(null);
  const birthPlaceRef = useRef<HTMLInputElement>(null);

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  useEffect(() => {
    for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = window.sessionStorage.key(index);
      if (key?.startsWith("vedicway:profile:")) window.sessionStorage.removeItem(key);
    }
  }, []);

  useEffect(() => {
    const normalizedQuery = cityQuery.trim();

    if (selectedCity?.label === cityQuery) {
      setSearchState("idle");
      setCityOptions([]);
      return;
    }

    if (normalizedQuery.length < 2) {
      setSearchState("idle");
      setCityOptions([]);
      setIsCityOpen(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearchState("loading");
      setIsCityOpen(true);
      setActiveCityIndex(-1);

      try {
        const options = await searchCities(normalizedQuery, controller.signal);
        setCityOptions(options);
        setSearchState(options.length ? "ready" : "empty");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setCityOptions([]);
        setSearchState("error");
      }
    }, 350);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [cityQuery, retryNonce, selectedCity]);

  const refs: Record<FieldName, React.RefObject<HTMLInputElement | null>> = {
    birthDate: birthDateRef,
    birthTime: birthTimeRef,
    birthPlace: birthPlaceRef,
  };

  function validateField(field: FieldName) {
    const message = errorForField(field, values, selectedCity);
    setErrors((current) => ({ ...current, [field]: message || undefined }));
    return !message;
  }

  function handleBlur(field: FieldName) {
    setTouched((current) => ({ ...current, [field]: true }));
    validateField(field);
  }

  function updateValue(field: keyof FormValues, value: string) {
    const nextValues = { ...values, [field]: value };
    setValues(nextValues);

    if (touched[field]) {
      const message = errorForField(field, nextValues, selectedCity);
      setErrors((current) => ({ ...current, [field]: message || undefined }));
    }
  }

  function selectCity(city: CityOption) {
    setSelectedCity(city);
    setCityQuery(city.label);
    setCityOptions([]);
    setSearchState("idle");
    setIsCityOpen(false);
    setActiveCityIndex(-1);
    setErrors((current) => ({ ...current, birthPlace: undefined }));
  }

  function handleCityKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setIsCityOpen(false);
      return;
    }

    if (!cityOptions.length) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setIsCityOpen(true);
      setActiveCityIndex((current) => (current + 1) % cityOptions.length);
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setIsCityOpen(true);
      setActiveCityIndex((current) =>
        current <= 0 ? cityOptions.length - 1 : current - 1,
      );
    }

    if (event.key === "Enter" && activeCityIndex >= 0) {
      event.preventDefault();
      selectCity(cityOptions[activeCityIndex]);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitMessage("");

    const fields: FieldName[] = ["birthDate", "birthTime", "birthPlace"];
    const nextErrors = fields.reduce<Errors>((result, field) => {
      const message = errorForField(field, values, selectedCity);
      if (message) result[field] = message;
      return result;
    }, {});

    setTouched({ birthDate: true, birthTime: true, birthPlace: true });
    setErrors(nextErrors);

    const firstInvalid = fields.find((field) => nextErrors[field]);
    if (firstInvalid) {
      refs[firstInvalid].current?.focus();
      return;
    }

    if (!personalDataConsent || !termsAccepted) {
      setSubmitMessage("Подтвердите отдельное согласие и пользовательское соглашение.");
      return;
    }

    setIsSubmitting(true);
    setSubmitMessage("Проверяем данные");
    try {
      const result = await createChart({
        localDate: values.birthDate,
        localTime: values.birthTime,
        placeId: selectedCity!.id,
        place: {
          displayName: selectedCity!.label,
          countryCode: selectedCity!.countryCode,
          latitude: selectedCity!.latitude,
          longitude: selectedCity!.longitude,
          timezone: selectedCity!.timezone,
        },
        timeAccuracy,
        personalDataConsent,
        termsAccepted,
      });
      trackWorkspaceEvent("chart_create_accepted", { time_accuracy: timeAccuracy });
      setSubmitMessage("Карта принята. Переходим к расчёту.");
      onChartCreated?.(result.chart_id);
    } catch (error) {
      setIsSubmitting(false);
      setSubmitMessage(error instanceof ApiError ? error.message : "Не удалось отправить данные. Проверьте соединение и повторите.");
      trackWorkspaceEvent("chart_create_failed", { code: error instanceof ApiError ? error.code ?? "api" : "network" });
    }
  }

  async function handleRecoverySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (recoveryState === "sending") return;
    const normalizedEmail = recoveryEmail.trim();
    if (!normalizedEmail || !EMAIL_SHAPE.test(normalizedEmail)) {
      setRecoveryError("Проверьте адрес email");
      return;
    }
    setRecoveryError("");
    setRecoveryState("sending");
    try {
      const response = await fetch("/api/v1/access/recovery", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: normalizedEmail }),
      });
      if (!response.ok) throw new Error("request failed");
      setRecoveryEmail("");
      setRecoveryState("accepted");
      trackWorkspaceEvent("access_recovery_requested");
    } catch {
      setRecoveryState("error");
    }
  }

  function showRecovery() {
    setMode("recovery");
    setRecoveryState("idle");
    setRecoveryError("");
    setSubmitMessage("");
  }

  function showCalculation() {
    setMode("calculate");
    setRecoveryEmail("");
    setRecoveryState("idle");
    setRecoveryError("");
  }

  return (
    <aside
      className={`chart-card${mode === "recovery" ? " chart-card--recovery" : ""}`}
      aria-labelledby="chart-form-title"
      data-od-id="birth-chart-form"
    >
      <header className="chart-card__header">
        <h2 id="chart-form-title">
          {mode === "recovery" ? (
            <>Восстановить <span>оплаченный разбор</span></>
          ) : (
            <>Получите вашу <span>натальную карту</span></>
          )}
        </h2>
        <img className="chart-card__star" src="/assets/celestial-star-light.png" alt="" />
      </header>

      {mode === "recovery" ? (
        <form className="chart-form chart-form--recovery" onSubmit={handleRecoverySubmit} noValidate>
          <p className="chart-form__recovery-copy">
            Введите email, который использовали при оплате. Если по нему найден готовый разбор,
            мы отправим одноразовые ссылки на карту и PDF.
          </p>

          {recoveryState === "accepted" ? (
            <div className="chart-form__recovery-result" role="status">
              Если заказ найден, письмо с одноразовой ссылкой придёт на указанный адрес.
              Проверьте также папку со спамом.
            </div>
          ) : (
            <>
              <div className="field" data-invalid={Boolean(recoveryError) || undefined}>
                <label htmlFor="recoveryEmail">Email оплаты</label>
                <div className="input-shell input-shell--icon">
                  <input
                    id="recoveryEmail"
                    name="email"
                    type="email"
                    autoComplete="email"
                    inputMode="email"
                    maxLength={320}
                    placeholder="name@example.ru"
                    value={recoveryEmail}
                    onChange={(event) => {
                      setRecoveryEmail(event.target.value);
                      if (recoveryError) setRecoveryError("");
                    }}
                    aria-invalid={Boolean(recoveryError)}
                    aria-describedby={recoveryError ? "recovery-email-error" : undefined}
                    required
                  />
                  <Mail aria-hidden="true" />
                </div>
                {recoveryError && (
                  <span id="recovery-email-error" className="field-error" role="alert">
                    {recoveryError}
                  </span>
                )}
              </div>

              <button
                className="submit-button"
                type="submit"
                aria-label="Отправить одноразовую ссылку"
                disabled={recoveryState === "sending"}
              >
                <span>{recoveryState === "sending" ? "ОТПРАВЛЯЕМ..." : "ОТПРАВИТЬ ОДНОРАЗОВУЮ ССЫЛКУ"}</span>
                <span className="submit-button__star" aria-hidden="true">
                  <img src="/assets/celestial-star-light.png" alt="" />
                </span>
              </button>
            </>
          )}

          {recoveryState === "error" && (
            <p className="chart-form__recovery-error" role="alert">
              Не удалось отправить запрос. Проверьте соединение и повторите.
            </p>
          )}

          <button className="chart-form__back" type="button" onClick={showCalculation}>
            <ArrowLeft aria-hidden="true" />
            Вернуться к расчёту
          </button>

          <div className="privacy-note">
            <LockKeyhole aria-hidden="true" />
            <span>Email не сохраняется в браузере и используется только для поиска оплаченного заказа</span>
          </div>
        </form>
      ) : (
      <form className="chart-form" onSubmit={handleSubmit} noValidate>

        <div className="field" data-invalid={Boolean(errors.birthDate) || undefined}>
          <label htmlFor="birthDate">Дата рождения</label>
          <div className="input-shell input-shell--icon">
            <input
              ref={birthDateRef}
              id="birthDate"
              name="birthDate"
              type="date"
              lang="ru"
              min="1900-01-01"
              max={today}
              value={values.birthDate}
              onChange={(event) => updateValue("birthDate", event.target.value)}
              onBlur={() => handleBlur("birthDate")}
              aria-invalid={Boolean(errors.birthDate)}
              aria-describedby={errors.birthDate ? "birthDate-error" : undefined}
              required
            />
            <CalendarDays aria-hidden="true" />
          </div>
          {errors.birthDate && (
            <span id="birthDate-error" className="field-error" role="alert">
              {errors.birthDate}
            </span>
          )}
        </div>

        <div className="field" data-invalid={Boolean(errors.birthTime) || undefined}>
          <label htmlFor="birthTime">Время рождения</label>
          <div className="input-shell input-shell--icon">
            <input
              ref={birthTimeRef}
              id="birthTime"
              name="birthTime"
              type="time"
              step="60"
              value={values.birthTime}
              onChange={(event) => updateValue("birthTime", event.target.value)}
              onBlur={() => handleBlur("birthTime")}
              aria-invalid={Boolean(errors.birthTime)}
              aria-describedby={errors.birthTime ? "birthTime-error" : undefined}
              required
            />
            <Clock3 aria-hidden="true" />
          </div>
          {errors.birthTime && (
            <span id="birthTime-error" className="field-error" role="alert">
              {errors.birthTime}
            </span>
          )}
        </div>

        <div className="field field--city" data-invalid={Boolean(errors.birthPlace) || undefined}>
          <label htmlFor="birthPlace">Место рождения</label>
          <div className="input-shell input-shell--icon">
            <input
              ref={birthPlaceRef}
              id="birthPlace"
              name="birthPlace"
              type="text"
              role="combobox"
              autoComplete="off"
              placeholder="Введите город"
              value={cityQuery}
              onChange={(event) => {
                setCityQuery(event.target.value);
                setSelectedCity(null);
                setIsCityOpen(true);
                if (touched.birthPlace) {
                  setErrors((current) => ({
                    ...current,
                    birthPlace: "Выберите город из списка",
                  }));
                }
              }}
              onFocus={() => cityQuery.trim().length >= 2 && setIsCityOpen(true)}
              onBlur={() => {
                handleBlur("birthPlace");
                window.setTimeout(() => setIsCityOpen(false), 120);
              }}
              onKeyDown={handleCityKeyDown}
              aria-autocomplete="list"
              aria-controls="city-options"
              aria-expanded={isCityOpen}
              aria-activedescendant={
                activeCityIndex >= 0 ? `city-option-${activeCityIndex}` : undefined
              }
              aria-invalid={Boolean(errors.birthPlace)}
              aria-describedby={errors.birthPlace ? "birthPlace-error" : "birthPlace-hint"}
              required
            />
            <MapPin aria-hidden="true" />
          </div>

          <span id="birthPlace-hint" className="sr-only">
            Начните вводить город и выберите точный вариант из списка
          </span>

          {isCityOpen && searchState !== "idle" && (
            <div className="city-popover" id="city-options">
              {searchState === "loading" && (
                <div className="city-message" role="status">
                  <LoaderCircle className="city-spinner" aria-hidden="true" />
                  Ищем города по всему миру...
                </div>
              )}

              {searchState === "empty" && (
                <div className="city-message" role="status">
                  Ничего не найдено. Проверьте написание или введите ближайший крупный город.
                </div>
              )}

              {searchState === "error" && (
                <div className="city-message city-message--error" role="alert">
                  <span>Сервис городов недоступен. Введённый текст сохранён.</span>
                  <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => setRetryNonce((value) => value + 1)}>
                    Повторить
                  </button>
                </div>
              )}

              {searchState === "ready" && (
                <ul role="listbox" aria-label="Варианты городов">
                  {cityOptions.map((city, index) => (
                    <li
                      id={`city-option-${index}`}
                      key={city.id}
                      role="option"
                      aria-label={city.label}
                      aria-selected={activeCityIndex === index}
                      onMouseDown={(event) => event.preventDefault()}
                      onMouseEnter={() => setActiveCityIndex(index)}
                      onClick={() => selectCity(city)}
                    >
                      <span>{city.name}</span>
                      <small>{[city.admin1, city.country].filter(Boolean).join(", ")}</small>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {errors.birthPlace && (
            <span id="birthPlace-error" className="field-error" role="alert">
              {errors.birthPlace}
            </span>
          )}
        </div>

        <input type="hidden" name="latitude" value={selectedCity?.latitude ?? ""} />
        <input type="hidden" name="longitude" value={selectedCity?.longitude ?? ""} />
        <input type="hidden" name="timezone" value={selectedCity?.timezone ?? ""} />

        <fieldset className="time-accuracy" aria-describedby="time-accuracy-hint">
          <legend>Точность времени</legend>
          <div className="time-accuracy__choices">
            <label>
              <input type="radio" name="timeAccuracy" value="exact" checked={timeAccuracy === "exact"} onChange={() => setTimeAccuracy("exact")} />
              Точно
            </label>
            <label>
              <input type="radio" name="timeAccuracy" value="approximate_15m" checked={timeAccuracy === "approximate_15m"} onChange={() => setTimeAccuracy("approximate_15m")} />
              До 15 минут
            </label>
            <label>
              <input type="radio" name="timeAccuracy" value="approximate_hour" checked={timeAccuracy === "approximate_hour"} onChange={() => setTimeAccuracy("approximate_hour")} />
              Примерно
            </label>
          </div>
          <small id="time-accuracy-hint">Лагна, дома и дробные карты чувствительны к минутам рождения.</small>
        </fieldset>

        <div className="legal-acceptance" aria-label="Правовые согласия">
          <label>
            <input type="checkbox" checked={personalDataConsent} onChange={(event) => setPersonalDataConsent(event.target.checked)} required />
            <span>Даю отдельное <a href="/legal/personal-data-consent" target="_blank" rel="noreferrer">согласие на обработку персональных данных</a></span>
          </label>
          <label>
            <input type="checkbox" checked={termsAccepted} onChange={(event) => setTermsAccepted(event.target.checked)} required />
            <span>Принимаю <a href="/legal/user-agreement" target="_blank" rel="noreferrer">пользовательское соглашение</a></span>
          </label>
        </div>

        <button className="submit-button" type="submit" disabled={isSubmitting || !personalDataConsent || !termsAccepted}>
          <span>{isSubmitting ? "РАССЧИТЫВАЕМ..." : "РАССЧИТАТЬ КАРТУ"}</span>
          <span className="submit-button__star" aria-hidden="true">
            <img src="/assets/celestial-star-light.png" alt="" />
          </span>
        </button>

        <div className="privacy-note">
          <LockKeyhole aria-hidden="true" />
          <span>Используем данные только для расчёта карты и оказания сервиса</span>
        </div>

        <div className="submit-status" role="status" aria-live="polite">
          {submitMessage}
        </div>

        <div className="chart-form__switch">
          <span>Уже оплатили и хотите вернуться к готовой карте?</span>
          <button type="button" onClick={showRecovery}>
            Восстановить оплаченный разбор
          </button>
        </div>
      </form>
      )}
    </aside>
  );
}

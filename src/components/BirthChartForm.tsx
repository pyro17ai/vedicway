import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  CalendarDays,
  Clock3,
  LoaderCircle,
  LockKeyhole,
  MapPin,
} from "lucide-react";

import { ApiError, createChart } from "../lib/chart-api";
import { trackWorkspaceEvent } from "../lib/analytics";
import { searchCities, type CityOption } from "../lib/city-search";

type FieldName = "name" | "birthDate" | "birthTime" | "birthPlace";

type FormValues = {
  name: string;
  birthDate: string;
  birthTime: string;
};

type Errors = Partial<Record<FieldName, string>>;
type SearchState = "idle" | "loading" | "ready" | "empty" | "error";

type BirthChartFormProps = {
  onChartCreated?: (chartId: string) => void;
};

const initialValues: FormValues = {
  name: "",
  birthDate: "",
  birthTime: "",
};

function errorForField(
  field: FieldName,
  values: FormValues,
  selectedCity: CityOption | null,
) {
  if (field === "name" && !values.name.trim()) return "Введите имя";
  if (field === "birthDate" && !values.birthDate) return "Укажите дату рождения";
  if (field === "birthDate" && values.birthDate > new Date().toISOString().slice(0, 10)) {
    return "Дата рождения должна быть в прошлом";
  }
  if (field === "birthTime" && !values.birthTime) return "Укажите время рождения";
  if (field === "birthPlace" && !selectedCity) return "Выберите город из списка";
  return "";
}

export function BirthChartForm({ onChartCreated }: BirthChartFormProps) {
  const [values, setValues] = useState(initialValues);
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

  const nameRef = useRef<HTMLInputElement>(null);
  const birthDateRef = useRef<HTMLInputElement>(null);
  const birthTimeRef = useRef<HTMLInputElement>(null);
  const birthPlaceRef = useRef<HTMLInputElement>(null);

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

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
    name: nameRef,
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

    const fields: FieldName[] = ["name", "birthDate", "birthTime", "birthPlace"];
    const nextErrors = fields.reduce<Errors>((result, field) => {
      const message = errorForField(field, values, selectedCity);
      if (message) result[field] = message;
      return result;
    }, {});

    setTouched({ name: true, birthDate: true, birthTime: true, birthPlace: true });
    setErrors(nextErrors);

    const firstInvalid = fields.find((field) => nextErrors[field]);
    if (firstInvalid) {
      refs[firstInvalid].current?.focus();
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
      });
      window.sessionStorage.setItem(`vedicway:profile:${result.chart_id}`, JSON.stringify({ name: values.name.trim() }));
      trackWorkspaceEvent("chart_create_accepted", { time_accuracy: timeAccuracy });
      setSubmitMessage("Карта принята. Переходим к расчёту.");
      onChartCreated?.(result.chart_id);
    } catch (error) {
      setIsSubmitting(false);
      setSubmitMessage(error instanceof ApiError ? error.message : "Не удалось отправить данные. Проверьте соединение и повторите.");
      trackWorkspaceEvent("chart_create_failed", { code: error instanceof ApiError ? error.code ?? "api" : "network" });
    }
  }

  return (
    <aside
      className="chart-card"
      aria-labelledby="chart-form-title"
      data-od-id="birth-chart-form"
    >
      <header className="chart-card__header">
        <h2 id="chart-form-title">
          Получите вашу{" "}
          <span>натальную карту</span>
        </h2>
        <img className="chart-card__star" src="/assets/celestial-star.png" alt="" />
      </header>

      <form className="chart-form" onSubmit={handleSubmit} noValidate>
        <div className="field" data-invalid={Boolean(errors.name) || undefined}>
          <label htmlFor="name">Имя</label>
          <div className="input-shell">
            <input
              ref={nameRef}
              id="name"
              name="name"
              type="text"
              autoComplete="name"
              placeholder="Введите ваше имя"
              value={values.name}
              onChange={(event) => updateValue("name", event.target.value)}
              onBlur={() => handleBlur("name")}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? "name-error" : undefined}
              required
            />
          </div>
          {errors.name && (
            <span id="name-error" className="field-error" role="alert">
              {errors.name}
            </span>
          )}
        </div>

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

        <button className="submit-button" type="submit" disabled={isSubmitting}>
          <span>{isSubmitting ? "РАССЧИТЫВАЕМ..." : "РАССЧИТАТЬ КАРТУ"}</span>
          <span className="submit-button__star" aria-hidden="true">
            <img src="/assets/celestial-star.png" alt="" />
          </span>
        </button>

        <div className="privacy-note">
          <LockKeyhole aria-hidden="true" />
          <span>Ваши данные защищены и не передаются третьим лицам</span>
        </div>

        <div className="submit-status" role="status" aria-live="polite">
          {submitMessage}
        </div>
      </form>
    </aside>
  );
}

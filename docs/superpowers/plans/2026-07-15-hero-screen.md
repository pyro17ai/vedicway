# Первый экран VedicWay: план реализации

> **Для агентных исполнителей:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Цель:** собрать и проверить первый экран сервиса натальных карт по четырём визуальным референсам.

**Архитектура:** Vite обслуживает React SPA. Hero состоит из независимых слоёв: фоновой фотографии, программного SVG-круга, контентной колонки и формы. Поиск городов вынесен в чистый сервис, чтобы проверить URL, нормализацию ответа и отмену запросов без браузера.

**Стек:** React 19.2.7, TypeScript 7.0.2, Vite 8.1.4, GSAP 3.15.0, Vitest 4.1.10, Testing Library, Open-Meteo Geocoding API.

## Глобальные ограничения

- Публичный текст не содержит упоминаний искусственного интеллекта, Hermes и ведической астрологии.
- Растровый фон берётся из изображения 3; изображение 2 служит только целью композиции.
- Круг строится кодом и содержит только тонкие оранжевые линии.
- Дата открывает календарь, город ищется по всему миру, кнопка отправки кликабельна.
- Вращение отключается при `prefers-reduced-motion: reduce`.
- Каталог `.git` пуст, поэтому коммиты в этой рабочей копии недоступны.

---

### Задача 1: каркас и тестовый контур

**Файлы:**
- Создать: `package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `index.html`
- Создать: `src/main.tsx`, `src/test/setup.ts`

**Интерфейсы:**
- Produces: команды `npm run dev`, `npm test`, `npm run build`.
- Consumes: Node.js 24 и npm 11 из рабочей среды.

- [ ] Создать конфигурацию Vite и Vitest с окружением `jsdom` и setup-файлом `@testing-library/jest-dom/vitest`.
- [ ] Запустить `npm install`; ожидается завершение с кодом 0.
- [ ] Запустить `npm test -- --run`; ожидается сообщение об отсутствии тестов, пока RED-тесты не добавлены.

### Задача 2: поиск городов, цикл RED-GREEN

**Файлы:**
- Создать: `src/lib/city-search.test.ts`
- Создать: `src/lib/city-search.ts`

**Интерфейсы:**
- Produces: `searchCities(query: string, signal?: AbortSignal): Promise<CityOption[]>`.
- Produces: `CityOption` с полями `id`, `label`, `name`, `country`, `admin1`, `latitude`, `longitude`, `timezone`.

- [ ] Написать тест, который требует URL `https://geocoding-api.open-meteo.com/v1/search` с `name`, `count=6`, `language=ru`, `format=json`.
- [ ] Запустить `npm test -- --run src/lib/city-search.test.ts`; ожидается FAIL из-за отсутствующего модуля.
- [ ] Реализовать fetch, проверку `response.ok`, нормализацию отсутствующих полей и пустой выдачи.
- [ ] Повторить тест; ожидается PASS.

### Задача 3: программный астрологический круг, цикл RED-GREEN

**Файлы:**
- Создать: `src/components/AstrologyWheel.test.tsx`
- Создать: `src/components/AstrologyWheel.tsx`

**Интерфейсы:**
- Produces: `<AstrologyWheel />` с `data-testid="astrology-wheel"`, 12 основными спицами и без белых stroke/fill.

- [ ] Написать тест на 12 элементов `[data-spoke]`, декоративный `aria-hidden="true"` и отсутствие `#fff`, `white`, `rgb(255`.
- [ ] Запустить точечный тест; ожидается FAIL из-за отсутствующего компонента.
- [ ] Создать SVG из массивов радиусов и углов; линии используют `currentColor` и несколько уровней opacity.
- [ ] Подключить `useGSAP`, `gsap.matchMedia()` и вращение `rotation: 360`, `duration: 90`, `repeat: -1`, `ease: "none"` только при `no-preference`.
- [ ] Повторить тест; ожидается PASS.

### Задача 4: форма рождения, цикл RED-GREEN

**Файлы:**
- Создать: `src/components/BirthChartForm.test.tsx`
- Создать: `src/components/BirthChartForm.tsx`

**Интерфейсы:**
- Consumes: `searchCities` из `src/lib/city-search.ts`.
- Produces: доступная форма с полями `name`, `birthDate`, `birthTime`, `birthPlace` и локальным подтверждением успешного submit.

- [ ] Написать тест на четыре постоянные подписи, `type="date"`, `type="time"`, role `combobox`, кнопку `Рассчитать карту` и валидацию пустой формы.
- [ ] Добавить тест с fake timers: ввод `Москва`, вызов поиска после 350 мс, выбор варианта клавишами ArrowDown и Enter.
- [ ] Запустить точечный тест; ожидается FAIL из-за отсутствующего компонента.
- [ ] Реализовать controlled inputs, blur-валидацию, фокус первого ошибочного поля, debounced fetch с `AbortController` и состояния `loading`, `empty`, `error`, `populated`.
- [ ] Повторить тест; ожидается PASS.

### Задача 5: композиция hero и созданные изображения

**Файлы:**
- Создать: `src/App.test.tsx`, `src/App.tsx`, `src/styles.css`
- Создать: `public/assets/hero-space.png`, `public/assets/brand-mark.png`, `public/assets/celestial-star.png`
- Создать: `public/assets/avatar-01.png` ... `avatar-04.png`

**Интерфейсы:**
- Consumes: `<AstrologyWheel />`, `<BirthChartForm />` и все локальные изображения.
- Produces: адаптивный hero без публичных запрещённых терминов.

- [ ] Написать тест на главный слоган, форму, социальное доказательство и отсутствие строк `Hermes`, `искусственн`, `ведическ`.
- [ ] Запустить тест; ожидается FAIL из-за отсутствующего `App.tsx`.
- [ ] Скопировать третий референс как фон. Сгенерировать оригинальную марку, одну звезду и четыре портрета встроенным ImageGen; поместить итоговые файлы в `public/assets`.
- [ ] Реализовать точную десктопную сетку и адаптивные брейкпоинты 1100, 760 и 480 px.
- [ ] Повторить тест; ожидается PASS.

### Задача 6: полная и визуальная проверка

**Файлы:**
- При необходимости изменить: `src/*.tsx`, `src/styles.css`

**Интерфейсы:**
- Consumes: собранное приложение.
- Produces: проверенный локальный URL и скриншоты контрольных ширин.

- [ ] Запустить `npm test -- --run`; ожидается 0 упавших тестов.
- [ ] Запустить `npm run build`; ожидается exit 0 и каталог `dist`.
- [ ] Запустить `npm run dev -- --host 127.0.0.1`, открыть страницу через Playwright и проверить 1672×941, 1024×768, 390×844.
- [ ] Протестировать календарь, ввод времени, выдачу города, клавиатурный выбор, пустую отправку и успешное подтверждение.
- [ ] Проверить консоль браузера, горизонтальный overflow и reduced motion; исправить найденные дефекты и повторить весь набор команд.

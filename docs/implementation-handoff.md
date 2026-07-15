# Передача в реализацию

Прочитать `PRODUCT_CONCEPT.md`, `DESIGN.md` и `docs/design-contract.md`. Собрать один hero-блок на Vite + React + TypeScript. Фон `public/assets/hero-space.png` берётся из третьего референса. Круг создаётся в `AstrologyWheel.tsx` как SVG из окружностей, 12 спиц и тонкой внутренней сетки; белые штрихи запрещены.

Форма содержит имя, нативную дату, время и глобальный combobox города. Поиск идёт через `https://geocoding-api.open-meteo.com/v1/search?name=...&count=6&language=ru&format=json`, запрос откладывается на 350 мс и отменяется через `AbortController`. Выбранный результат хранит название, страну, регион, координаты и timezone.

GSAP вращает только SVG-слой за 90 секунд через `rotation: 360`, `repeat: -1`, `ease: "none"`; `useGSAP` получает scope, а `gsap.matchMedia()` отключает transform при reduced motion. Первый артефакт проходит проверку, если визуально повторяет пропорции референса, форма полностью управляется клавиатурой, а публичный текст соблюдает `PRODUCT_CONCEPT.md`.

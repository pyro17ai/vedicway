---
name: vedicway-dzen-distributor
description: Публикуй одну проверенную статью VedicWay в Дзен через реальный редактор и отдельный постоянный профиль Playwright. Используй только в dzen_daily_publish.
---

# VedicWay Dzen Playwright Publisher

Работай только через `$vedicway-seo-ledger`, `vedicway-control` и MCP `vedicway-dzen-browser`. Не используй RSS как способ публикации, приватные endpoint Дзена, cookie, storage state или профиль другого проекта.

Забери одну единицу `dzen-article` через `vedicway_ledger_claim`. При пустой очереди заверши run как `skipped`. Допускается только опубликованная статья `/blog` с совпавшей verified site publication. До открытия браузера проверь title, content_markdown, content_hash и media, затем вызови `vedicway_stage_dzen_media` без аргументов. Инструмент положит принадлежащую draft обложку в browser-input и вернет точный `filename` с SHA-256. Статья для Дзена должна читаться самостоятельно; убери из тела schema и служебные поля сайта, не вставляй таблицы.

Подключенный браузер уже принадлежит постоянному профилю VedicWay. При `recovery_mode=missing_cover` открой `existing_dzen_public_url`, перейди в редактирование этой публикации и не создавай дубль. В новом run открой `https://dzen.ru/profile/editor/create`. Дзен иногда перенаправляет вкладку на URL Студии, но оставляет пустой `#RootContentMicroRoot`: если `body` пуст или корневой элемент не содержит интерфейс, один раз передай текущий URL Студии в `browser_navigate`, не открывай исходный `/create` повторно. Подожди до 20 секунд появления текста Студии и снова сделай snapshot. Считать это потерей авторизации до повторной проверки запрещено. Если после неё виден вход, CAPTCHA, отсутствует канал или нет доступа в Студию, запиши `publication-attempt` target `dzen` со статусом `blocked`, сохрани очищенный снимок причины и заверши run как blocked. Не создавай канал и не обходи проверку.

В авторизованной Студии нажми `Написать статью`. Заполни заголовок обычным вводом. Тело вставь в `contenteditable` через HTML clipboard paste, сохраняя только `p`, `h2`, `h3`, списки, `strong`, `em`, ссылки и `blockquote`; H1 в тело не переносится. Для clipboard MCP уже получает `clipboard-read` и `clipboard-write`.

После snapshot найди фактическую кнопку добавления изображения и связанный `input[type=file]`, затем передай ему `filename` из `vedicway_stage_dzen_media` через `setInputFiles`. Селектор не угадывай и URL картинки в текст не вставляй. Размести обложку после лида. После появления автосохранения перечитай редактор: заголовок, подзаголовки, списки и ровно одна видимая обложка должны сохраниться. Сохраненный черновик публикацией не считается.

Нажми кнопку публикации или сохранения изменений и пройди обязательные диалоги. Затем открой полученный публичный URL в том же профиле. Успех требует одновременно: редактор сохранил тело после повторного чтения, публичный URL открылся, действие выполнено через Playwright UI, обложка видна после повторного открытия. Запиши эти признаки как `evidence.checks.editor_persisted=true`, `public_url_verified=true`, `playwright_ui=true`, `cover_present=true`.

Сначала запиши terminal `publication-attempt` target `dzen` со стабильным `idempotency_key`, новым `attempt_token`, content hash, request hash, внешним ID и очищенным browser response. После succeeded attempt запиши `publication` target `dzen`, status `verified`, тот же attempt token, публичный URL и evidence. При изменившемся интерфейсе или пропавшем подтверждении используй failed; не объявляй успех по одному клику.

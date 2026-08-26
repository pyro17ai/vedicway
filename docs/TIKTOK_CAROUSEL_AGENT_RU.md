# TikTok-карусели VedicWay через Codex CLI

Система не содержит самостоятельного AI-агента и TikTok MCP. Внешний scheduler запускает обычный `codex exec` из корня worktree, а Codex исполняет режим навыка `$vedicway-tiktok-carousel`. Единственный MCP в контуре выпуска — Exa для короткого ресёрча. Шесть исходных карточек создаёт встроенный `$imagegen`; загрузкой управляет установленный `$playwright-cli` через Chrome DevTools Protocol или отдельный persistent profile Chromium.

## Два задания scheduler

Первое задание по воскресеньям в 03:15 UTC поддерживает очередь в режиме `plan-queue`. Оно использует `$vedicway-tiktok-carousel` и Exa MCP, добавляет до семи неповторяющихся тем и не открывает TikTok. Второе задание ежедневно в 09:00 UTC работает в режиме `publish-next`: проверяет вход через `$playwright-cli`, исследует тему через Exa, вызывает `$imagegen` отдельно для каждого из шести слайдов, собирает manifest и публикует одну карусель. Готовые prompts лежат в `scripts/tiktok/prompts`; Python-runner `scripts/tiktok/scheduler.py` передаёт их в `codex exec` через stdin, пишет JSONL-лог и держит глобальную блокировку от параллельных запусков.

Обе cron-записи можно установить заранее: без файла `runtime/tiktok/SCHEDULER_ENABLED` runner вернёт статус `disabled` и не запустит Codex. Sentinel создаётся только после входа в TikTok, проверки Exa и ручного полного прогона.

## Локальный и VPS-браузер

Для уже запущенного локального Chrome с включённым remote debugging runner подключается к текущему профилю:

```powershell
node scripts/tiktok/playwright-runner.mjs `
  --manifest runtime/tiktok/runs/<run-id>/manifest.json `
  --cdp chrome `
  --session vedicway-tiktok-local
```

На VPS один раз создаётся профиль `runtime/tiktok/chromium-profile`, в котором владелец вручную входит в `@vedicway7`. Для входа служит временный systemd-сервис `vedicway-tiktok-login`: он поднимает Chrome в Xvfb и отдаёт экран через локальные x11vnc с noVNC. Порты VNC и WebSocket слушают только `127.0.0.1`; владелец открывает `http://127.0.0.1:6089/vnc.html` через локальный SSH-туннель. После подтверждения аккаунта сервис останавливается, а scheduler открывает тот же каталог headless:

```bash
node scripts/tiktok/playwright-runner.mjs \
  --manifest runtime/tiktok/runs/<run-id>/manifest.json \
  --profile runtime/tiktok/chromium-profile \
  --session vedicway-tiktok
```

Команда без `--publish` загружает шесть файлов, заполняет заголовок с описанием, проверяет `Everyone` и `Now`, сохраняет `tiktok-prepared.png`, затем останавливается. После визуальной проверки тот же выпуск публикуется командой с `--publish --resume-current`. Runner сверяет manifest и реальные SHA-256, резервирует одно нажатие Post в `runtime/tiktok/state.json` и принимает успехом только новый URL `https://www.tiktok.com/@vedicway7/photo/...`. Неопределённый ответ после клика переводит выпуск в `needs_review`, поэтому scheduler не создаст дубль.

## Почему не внутренний endpoint TikTok

Сетевой прогон TikTok Studio показал двухступенчатую схему: страница получает временную авторизацию через `/api/v1/video/upload/auth/`, затем отправляет карточки на одноразовые подписанные URL вида `tos*-up-*.tiktokcdn-us.com/upload/v1/...-photomode-*`. Запросы завязаны на активную браузерную сессию, короткоживущие параметры и меняющиеся anti-bot-подписи `X-Bogus`/`X-Gnarly`. Прямой вызов private API потребовал бы копировать cookies и поддерживать обратную разработку подписей после обновлений TikTok; этот путь ломается чаще DOM-сценария и создаёт лишний риск для аккаунта.

Официальный Photo Content Posting API технически существует на `/v2/post/publish/content/init/`, но требует OAuth scopes, публичных изображений на подтверждённом домене и аудита приложения. Неаудированный клиент ограничен приватными публикациями. Для внутреннего автопостера VedicWay устойчивый путь сейчас один: persistent Chromium плюс `playwright-cli`. Источники: [Photo API](https://developers.tiktok.com/doc/content-posting-api-reference-photo-post) и [Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/).

## Артефакты и проверки

Каждый выпуск живёт в `runtime/tiktok/runs/<run-id>`: `research.json`, `plan.json`, исходники `$imagegen`, WebP 1080×1440, `manifest.json` и снимки TikTok Studio. Нормализация одной карточки выполняется без генеративной обработки:

```powershell
node scripts/tiktok/finalize-slide.mjs --source <raw.png> --output <slide.webp>
```

Проверки pipeline:

```powershell
node --test tests/tiktok-playwright-publisher.test.mjs
python C:\Users\Huawei\.codex\skills\.system\skill-creator\scripts\quick_validate.py .agents\skills\vedicway-tiktok-carousel
```

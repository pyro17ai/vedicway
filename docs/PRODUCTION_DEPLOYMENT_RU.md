# Production deployment VedicWay

SEO-agent запускается отдельным Compose profile `seo`, получает PostgreSQL credentials через secret и работает только со схемой `seo_agent` через свой CLI. Его полный deployment и activation runbook находится в [SEO_AGENT_PRODUCTION_RU.md](SEO_AGENT_PRODUCTION_RU.md). Схема входит в общий PostgreSQL dump; перед backup и restore SEO-сервис останавливается вместе с API и worker.

## Контур

`compose.production.yml` поднимает PostgreSQL, Alembic-миграции content store, FastAPI, durable worker, отдельный SMTP-consumer и Nginx. Наружу опубликован только `127.0.0.1:8080`; TLS завершает хостовый reverse proxy или облачный ingress. PostgreSQL и служебные endpoints не имеют host port. Nginx работает от UID 101, прикладные Python-процессы от UID 10001; root filesystem у контейнеров read-only, writable paths вынесены в named volumes и tmpfs.

PostgreSQL хранит весь табличный контур: runtime в схеме `runtime`, статьи и правовой журнал в `public`, SEO-реестр в `seo_agent`. Том `runtime_data` содержит PDF и служебные ключевые файлы, `media_data` хранит изображения. API, worker и email-consumer используют одно подключение и не имеют файловой базы.

Nginx проксирует `/api`, отключает buffering для SSE, закрывает `/internal`, добавляет security headers и сжимает текстовые ответы gzip. Stock Nginx image не содержит сторонний Brotli module, поэтому Brotli намеренно не включён. Access log не записывает IP, URL, query, referrer и user-agent; для связи событий остаётся случайный request id. Uvicorn запускается с `--no-access-log`, а прикладной журнал использует шаблон маршрута `/api/v1/magic-links/{token}`. Inter и Cormorant Garamond собираются из локальных `@fontsource` assets: до согласия на cookies браузер не обращается к Google. CSP оставляет прямой поиск городов Open-Meteo, который нужен форме и должен быть раскрыт в политике персональных данных.

Хостовый TLS ingress, CDN и WAF стоят перед контейнерным Nginx и настраиваются отдельно. Для `/api/v1/magic-links/*` они обязаны полностью отключить URI access-log либо заменять сегмент токена фиксированным `{token}` до записи и экспорта в error tracking. Проверка проводится реальным запросом со специально созданной строкой-маркером и поиском этой строки во всех host, ingress, CDN и SIEM журналах; наличие маркера останавливает релиз.

Служебные payment/metrics endpoints доступны только через профиль `ops`: `ops-gateway` слушает loopback `127.0.0.1:8081` и подключён к отдельной internal-сети. Оператор открывает SSH tunnel или входит через VPN bastion; публичный TLS ingress этот порт не публикует. API не получает Codex key, worker не получает YooKassa, operations и metrics tokens. Раздельные `api-egress` и `worker-egress` сети позволяют хостовому firewall либо egress proxy независимо ограничить исходящий трафик. Сам Docker Compose не фильтрует HTTPS по домену: API разрешается только `api.yookassa.ru`, worker получает доступ только к утверждённым OpenAI/Codex endpoints.

`/sitemap.xml` запрашивает `/api/v1/seo/sitemap.xml`. Backend включает только опубликованные статьи и разрешённые кодом слоты гида. При 404/502/503/504 Nginx отдаёт статический `public/sitemap.xml`, в котором остаются главная, `/guide` и `/blog`. Служебные, chart, checkout и API URL запрещены в sitemap.

Запросы `/guide/<slug>` и `/blog/<slug>` проходят через серверный HTML endpoint. Опубликованная статья уже в первом ответе содержит title, description, canonical, полный текст, BreadcrumbList и Article либо BlogPosting JSON-LD; после загрузки React заменяет исходную разметку интерактивным интерфейсом. Неизвестный slug возвращает статический 404 без SPA fallback; frontend image проверяет Nginx через `nginx -t` при сборке.

## Обязательные входы релиза

Нужны Docker Engine с BuildKit и Docker Compose 2.24 или новее. Скопируйте `.env.production.example` в `.env.production` и замените все `REPLACE_*` и `vedicway.example`. Реальный домен обязан работать по HTTPS до активации YooKassa. Создайте secret-файлы по [secrets/README.md](../secrets/README.md), положите лицензированный мировой справочник мест в путь `VEDICWAY_PLACE_DATASET_FILE`, подготовьте Linux wheelhouse по [runtime/README.md](../runtime/README.md).

Никакой secret не запекается в image и не передаётся build argument. Compose монтирует credentials через `/run/secrets`, а entrypoint выдаёт каждому процессу только его набор: API получает платежи и operations, worker получает `OPENAI_API_KEY`, сервис `email` получает SMTP, lifecycle ограничен ключами runtime. Открытые пароли в `.env.production` запрещены. `CODEX_CLI_VERSION=0.144.6`, Node 22.17.0, Python 3.11.13, Playwright 1.58.2, PostgreSQL 17.5 и Nginx 1.28.0 зафиксированы в release-файлах; base images дополнительно закреплены manifest digest. Перед каждым обновлением версии прогоняйте весь CI и golden-карту.

## Сборка и запуск

PowerShell:

```powershell
Copy-Item .env.production.example .env.production
# Заполнить .env.production, secrets/*, runtime/places.json и wheelhouse.
python scripts/check_production_release.py --env-file .env.production
docker compose --env-file .env.production -f compose.production.yml build --pull
docker compose --env-file .env.production -f compose.production.yml up -d postgres content-migrate
docker compose --env-file .env.production -f compose.production.yml up -d backend worker email frontend
docker compose --env-file .env.production -f compose.production.yml ps
```

Bash использует те же команды после `cp .env.production.example .env.production`. `content-migrate` последовательно применяет `backend/migrations/*.sql`, Alembic и миграции `seo_agent`. Backend, worker и SEO-agent не стартуют до успешного завершения этого сервиса.

FastAPI запускается одним Uvicorn process. `VEDICWAY_INLINE_WORKER=0` отключает обработку очереди внутри API, поэтому jobs исполняет отдельный `worker`. Named volumes `runtime_data` и `media_data` обязательны и не удаляются командой `down -v`. Readiness проверяет PostgreSQL и текущую ревизию контентной схемы.

Production API и worker запускают контрольную D1 для Москвы 16.10.2006 13:30 и сверяют лагну с утверждённым fingerprint. Ошибка импорта PyJHora, эфемерид или расхождение расчёта оставляет API в `not_ready`, а worker завершает процесс и попадает под restart policy. Неверный Codex executable, пустой auth contour и любой provider кроме `codex` в production также останавливают процесс до приёма пользовательских задач.

Codex worker не получает внутренний `snapshot_id`; модель видит только минимальный набор производных астрологических фактов, нужных для объяснения. До запуска заполните юридическое наименование, адрес, страну, цель, категории данных и флаг трансграничной передачи `VEDICWAY_INTERPRETATION_PROCESSOR_*`. Заключённый договор поручения, проверка Роскомнадзора и заключение юриста остаются внешними release gates: зелёная readiness подтверждает заполненность конфигурации, но не подтверждает правомерность выбранной схемы передачи.

Письма восстановления содержат одноразовые ссылки со сроком 1 час. GET не расходует ссылку и перенаправляет на `noindex`/`no-referrer` страницу `/access/confirm`; доступ выдаёт только явная same-origin POST-форма с double-submit CSRF. В smoke-проверке почтовый scanner сначала выполняет GET без изменения `magic_links.used_at` и `chart_access`, затем отдельный браузер подтверждает ссылку, а повторный POST получает 401.

PDF-рендерер получает только локально собранный и экранированный HTML, блокирует все сетевые запросы страницы и запускает Chromium без внутренней sandbox: контейнер уже работает от непривилегированного UID, без capabilities, с `no-new-privileges` и read-only root filesystem. Такой режим нужен потому, что setuid sandbox Chromium несовместима с этими контейнерными ограничениями.

## Проверка после выкладки

```powershell
curl.exe -fsS https://YOUR_DOMAIN/healthz
curl.exe -fsS https://YOUR_DOMAIN/api/v1/health/ready
curl.exe -fsS https://YOUR_DOMAIN/robots.txt
curl.exe -fsS https://YOUR_DOMAIN/sitemap.xml
curl.exe -I https://YOUR_DOMAIN/media/articles/KNOWN_ASSET_ID/640.webp
curl.exe -I https://YOUR_DOMAIN/internal/metrics
```

Последний запрос обязан вернуть 404. Затем проведите один расчёт контрольной карты через публичную форму, дождитесь D1, бесплатного объяснения и вопросов. Тестовый платёж в production запрещён. До приёма реальных денег используйте тестовый магазин YooKassa в отдельном staging-контуре с `VEDICWAY_ENV=development`; production запускается только с реальными HTTPS callback URL и подтверждённым кодом НДС.

Проверка PDF включает D1 и выбранную varga/mode из интерфейса, загрузку файла и открытие всех страниц. Проверка sitemap включает статьи гида и блога, но исключает скрытые старые slug гида и `/chart/*`.

## Backup и restore PostgreSQL

`production_state.py` останавливает frontend, API и worker до первого снимка, присваивает PostgreSQL и runtime один `BACKUP_SET_ID`, проверяет оба SHA-256 и упаковывает их в аутентифицированный AES-256-GCM bundle. Открытые `.dump` и `.tar.gz` удаляются сразу после успешного шифрования. Перед первым запуском на Linux создайте каталог `install -d -m 0700 -o 10001 -g 10001 backups`; храните `.vwb` и ключ на раздельной российской инфраструктуре с утверждённым сроком хранения.

```powershell
python scripts/production_state.py backup --env-file .env.production
```

Restore расшифровывает bundle во временный каталог, проверяет manifest и готовит отдельную PostgreSQL database вместе со скрытыми runtime directories. Текущие данные остаются на месте до общей commit-фазы. При сбое обе части возвращаются в предыдущее состояние; предыдущая database и runtime directories удаляются после успешного commit обеих частей.

```powershell
python scripts/production_state.py restore --env-file .env.production --bundle "vedicway-pair-20260719T010000Z-deadbeef.vwb"
```

Раз в квартал восстанавливайте свежий bundle в изолированном staging и проверяйте число charts, purchases, entitlements, articles и media references. Runtime archive читается только с тем же `VEDICWAY_DATA_KEY`, а `.vwb` требует отдельного `VEDICWAY_BACKUP_KEY_FILE`; signing key хранится в secret manager для действующих ссылок. Backup без проверенного restore не считается резервной копией.

## Срок хранения и удаление

Публичный трафик запрещён, пока владелец не утвердил конкретные сроки хранения карт, контактных данных, consent records, media и резервных копий. Процедура удаления обязана очищать PostgreSQL, reports/media и все backup-копии по одному идентификатору субъекта либо подтверждённому отзыву согласия; одно удаление строки из основной базы не закрывает запрос субъекта. Перед релизом проведите проверяемую репетицию удаления в staging, сохраните только обезличенный audit-факт и убедитесь, что удалённые данные не возвращаются после восстановления очередной допустимой резервной копии.

Runtime lifecycle запускается сервисами `retention-dry-run` и `retention-apply` из профиля `ops`. Production-расписание systemd, SMTP-проверка и процедура tombstone recovery описаны в [recovery/retention runbook](RECOVERY_RETENTION_RUNBOOK_RU.md). Зелёная readiness без включённого ежедневного таймера не закрывает lifecycle gate.

## Release readiness checklist

- [ ] `.env.production` не содержит `.example`, `REPLACE_*`, тестовых payment flags и чужих CIDR; `check_production_release.py` завершился кодом 0.
- [ ] Image tags привязаны к Git SHA, wheelhouse PyJHora имеет сохранённый `SHA256SUMS`, лицензированный `places.json` прошёл загрузку, Codex API key принадлежит отдельному service account.
- [ ] `content-migrate` завершился кодом 0; runtime и SEO migrations применены, Alembic находится на `head`, все процессы используют PostgreSQL, публичная обложка отдаётся через `/media/articles/...`, а backup восстановлен в staging.
- [ ] TLS ingress передаёт `X-Forwarded-Proto=https`, порт Compose слушает loopback, `/internal` закрыт, CSP report в браузере пуст, HSTS присутствует на HTTPS-ответе. URI `/api/v1/magic-links/*` отключён или отредактирован во всех внешних access/error logs; тестовый токен-маркер не найден в CDN, ingress и SIEM.
- [ ] Опубликованы актуальные оферта, политика и согласие; реквизиты `VEDICWAY_INTERPRETATION_PROCESSOR_*` совпадают с договором, юрист проверил трансграничный флаг и уведомительный порядок Роскомнадзора. `VEDICWAY_OFFER_VERSION` совпадает с текстом, YooKassa webhook и возврат проверены из разрешённых сетей без ручного SQL.
- [ ] SMTP secret смонтирован, SPF/DKIM/DMARC проходят внешний тест, одноразовые chart/PDF ссылки не попадают в access log и не принимают replay.
- [ ] `/`, `/guide`, `/blog`, legal pages и опубликованные статьи возвращают корректные canonical/robots/schema; sitemap не содержит служебных URL, Yandex Webmaster принял robots и sitemap.
- [ ] Golden-карта, бесплатное объяснение, полный отчёт, вопросы и PDF прошли end-to-end. p95 расчёта и provider timeout укладываются в утверждённый SLO.
- [ ] Логи, PostgreSQL, media volume и backup физически размещены по утверждённой схеме локализации; секреты и персональные данные не попадают в logs, CI artifacts и error tracking.
- [ ] Утверждены сроки хранения по каждому классу данных; `retention-dry-run` проверен, systemd timer включён, запрос удаления очищает primary storage, отчёты, медиа и backup-копии, а восстановление не возвращает данные с истёкшим сроком.

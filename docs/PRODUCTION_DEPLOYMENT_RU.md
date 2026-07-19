# Production deployment VedicWay

## Контур

`compose.production.yml` поднимает PostgreSQL, две последовательные цепочки миграций, FastAPI, отдельный durable worker и Nginx. Наружу опубликован только `127.0.0.1:8080`; TLS завершает хостовый reverse proxy или облачный ingress. PostgreSQL и служебные endpoints не имеют host port. Nginx работает от UID 101, backend и worker от UID 10001; root filesystem у прикладных контейнеров read-only, writable paths вынесены в named volumes и tmpfs.

Сейчас действует split storage. PostgreSQL предназначен для users, roles, articles и media metadata после объединения admin-ветки. Расчёты, purchases, entitlements и PDF metadata остаются в SQLite `runtime_data`; сами media лежат в `media_data`. Поэтому production запускает ровно один API и один worker. Масштабирование `backend` или `worker`, rolling update с двумя активными экземплярами и перенос jobs между узлами запрещены до появления реального PostgreSQL adapter для chart/payment Store.

Nginx проксирует `/api`, отключает buffering для SSE, закрывает `/internal`, добавляет security headers и сжимает текстовые ответы gzip. Stock Nginx image не содержит сторонний Brotli module, поэтому Brotli намеренно не включён. Access log не записывает IP, URL, query, referrer и user-agent; для связи событий остаётся случайный request id. Inter и Cormorant Garamond собираются из локальных `@fontsource` assets: до согласия на cookies браузер не обращается к Google. CSP оставляет прямой поиск городов Open-Meteo, который нужен форме и должен быть раскрыт в политике персональных данных.

`/sitemap.xml` запрашивает `/api/v1/seo/sitemap.xml`. Backend должен включать в ответ только опубликованные статьи. При 404/502/503/504 Nginx отдаёт статический `public/sitemap.xml`, в котором остаются главная и `/guide`. Draft, admin, chart, checkout и API URL запрещены в sitemap и уже закрыты в `robots.txt`.

Запрос `/guide/<slug>` проходит через серверный HTML endpoint. Опубликованная статья уже в первом ответе содержит собственные title, description, canonical, полный текст и Article JSON-LD, после загрузки стабильных `seo-entry` aliases React заменяет исходную разметку обычным интерфейсом. Неизвестный slug и черновик возвращают статический 404 без SPA fallback; frontend image проверяет Nginx через `nginx -t` при сборке.

## Обязательные входы релиза

Нужны Docker Engine с BuildKit и Docker Compose 2.24 или новее. Скопируйте `.env.production.example` в `.env.production` и замените все `REPLACE_*` и `vedicway.example`. Реальный домен обязан работать по HTTPS до активации YooKassa. Создайте secret-файлы по [secrets/README.md](../secrets/README.md), положите лицензированный мировой справочник мест в путь `VEDICWAY_PLACE_DATASET_FILE`, подготовьте Linux wheelhouse по [runtime/README.md](../runtime/README.md).

Никакой secret не запекается в image и не передаётся build argument. Compose монтирует credentials через `/run/secrets`, а backend entrypoint переносит их в process environment без вывода в лог. Файл `codex_api_key.txt` экспортируется только как стандартная переменная `OPENAI_API_KEY`, которую читает Codex CLI; custom-имя ключа readiness не принимает. `CODEX_CLI_VERSION=0.144.6`, Node 22.17.0, Python 3.11.13, Playwright 1.58.2, PostgreSQL 17.5 и Nginx 1.28.0 зафиксированы в release-файлах; base images дополнительно закреплены manifest digest. Перед каждым обновлением версии прогоняйте весь CI и golden-карту.

## Сборка и запуск

PowerShell:

```powershell
Copy-Item .env.production.example .env.production
# Заполнить .env.production, secrets/*, runtime/places.json и wheelhouse.
python scripts/check_production_release.py --env-file .env.production
docker compose --env-file .env.production -f compose.production.yml build --pull
docker compose --env-file .env.production -f compose.production.yml up -d postgres migrate content-migrate
docker compose --env-file .env.production -f compose.production.yml up -d backend worker frontend
docker compose --env-file .env.production -f compose.production.yml ps
```

Bash использует те же команды после `cp .env.production.example .env.production`. Сервис `migrate` создаёт `schema_migrations`, исполняет все `backend/migrations/*.sql` по имени файла и сохраняет SHA-256. Изменённая задним числом миграция завершает запуск кодом 65. Затем `content-migrate` выполняет `alembic upgrade head` для пользователей, статей, медиа и журнала согласий. Backend и worker не стартуют, пока обе цепочки не завершатся без ошибки.

Первого администратора создаёт отдельный одноразовый профиль. Положите адрес и пароль длиной от 16 символов в `secrets/admin_bootstrap_email.txt` и `secrets/admin_bootstrap_password.txt`, затем выполните команду и удалите оба файла:

```powershell
docker compose --env-file .env.production -f compose.production.yml --profile bootstrap run --rm bootstrap-admin
Remove-Item secrets/admin_bootstrap_email.txt, secrets/admin_bootstrap_password.txt
```

Bootstrap-секреты не передаются обычным backend/worker. Повторный запуск не меняет существующего администратора и завершится без создания дубликата.

FastAPI запускается одним Uvicorn process. `VEDICWAY_INLINE_WORKER=0` отключает обработку очереди внутри API, поэтому jobs исполняет отдельный `worker`. Named volume `runtime_data` обязателен и не удаляется командой `down -v`. PostgreSQL readiness не доказывает сохранность chart/payment Store: отдельно проверяйте SQLite volume и runtime backup.

Production API и worker запускают контрольную D1 для Москвы 16.10.2006 13:30 и сверяют лагну с утверждённым fingerprint. Ошибка импорта PyJHora, эфемерид или расхождение расчёта оставляет API в `not_ready`, а worker завершает процесс и попадает под restart policy. Неверный Codex executable, пустой auth contour и любой provider кроме `codex` в production также останавливают процесс до приёма пользовательских задач.

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

Проверка PDF включает D1 и выбранную varga/mode из интерфейса, загрузку файла и открытие всех страниц. Проверка sitemap включает опубликованную статью и подтверждает отсутствие draft slug, `/admin`, `/guide/editor` и `/chart/*`.

## Backup и restore PostgreSQL

Нужны два backup: PostgreSQL и runtime archive. PostgreSQL backup создаёт custom-format dump, runtime backup использует SQLite Online Backup API, добавляет reports/media и сохраняет соседний SHA-256. Перед первым запуском на Linux создайте каталог `install -d -m 0700 -o 10001 -g 10001 backups`. Каталог содержит персональные данные: храните его на российской инфраструктуре, шифруйте внешним KMS/backup-сервисом и ограничьте срок хранения утверждённой политикой.

```powershell
docker compose --env-file .env.production -f compose.production.yml --profile ops run --rm backup
docker compose --env-file .env.production -f compose.production.yml stop frontend backend worker
docker compose --env-file .env.production -f compose.production.yml --profile ops run --rm runtime-backup
docker compose --env-file .env.production -f compose.production.yml up -d backend worker frontend
```

Restore PostgreSQL разрушает текущую базу и требует точной фразы подтверждения. Сначала остановите intake, API и worker, затем укажите только имя файла из `backups`:

```powershell
docker compose --env-file .env.production -f compose.production.yml stop frontend backend worker
$env:RESTORE_FILE = "vedicway-20260719T010000Z.dump"
$env:CONFIRM_RESTORE = "restore-vedicway"
docker compose --env-file .env.production -f compose.production.yml --profile ops run --rm restore
docker compose --env-file .env.production -f compose.production.yml up -d backend worker frontend
Remove-Item Env:RESTORE_FILE, Env:CONFIRM_RESTORE
```

Runtime restore выполняется отдельной командой и тоже требует остановленных API/worker. Он заменяет SQLite, reports и media volume одним проверенным архивом:

```powershell
docker compose --env-file .env.production -f compose.production.yml stop frontend backend worker
$env:RESTORE_RUNTIME_FILE = "vedicway-runtime-20260719T010000Z.tar.gz"
$env:CONFIRM_RUNTIME_RESTORE = "restore-runtime"
docker compose --env-file .env.production -f compose.production.yml --profile ops run --rm runtime-restore
docker compose --env-file .env.production -f compose.production.yml up -d backend worker frontend
Remove-Item Env:RESTORE_RUNTIME_FILE, Env:CONFIRM_RUNTIME_RESTORE
```

Раз в квартал восстанавливайте свежий dump в изолированном staging и проверяйте число charts, purchases, entitlements, articles и media references. Runtime archive читается только с тем же `VEDICWAY_DATA_KEY`; signing key отдельно сохраняется в secret manager для действующих ссылок. Backup без проверенного restore не считается резервной копией.

## Срок хранения и удаление

Публичный трафик запрещён, пока владелец не утвердил конкретные сроки хранения карт, контактных данных, consent records, media и резервных копий. Процедура удаления обязана очищать PostgreSQL, SQLite, reports/media и все backup-копии по одному идентификатору субъекта либо подтверждённому отзыву согласия; одно удаление строки из основной базы не закрывает запрос субъекта. Перед релизом проведите проверяемую репетицию удаления в staging, сохраните только обезличенный audit-факт и убедитесь, что удалённые данные не возвращаются после восстановления очередной допустимой резервной копии.

## Release readiness checklist

- [ ] `.env.production` не содержит `.example`, `REPLACE_*`, тестовых payment flags и чужих CIDR; `check_production_release.py` завершился кодом 0.
- [ ] Image tags привязаны к Git SHA, wheelhouse PyJHora имеет сохранённый `SHA256SUMS`, лицензированный `places.json` прошёл загрузку, Codex API key принадлежит отдельному service account.
- [ ] `migrate` и `content-migrate` завершились кодом 0; Alembic находится на `head`, users/articles store использует `VEDICWAY_DATABASE_URL`, публичная обложка отдаётся через `/media/articles/...`. Chart/payment SQLite работает только в одном API и одном worker, оба вида backup восстановлены в staging.
- [ ] TLS ingress передаёт `X-Forwarded-Proto=https`, порт Compose слушает loopback, `/internal` закрыт, CSP report в браузере пуст, HSTS присутствует на HTTPS-ответе.
- [ ] Опубликованы актуальные оферта и политика; `VEDICWAY_OFFER_VERSION` совпадает с текстом, YooKassa webhook и возврат проверены из разрешённых сетей без ручного SQL.
- [ ] `/`, `/guide`, legal pages и опубликованные статьи возвращают корректные canonical/robots/schema; sitemap не содержит служебных URL, Yandex Webmaster принял robots и sitemap.
- [ ] Golden-карта, бесплатное объяснение, полный отчёт, вопросы и PDF прошли end-to-end. p95 расчёта и provider timeout укладываются в утверждённый SLO.
- [ ] Логи, PostgreSQL, media volume и backup физически размещены по утверждённой схеме локализации; секреты и персональные данные не попадают в logs, CI artifacts и error tracking.
- [ ] Утверждены сроки хранения по каждому классу данных; запрос удаления проверенно очищает primary storage, отчёты, медиа и backup-копии, а восстановление не возвращает данные с истёкшим сроком.

Жёсткий стоп масштабирования: `backend/src/vedicway_backend/store.py` хранит charts и payments в SQLite. Compose передаёт `DATABASE_URL` и `VEDICWAY_DATABASE_URL` для admin/content adapter, но до переноса chart/payment таблиц допускается только single-node split storage. Если после объединения admin-ветки ни один production component не читает PostgreSQL, уберите `postgres` и `migrate` из запуска: декоративная база создаёт ложное ощущение надёжности. Зелёный `/health/ready` сейчас подтверждает доступ к runtime Store, но не полноценный disaster recovery.

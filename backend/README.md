# VedicWay backend

Сервис реализует путь от формы рождения до вычисленного снимка D1, бесплатных объяснений, оплаты через YooKassa и PDF. Для вычислений он импортирует собственный пакет `pyjhora_mcp`; астрологические формулы в этот репозиторий не копируются.

## Локальный запуск

Для локального интерфейса с настоящими персональными объяснениями запускайте готовый изолированный контур. Первый запуск копирует только файл авторизации в отдельный `CODEX_HOME`; пользовательские настройки, skills, MCP, память и рабочие файлы runner не видит:

```powershell
.\scripts\Start-VedicWayCodexBackend.ps1 -Port 8015 -BootstrapAuthFromCurrentUser
```

Следующие запуски не требуют bootstrap-флага:

```powershell
.\scripts\Start-VedicWayCodexBackend.ps1 -Port 8015
```

Скрипт находит настоящий `codex.exe`, создаёт пустой read-only workdir в `%LOCALAPPDATA%\VedicWay\codex-runner`, включает `VEDICWAY_INTERPRETATION_PROVIDER=codex` и хранит локальную БД отдельно от основной рабочей копии.

Укажите путь к исходникам собственного PyJHora MCP и используйте Python 3.11 из его виртуального окружения:

```powershell
$env:PYTHONPATH = "D:\VedicWay\backend\src"
$env:VEDICWAY_PYJHORA_SOURCE = "C:\Users\Huawei\.codex\mcp\pyjhora-mcp\src"
$env:VEDICWAY_TEST_PAYMENTS = "1"
C:\Users\Huawei\.codex\mcp\pyjhora-mcp\.venv\Scripts\python.exe -m uvicorn vedicway_backend.main:app --host 127.0.0.1 --port 8000
```

`VEDICWAY_TEST_PAYMENTS=1` открывает только локальный тестовый провайдер. Production-процесс принимает реальный payment adapter по конфигурации и не подтверждает оплату браузерным query-параметром.

Локальный тестовый провайдер проводит браузер через `/api/v1/test/checkout/:purchaseId`. Страница симулирует внешний redirect, но не запрашивает реквизиты и не списывает деньги. `VEDICWAY_ENV=production` запрещает запуск этого контура.

Для production также задайте `VEDICWAY_PLACE_DATASET_PATH`: это путь к лицензированному JSON-справочнику городов, который хранится рядом с приложением. Каждая запись содержит `place_id`, отображаемое имя, код страны, координаты, IANA `tzid` и необязательный массив `alternate_names`. Бэкенд не отправляет поисковый запрос в публичный геокодер; без этого файла production-процесс не стартует.

## Production-конфигурация YooKassa

Процесс запускается с `VEDICWAY_ENV=production`, `VEDICWAY_PAYMENT_PROVIDER=yookassa` и `VEDICWAY_TEST_PAYMENTS=0`. Он аварийно завершает startup при отсутствии `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, публичного HTTPS-origin, оферты, кода НДС, operations token, разрешённых operations CIDR, `VEDICWAY_DATA_KEY` или `VEDICWAY_SIGNING_KEY`. Signing key содержит не меньше 32 байт. В production адаптер обращается только к `https://api.yookassa.ru/v3`; подмена origin запрещена.

Публичные адреса после выкладки:

- webhook: `https://<домен>/api/v1/webhooks/payments/yookassa`;
- return: `https://<домен>/chart/<chartId>?payment_return=<purchaseId>`;
- открытая конфигурация товара: `https://<домен>/api/v1/payments/config`.

Создание заказа принимает email для чека, код товара и принятую версию оферты. Серверный каталог хранит две цены: `99000 RUB` за полный отчёт и `30000 RUB` за ректификацию времени рождения. Backend сохраняет provider idempotency key до запроса, поэтому сетевой повтор использует тот же объект YooKassa. Browser получает только внутренний ID заказа, статус, цену и `confirmation_url`; платёжные реквизиты VedicWay не собирает.

YooKassa не присылает пользовательскую HMAC-подпись для уведомлений этого типа. Backend допускает webhook только из опубликованных сетей YooKassa, учитывает `X-Forwarded-For` лишь от `VEDICWAY_TRUSTED_PROXY_CIDRS`, затем повторно запрашивает payment или refund через API v3. Entitlement появляется после сверки provider ID, серверной цены выбранного товара, metadata и признаков `paid/captured`.

Внутренние `reconcile` и `refund` закрыты токеном `VEDICWAY_OPERATIONS_TOKEN` и сетями `VEDICWAY_OPERATIONS_CIDRS`. Причина возврата и email шифруются `VEDICWAY_DATA_KEY`; audit хранит fingerprint токена, trace ID и результат. Частичный возврат оставляет entitlement, полный помечает его отозванным.

PostgreSQL накатывается по порядку:

```text
backend/migrations/001_chart_result.sql
backend/migrations/002_yookassa_production.sql
backend/migrations/003_pdf_render_preferences.sql
backend/migrations/004_runtime_rate_limits.sql
backend/migrations/005_recovery_retention.sql
backend/migrations/006_magic_link_confirmation.sql
backend/migrations/007_birth_time_rectification.sql
```

SQLite остаётся runnable-контуром для текущего production-профиля `single-node-sqlite` и обновляет старую базу совместимыми `ALTER TABLE`. Файлы `backend/migrations/*.sql` остаются заготовкой для будущего PostgreSQL-backed Store и не запускаются в production до появления этого adapter.

## Границы

- SQLite используется для локального runnable-контура. PostgreSQL DDL лежит в последовательных миграциях `001_chart_result.sql` - `004_runtime_rate_limits.sql`.
- `DevelopmentInterpretationProvider` служит только явным контрактным stub в тестах. Рабочий процесс не подставляет его при сбое: D1 остаётся доступной, а вкладка объяснений получает локальную retryable-ошибку. `CodexExecProvider` делает до двух one-shot вызовов: основной и один repair после schema/semantic validation.
- PDF создаёт Node/Playwright worker через `scripts/render_pdf.mjs`. Он строит HTML из экранированных строк и SVG D1, без model HTML и внешней сети.

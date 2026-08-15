# Production-интеграция VedicWay с YooKassa

**Статус:** утверждено владельцем продукта 18 июля 2026 года

**Ветка:** `codex/yookassa-production`

**Worktree:** `D:\CODEX_WORK\VedicWay-yookassa`

**Ограничение:** реализация не входит в личный кабинет YooKassa, не получает реальные ключи и не выполняет живые платежи.

## 1. Цель и границы

VedicWay продаёт один цифровой товар `full_report_v1`: полный персональный отчёт за 990 рублей, без подписки и сохранения платёжного средства. Интеграция должна принимать оплату через redirect-страницу YooKassa, формировать чек через решение «Чеки от YooKassa», выдавать `report_full` только после серверной проверки платежа, поддерживать возвраты и сохранять восстанавливаемое состояние при задержке webhook.

В работу входят backend-адаптер API v3, хранение заказов и событий, защищённый webhook, серверная сверка статусов, возвраты, фискальные данные, frontend-сценарий оплаты, production-конфигурация, эксплуатационные инструкции и автоматические проверки. Авторизация магазина, регистрация webhook в кабинете, ввод реальных секретов и десять контрольных платежей выполняются позже по отдельной команде.

## 2. Выбранный технический подход

Backend обращается к YooKassa напрямую через асинхронный `httpx.AsyncClient`. Официальный Python SDK не используется: его синхронный транспорт и глобальная конфигурация учётных данных плохо сочетаются с FastAPI lifespan, изолированными тестами и возможной ротацией секретов. Доменный интерфейс `PaymentProvider` сохраняется, поэтому поставщика можно заменить без изменения покупки, entitlement и интерфейса.

Production фиксирует `https://api.yookassa.ru/v3` как единственный допустимый API origin. Подмена base URL разрешена только в development и test для локального эмулятора. Клиент задаёт общий timeout, не пишет Basic Auth в логи и повторяет временные ошибки с прежним `Idempotence-Key`. Ошибка после отправки запроса считается неопределённым результатом: следующий вызов использует тот же provider key и получает тот же объект YooKassa.

## 3. Конфигурация

Production-процесс запускается с `VEDICWAY_PAYMENT_PROVIDER=yookassa` и требует следующие переменные:

| Переменная | Назначение |
|---|---|
| `YOOKASSA_SHOP_ID` | идентификатор магазина для Basic Auth |
| `YOOKASSA_SECRET_KEY` | секретный ключ магазина |
| `VEDICWAY_PUBLIC_BASE_URL` | публичный HTTPS-origin VedicWay для return URL |
| `YOOKASSA_VAT_CODE` | код НДС из настроек продавца; значение не угадывается кодом |
| `VEDICWAY_OFFER_VERSION` | версия оферты, принятой покупателем |
| `VEDICWAY_OFFER_URL` | публичный HTTPS-адрес оферты |
| `VEDICWAY_PRIVACY_URL` | публичный HTTPS-адрес политики обработки данных |
| `VEDICWAY_OPERATIONS_TOKEN` | отдельный секрет внутреннего контура сверки и возвратов |
| `VEDICWAY_TRUSTED_PROXY_CIDRS` | сети reverse proxy, которым разрешено передавать адрес клиента |
| `VEDICWAY_OPERATIONS_CIDRS` | сети, из которых доступен внутренний платёжный API |

`YOOKASSA_PAYMENT_DESCRIPTION` и название позиции чека имеют безопасные значения по умолчанию без даты рождения, имени и астрологических данных. `YOOKASSA_API_BASE_URL` допускается только вне production. Тестовый провайдер остаётся доступным за `VEDICWAY_TEST_PAYMENTS=1` и не может включиться в production.

## 4. Создание покупки

Frontend отправляет `POST /api/v1/charts/:chartId/purchases` с `product_code=full_report_v1`, email, подтверждением оферты и клиентским `Idempotency-Key`. Сумма от браузера не принимается. Backend проверяет ownership карты, готовность snapshot, отсутствие действующего entitlement, email, принятую оферту и server catalog `99000 RUB`.

Новая запись purchase получает собственный provider idempotency key. Повтор исходного запроса возвращает существующий заказ. Если для карты уже существует активный `pending`-заказ на этот товар, backend возвращает его и не создаёт второй платёж. Новый заказ разрешён после окончательного `canceled` или `failed` статуса. При неопределённом состоянии backend сначала выполняет server-to-server reconciliation.

Запрос YooKassa содержит:

- `amount.value = "990.00"`, `currency = "RUB"`, `capture = true`;
- redirect confirmation с публичным return URL, содержащим только внутренний `purchase_id`;
- metadata `purchase_id`, `chart_id`, `product_code` и deployment environment;
- receipt customer email и одну позицию услуги с количеством `1.00`, полной оплатой, предметом `service` и `vat_code` из конфигурации.

Ответ сохраняется в redacted-виде: provider payment ID, status, confirmation URL, время создания и безопасный код ошибки. Полный provider payload, Basic Auth, email и платёжные реквизиты не попадают в обычные логи.

## 5. Webhook и подтверждение оплаты

Публичный endpoint `POST /api/v1/webhooks/payments/yookassa` не использует browser session. YooKassa не присылает секретную HMAC-подпись для этого сценария, поэтому backend проверяет фактический адрес соединения по официальному списку сетей. `X-Forwarded-For` учитывается только при подключении от reverse proxy из `VEDICWAY_TRUSTED_PROXY_CIDRS`.

После разбора JSON backend берёт provider object ID и повторно запрашивает его через API YooKassa. Для `payment.succeeded` проверяются provider ID, финальный status, `paid`, `captured`, сумма, валюта и metadata. Purchase должен принадлежать текущему deployment и совпадать с `chart_id` и товаром. Любое несовпадение создаёт security incident, не выдаёт доступ и возвращает ответ, вызывающий повтор уведомления либо ручную сверку.

Дедупликационный ключ строится из provider, типа события и идентификатора объекта. В одной транзакции backend сохраняет checksum события, переводит purchase в финальный статус, создаёт или отзывает entitlement, пишет outbox-событие и ставит нужную job. Повторное уведомление возвращает `200 OK` без повторной выдачи доступа. Временная недоступность API возвращает `503`, чтобы YooKassa повторила доставку.

`payment.canceled` закрывает попытку и сохраняет безопасную причину отмены. `refund.succeeded` проверяется через API возвратов, обновляет возвращённую сумму и переводит purchase в `partially_refunded` либо `refunded`. Полный возврат отзывает entitlement и запрещает новые скачивания; уже полученный пользователем файл технически отозвать невозможно.

## 6. Серверная сверка и возвраты

`GET /api/v1/purchases/:purchaseId` отдаёт локальный статус владельцу заказа. Для `pending` и неопределённого состояния backend выполняет ограниченную по частоте сверку с YooKassa. Redirect браузера не передаёт признак успеха и не меняет entitlement.

Внутренний API предоставляет действия reconcile и refund. Он закрыт одновременно constant-time токеном `VEDICWAY_OPERATIONS_TOKEN` и сетями `VEDICWAY_OPERATIONS_CIDRS`; CORS для него отсутствует. Возврат принимает внутренний purchase ID, сумму в копейках, причину и внешний idempotency key. Backend проверяет успешный исходный платёж, остаток суммы, валюту и отсутствие конфликтующей операции. Полный и частичный возвраты используют один и тот же provider key при повторе.

Каждое внутреннее действие записывает audit event с временем, trace ID, хешем actor token, причиной, суммой и результатом. Секрет и пользовательские данные в аудит не попадают.

## 7. Хранение и миграции

Purchase расширяется полями `product_code`, provider idempotency key, confirmation URL, offer version, provider status, failure code, paid/canceled timestamps, paid amount и refunded amount. Email остаётся зашифрованным существующим ключом данных. Entitlement получает `revoked_at` и `revocation_reason`, поэтому проверка доступа учитывает отзыв.

Отдельная таблица refunds хранит provider refund ID, idempotency key, сумму, статус и audit metadata. `payment_events` получает event type, object ID и безопасный payload checksum. Изменения runtime-схемы оформляются последовательными миграциями PostgreSQL.

Provider create и локальная запись не образуют распределённую транзакцию. Устойчивость достигается сохранением purchase и provider key до внешнего вызова, повтором с тем же ключом и reconciliation. Если процесс падает после ответа YooKassa, повтор восстанавливает provider object без двойного списания.

## 8. Frontend-сценарий

Paywall сохраняет выбранную жизненную тему и показывает один товар за 990 рублей. Перед CTA пользователь вводит email, принимает оферту и может открыть оферту либо политику в новой вкладке. Кнопка блокируется на время запроса и не собирает реквизиты карты.

После получения `confirmation_url` браузер сохраняет только внутренний purchase ID и выбранный контекст в `sessionStorage`, затем выполняет redirect. Return URL открывает состояние `Проверяем платёж` и опрашивает `GET /purchases/:id` с возрастающим интервалом до 60 секунд. `succeeded` запускает обновление chart resource и открывает выбранный полный текст после появления entitlement. `canceled` и `failed` возвращают paywall с нейтральной причиной. `pending` после тайм-аута сообщает, что проверка продолжается, и оставляет безопасную кнопку повторной проверки.

Повторная оплата не предлагается, пока предыдущая попытка остаётся `pending` или `unknown`. Query-параметр успеха, локальный storage и frontend-событие не способны открыть платный JSON или PDF.

## 9. Ошибки и наблюдаемость

API YooKassa переводится в стабильные доменные коды без текста, содержащего внутренние сведения. `400`, `401`, `403` и `404` не повторяются автоматически. `429`, transport timeout и `5xx` повторяются с тем же provider key по ограниченной политике backoff. После исчерпания попыток purchase остаётся сверяемым, а пользователю показывается безопасный статус.

Метрики охватывают создание платежа, latency provider API, webhook, reconciliation, status mismatch, duplicate event, entitlement transition и refunds. Labels содержат только operation, status и error code. Trace ID проходит через purchase, payment event и outbox. Runbook описывает задержку webhook, mismatch, ошибочный VAT, ротацию ключей и ручную сверку.

## 10. Проверки и выпуск

Unit-тесты используют `httpx.MockTransport` и проверяют точное тело create/refund, Basic Auth без утечки, provider idempotency key, status mapping и ошибки. API-тесты покрывают повторный клиентский key, активную попытку, spoofed webhook IP, trusted proxy, повторный lookup, mismatch суммы и metadata, duplicate event, delayed success, canceled, partial refund и full refund.

Frontend-тесты проверяют email, оферту, блокировку двойного клика, redirect, polling, возврат в выбранную тему и отсутствие открытия по query. Playwright поднимает локальный fake YooKassa server и проходит полный путь от paywall до entitlement без реальных учётных данных. Финальная проверка включает frontend build, Vitest, backend pytest, линтеры и Playwright.

Production activation остаётся закрыта до заполнения секретов, настройки HTTPS, регистрации webhook в кабинете YooKassa, проверки налогового кода владельцем и десяти последовательных тестовых платежей. Код и документация к этим действиям готовятся сейчас, сами действия не выполняются.

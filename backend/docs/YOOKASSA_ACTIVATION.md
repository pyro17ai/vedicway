# Активация YooKassa в VedicWay

Код платёжного контура готов к подключению магазина, но вход в YooKassa и авторизация не выполнялись. Реальные `shopId`, secret key, webhook и тестовые операции появятся только после отдельного решения владельца.

## Что готово в коде

Backend создаёт redirect payment через API v3 с `capture=true` и сохраняет UUID v4 как `Idempotence-Key` до обращения к провайдеру. Сервер назначает 990 ₽ за полный отчёт и 300 ₽ за ректификацию времени рождения. Email используется для чека и хранится в зашифрованном виде. Frontend требует согласие с текущей версией оферты, не собирает реквизиты карты и после возврата проверяет серверный purchase до открытия купленной услуги.

Webhook принимает только события из официальных сетей YooKassa. При наличии reverse proxy доверие к `X-Forwarded-For` ограничено `VEDICWAY_TRUSTED_PROXY_CIDRS`. В production туда входят сети `edge` и `ops`, адрес шлюза фиксированной `loopback`-сети и точный адрес публичного Timeweb edge `92.53.96.169/32`. Host Nginx передаёт TCP-адрес edge через PROXY protocol, поэтому прямой запрос к origin не может выдать себя за доверенный proxy. Каждое уведомление подтверждается запросом payment или refund через API v3; сумма, валюта, metadata и provider ID сверяются с локальным заказом. Entitlement создаётся транзакционно и отзывается после полного возврата.

Служебные reconcile и refund закрыты отдельным токеном и CIDR. Возвраты идемпотентны, причины шифруются, операции попадают в audit. Локальный redirect-симулятор включается только через `VEDICWAY_TEST_PAYMENTS=1`, а production отвергает такой запуск.

## Блокирующие условия выкладки

Production deploy использует PostgreSQL-backed `Store` и применяет весь каталог `backend/migrations`, включая `008_runtime_schema.sql`. Нужны публичный HTTPS-домен, корректная цепочка reverse proxy, долговечное хранилище отчётов и секреты из secret manager. Оферта и политика конфиденциальности должны отвечать 200 по тем URL, которые отдаёт `/api/v1/payments/config`.

Владелец магазина вместе с бухгалтером подтверждает `YOOKASSA_VAT_CODE` и при необходимости `YOOKASSA_TAX_SYSTEM_CODE`. До этого нельзя отправлять production-чеки. Operations endpoint публикуется только во внутренней сети или VPN; его CIDR не должен включать публичный интернет.

## Переменные production

```dotenv
VEDICWAY_ENV=production
VEDICWAY_TEST_PAYMENTS=0
VEDICWAY_PAYMENT_PROVIDER=yookassa
VEDICWAY_PUBLIC_BASE_URL=https://<домен>
VEDICWAY_OFFER_VERSION=<версия опубликованной оферты>
VEDICWAY_OFFER_URL=https://<домен>/legal/offer
VEDICWAY_PRIVACY_URL=https://<домен>/legal/privacy
VEDICWAY_TRUSTED_PROXY_CIDRS=<CIDR reverse proxy>
VEDICWAY_OPERATIONS_CIDRS=<CIDR support VPN>
VEDICWAY_OPERATIONS_TOKEN=<secret от 32 символов>
VEDICWAY_DATA_KEY=<Fernet key>
VEDICWAY_SIGNING_KEY=<random secret от 32 байт>
YOOKASSA_SHOP_ID=<из secret manager>
YOOKASSA_SECRET_KEY=<из secret manager>
YOOKASSA_VAT_CODE=<подтверждённый код 1..12>
YOOKASSA_TAX_SYSTEM_CODE=<код 1..6, если требуется>
```

`YOOKASSA_API_BASE_URL` в production не задаётся: приложение использует официальный `https://api.yookassa.ru/v3` и отвергает другой origin. Реальные значения не сохраняются в `.env`, Git, логи или CI artifacts.

## Действия в кабинете после разрешения владельца

В магазине YooKassa создать API secret и сохранить его вместе с `shopId` в secret manager. Настроить webhook `https://<домен>/api/v1/webhooks/payments/yookassa` для `payment.succeeded`, `payment.canceled` и `refund.succeeded`. Return URL приложение передаёт при создании платежа: `https://<домен>/chart/<chartId>?payment_return=<purchaseId>`.

Сначала использовать тестовый магазин YooKassa. Для него оставить `VEDICWAY_TEST_PAYMENTS=0`: значение `1` включает локальный симулятор и не обращается к YooKassa. Провести десять последовательных платежей, закрытие формы без оплаты, повторный browser return, задержанный webhook и двойную доставку одного события. Отдельно проверить частичный возврат минимум 1 ₽, полный возврат, чек и отзыв entitlement. После сверки audit и чеков переключить secret на production-магазин и повторить один малый контролируемый заказ с последующим полным возвратом.

## Контроль перед включением трафика

`/api/v1/health/ready` отвечает 200, legal URL открываются без авторизации, `/api/v1/payments/config` показывает 99000 RUB, а запрос с `product_code=birth_time_rectification_v1` показывает 30000 RUB. Webhook возвращает 403 для постороннего IP и 200 для проверенного события YooKassa. Повтор события не создаёт второй entitlement; поддельный `success=true` и неизвестный `payment_return` доступа не дают.

Служебные endpoints возвращают 404 без правильного токена и 403 вне support CIDR. Reconcile оставляет audit. Повтор refund с тем же `Idempotency-Key` не создаёт вторую операцию. После полного refund право `report_full` отозвано, а повторная покупка создаёт новый независимый purchase.

## Статус активации на 18.07.2026

Код, локальный simulator, миграция и эксплуатационная документация подготовлены. Автоматическая проверка на 18.07.2026 прошла 64 backend-теста, 34 frontend-теста, 8 Playwright-сценариев, production build, Ruff и secret scan. Провайдерный adapter покрыт `httpx.MockTransport`; реальный API не вызывался.

Авторизация в YooKassa не выполнялась. Secret key, webhook в кабинете, налоговые параметры, реальный PostgreSQL store и тестовые операции YooKassa ожидают действий владельца перед production deploy.

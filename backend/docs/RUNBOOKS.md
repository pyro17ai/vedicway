# Runbooks VedicWay

## D1 failures выше 1% за 10 минут

Остановить intake только при недоступности ephemeris или повреждении адаптера. Сначала проверить `EPHEMERIS_MISSING`, `TIMEZONE_RESOLUTION_FAILED` и `CALCULATION_FAILED` в событиях jobs, затем выполнить golden-карту Москвы: 16.10.2006, 13:30, `ru-moscow-524901`, Лахири. Лагна должна остаться в Скорпионе 23.7133°. При расхождении не публиковать новые отчёты до фиксации версии PyJHora и Swiss Ephemeris.

## Очередь не двигается

Сверить число `queued` jobs и возраст самого старого `instant_v1`. Если worker остановлен, поднять отдельный worker-процесс, не перезапуская API. Повторять только `failed_retryable` через endpoint retry; `failed_terminal` сначала требует исправления причины. Outbox не очищать вручную: SSE и polling используют его для восстановления состояния.

## Поставщик объяснений недоступен или ответы не проходят validator

Проверить count `job_failure_total{job_type="interpretation_free_v1"}` и коды `INTERPRETATION_UNAVAILABLE`/`INTERPRETATION_INVALID`. Не отправлять в повтор свободный текст и не ослаблять validator. Сначала сверить immutable snapshot, checksum evidence и prompt version, затем включить только безопасный локальный fallback либо повторить тот же job с прежним evidence checksum.

## Production не запускается с YooKassa

Не обходить fail-closed проверку. Сверить `VEDICWAY_PAYMENT_PROVIDER=yookassa`, выключенный `VEDICWAY_TEST_PAYMENTS`, публичный HTTPS-origin, опубликованные URL оферты и политики, актуальную версию оферты, `YOOKASSA_SHOP_ID`, secret key, код НДС, operations token длиной от 32 символов и разрешённые operations CIDR. Production принимает только `https://api.yookassa.ru/v3`. Ошибка startup означает, что приём денег оставлен выключенным намеренно.

## Webhook задержан, запрещён или не совпал с заказом

Redirect браузера не меняет entitlement. YooKassa не прикладывает merchant HMAC к этим уведомлениям: backend проверяет исходный IP по опубликованным сетям YooKassa, а затем получает payment или refund через API v3. Если запрос пришёл через reverse proxy, `X-Forwarded-For` учитывается только для peer из `VEDICWAY_TRUSTED_PROXY_CIDRS`; ошибочная сеть proxy даст `WEBHOOK_SOURCE_FORBIDDEN`. Для маршрута Timeweb edge -> TLS на порту 80 -> origin:8443 stream Nginx обязан отправлять PROXY protocol, а HTTP Nginx обязан принимать его на 8082 и 8443 только от `127.0.0.1`.

При задержке проверить доступность webhook URL, ответ 200 и provider payment ID. Повтор одного уведомления безопасен: `payment_events` дедуплицирует событие. Для ручной сверки support вызывает `POST /internal/payments/{purchase_id}/reconcile` из разрешённой сети с `X-Operations-Token`. Browser query, ручной `UPDATE` и повторная покупка не служат способом выдать entitlement.

При `PAYMENT_MISMATCH` оставить доступ закрытым. Сверить цену выбранного товара в server catalog, metadata `purchase_id`, `chart_id`, `product_code`, provider payment ID и финальный статус. Запись `payment_incidents` вместе с trace ID сохраняет причину; исправление требует отдельного расследования, а не нового webhook из браузера.

## YooKassa API недоступен или отвечает 429/5xx

Создание payment и refund повторяется с тем же сохранённым `Idempotence-Key`. Не генерировать новый ключ для уже созданного локального объекта. При `PAYMENT_PROVIDER_TEMPORARY` оставить purchase или refund в `unknown`, дождаться восстановления API и выполнить служебный reconcile. Ошибки авторизации не повторять: проверить secret в secret manager и привязку shop ID, затем перезапустить процесс с исправленной парой.

## Чек отклонён

Проверить email покупателя, `YOOKASSA_VAT_CODE`, необязательный `YOOKASSA_TAX_SYSTEM_CODE`, описание позиции и сумму. Код НДС выбирает владелец магазина вместе с бухгалтером; разработчик не угадывает его по режиму налогообложения. Полный возврат отправляется без нового состава чека, частичный содержит receipt item на сумму операции. Состояние `receipt_registration` хранится для диагностики.

## Частичный или полный возврат

Возврат создаётся только через `POST /internal/payments/{purchase_id}/refunds` из `VEDICWAY_OPERATIONS_CIDRS`. Требуются `X-Operations-Token`, стабильный `Idempotency-Key` и JSON с `amount_minor` от 100 до 99000 и содержательной `reason`. Повтор с тем же ключом возвращает прежнюю операцию. Частичный возврат сохраняет доступ; полный возврат отзывает `report_full`. Причина шифруется, а audit содержит fingerprint оператора, источник, trace ID и результат.

## Ротация ключей

Secret key YooKassa меняется через secret manager: сначала выпустить новый ключ в кабинете, обновить все экземпляры приложения и проверить server-to-server GET, затем отозвать старый. `VEDICWAY_OPERATIONS_TOKEN` меняется с коротким окном остановленных служебных операций. `VEDICWAY_DATA_KEY` нельзя заменить простым рестартом, поскольку им зашифрованы email и причины возвратов; сначала нужен отдельный скрипт re-encryption с резервной копией и проверкой чтения. `VEDICWAY_SIGNING_KEY` меняет валидность ранее выданных подписанных ссылок.

## Платёжный инцидент

Начать с purchase ID и trace ID, затем сопоставить `purchases`, `payment_events`, `payment_incidents`, `refunds` и `payment_operations`. В логах и тикете не размещать email, secret key, operations token или полный provider payload. Ручной SQL запрещён: reconcile и refund оставляют проверяемый audit, тогда как прямое изменение таблиц разрушает цепочку доказательств.

## PDF не собран

Проверить `PDF_RENDER_FAILED`, наличие Chromium и доступность packaged font. Повторить только `pdf_v1`: расчёт и текст заново не строятся. Если после трёх попыток PDF остаётся failed, веб-версия полного отчёта продолжает работать, а пользователю показывается действие повторной сборки.

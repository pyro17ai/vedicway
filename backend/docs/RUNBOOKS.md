# Runbooks VedicWay

## D1 failures выше 1% за 10 минут

Остановить intake только при недоступности ephemeris или повреждении адаптера. Сначала проверить `EPHEMERIS_MISSING`, `TIMEZONE_RESOLUTION_FAILED` и `CALCULATION_FAILED` в событиях jobs, затем выполнить golden-карту Москвы: 16.10.2006, 13:30, `ru-moscow-524901`, Лахири. Лагна должна остаться в Скорпионе 23.7133°. При расхождении не публиковать новые отчёты до фиксации версии PyJHora и Swiss Ephemeris.

## Очередь не двигается

Сверить число `queued` jobs и возраст самого старого `instant_v1`. Если worker остановлен, поднять отдельный worker-процесс, не перезапуская API. Повторять только `failed_retryable` через endpoint retry; `failed_terminal` сначала требует исправления причины. Outbox не очищать вручную: SSE и polling используют его для восстановления состояния.

## Поставщик объяснений недоступен или ответы не проходят validator

Проверить count `job_failure_total{job_type="interpretation_free_v1"}` и коды `INTERPRETATION_UNAVAILABLE`/`INTERPRETATION_INVALID`. Не отправлять в повтор свободный текст и не ослаблять validator. Сначала сверить immutable snapshot, checksum evidence и prompt version, затем включить только безопасный локальный fallback либо повторить тот же job с прежним evidence checksum.

## Webhook задержан или платёж не совпал

Redirect браузера не меняет entitlement. Проверить подпись, timestamp, `provider_event_id`, сумму 99000 и валюту RUB на стороне payment provider. Повтор webhook с тем же `provider_event_id` безопасен, поскольку таблица payment_events делает его idempotent. При mismatch не выдавать доступ и создать incident: этот код не должен автоматически исправляться повтором браузерного запроса.

## PDF не собран

Проверить `PDF_RENDER_FAILED`, наличие Chromium и доступность packaged font. Повторить только `pdf_v1`: расчёт и текст заново не строятся. Если после трёх попыток PDF остаётся failed, веб-версия полного отчёта продолжает работать, а пользователю показывается действие повторной сборки.

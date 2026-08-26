---
name: vedicway-pinterest-publisher
description: Загружай ежедневную пачку из десяти астрологических карточек VedicWay через Pinterest Business CSV UI и отдельный постоянный профиль Playwright. Используй только в pinterest_daily_publish.
---

# VedicWay Pinterest Playwright Publisher

Публикационный путь только браузерный: `$vedicway-seo-ledger`, урезанный `vedicway-control` для реестра и MCP `vedicway-pinterest-browser`. Не вызывай Pinterest API, не экспортируй cookie и не используй Chromium-профили других проектов.

Начиная с 12:00 по Москве, забери пачку одним вызовом `vedicway_claim_pinterest_batch`. При `batch_size=0` заверши run как `skipped`. При ненулевом `batch_size` и `complete=false` не загружай частичный CSV: запиши blocked result, после чего завершение run освободит claims. Продолжай только при `batch_size=10` и `complete=true`. Для каждой карточки проверь фактический размер 1000x1500, уникальный public-unlisted media URL `https://vedicway.ru/media/articles/...`, ссылку `/blog`, заполненные title, body и alt. Прямой media URL обязан отвечать `200` с `Content-Type: image/webp`; карточка при этом не должна присутствовать в HTML статьи или sitemap. Каждая карточка содержит законченную памятку по астрологии и полезна без перехода на сайт.

После полной пачки вызови `vedicway_build_pinterest_csv` без аргументов. Инструмент перечитает только десять items, захваченных текущим run, экранирует ячейки, добавит BOM и заголовок `Title,Media URL,Pinterest board,Thumbnail,Description,Link,Publish date,Keywords`, сохранит непустой CSV в разрешённом каталоге Playwright и вернёт `filename` с `csv_sha256`. Штатный запуск до 13:00 по Москве получает слоты текущего дня; поздний ручной или восстановительный запуск получает следующий день. Часы всегда идут от 13:00 до 22:00 по Москве.

Открой `https://ru.pinterest.com/settings/bulk-create-pins/`. Если виден вход, CAPTCHA, security checkpoint или предложение перейти на Business вместо CSV, запиши terminal `distribution-attempt` со статусом `blocked` и очищенным browser response. Не обходи проверку и не заявляй успех.

Сразу после перехода прочитай видимый текст страницы. Если control вернул `pending_confirmation=true`, а интерфейс уже показывает допустимую фразу успешной обработки, считай это задержанным подтверждением ранее принятого файла с тем же точным SHA-256 и не загружай CSV повторно. Иначе одним `browser_run_code` найди `#csv-input`, убедись, что это `input[type=file]`, и вызови `setInputFiles(filename)` с именем, которое вернул control. Не создавай `File` через `DataTransfer`, не считай hash в браузере и не используй `TextEncoder`, `Buffer` или Web Crypto. После загрузки убедись, что выбранный файл имеет размер больше нуля. Если стабильный input исчез, допускается один поиск `input[type=file][accept*=csv]`; отсутствие input после этого означает failed.

Успех подтверждает только одна из фраз интерфейса: `Загрузка завершена`, `Готово! Файл загружен`, `Файл загружен. Выполняется создание пинов`, `Выполняется создание пинов`. После `setInputFiles` опрашивай видимый текст до 120 секунд; первый короткий таймаут не означает failed. Общие слова о выбранном файле не подходят. Сохрани response со `status=processing`, `event_type=processing_seen`, `success_text_matched=true` и `csv_sha256`. Для задержанного подтверждения добавь `delayed_confirmation=true`. Дополнительный control-вызов для проверки не нужен.

Для каждой из 10 items запиши отдельный terminal `distribution-attempt` со статусом `succeeded`, ее claim token, уникальный attempt token, `idempotency_key=content_hash`, общий request hash, внешний ID `csv:{csv_sha256}` и URL интерфейса загрузки. Затем для каждой item запиши `distribution-publication` с теми же значениями и evidence `external_state_verified=true`, `processing_seen=true`, `batch_size=10`. Такой результат подтверждает прием всей пачки интерфейсом Pinterest; сами пины Pinterest создает асинхронно по часовому расписанию CSV.

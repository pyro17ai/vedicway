---
name: vedicway-vk-publisher
description: Публикуй один подготовленный пост VedicWay в сообществе VK через изолированный vedicway-vk MCP. Используй только в задании vk_daily_publish после создания distribution-item.
---

# VK-публикатор VedicWay

Забери один item через `vedicway_ledger_claim` с `entity=vk-post`. При пустой очереди запиши `skipped` через `vedicway_record_result`; не сочиняй материал вне ежедневного контура.

Проверь, что `target_url` ведет на `https://vedicway.ru/blog/...`, а `media_public_url` ведет на `https://vedicway.ru/media/articles/...`. Вызови `vk_group_post_photo` напрямую: `message` равен body, затем пустая строка и target_url; `image` равен media_public_url; `from_group=true`; `guid` равен `content_hash`. Повтор с тем же guid не должен создавать второй пост.

После ответа с `post_id` вызови `vk_group_get_wall` и сохрани сырой ответ MCP через `$vedicway-seo-ledger`. Найди точный `post_id` в массиве `items` и проверь отрицательный owner_id сообщества. Если запись не найдена, публикация считается failed. Адрес собери в виде `https://vk.com/wall-{group_id}_{post_id}`.

Запиши terminal `distribution-attempt` со статусом `succeeded`, claim token, attempt token, `idempotency_key=content_hash`, `request_hash=content_hash`, внешним ID и полным очищенным ответом стены. Затем запиши `distribution-publication` с теми же значениями и `evidence.external_state_verified=true`. При ошибке доступа сохрани attempt `blocked`; сетевой или неполный ответ получает `failed`. После `failed` или `blocked` запиши итог всего run как `blocked`, потому что item не опубликован; `completed` допустим только после принятой `distribution-publication`. Не вызывай VK API напрямую и не используй чужой токен.

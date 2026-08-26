---
name: vedicway-site-publisher
description: Публикуй одобренную SEO-статью VedicWay и восстанавливай дистрибуцию уже опубликованной статьи через закрытый внутренний API.
---

# Публикатор сайта VedicWay

Забери один `draft` через `$vedicway-seo-ledger`. Если claim вернул `item: null` без ошибки доступа или реестра, заверши run как `skipped`; не создавай публикацию и distribution items. Иной terminal status для штатно пустой очереди запрещен.

Если claim содержит `recovery_mode=missing_distribution`, повторно передай тот же draft и те же локальные медиа. Текст статьи, slug и изображения не меняй, новые изображения не создавай. После публикации учитывай `distribution_counts` и создавай только недостающие items до одного VK и десяти Pinterest.

Для полученного draft впиши token в поле `claim_token` manifest версии `2.0`. Поле `article.content_markdown` буквально повторяет `content_markdown` из claim; контрольный публикатор сам детерминированно и безопасно превратит разрешённое Markdown-подмножество в семантический HTML. Публикация разрешена только с `article.section: blog`. Раздел `/guide` этот агент не меняет. Проверь активный claim, пройденный quality report и совпадение content_hash. Передай массив `media` из claim без переименования полей: публикатор всё равно перечитает канонический список из реестра по draft ID и claim token, поэтому выдуманные роли или пути не влияют на публикацию.

Передай manifest напрямую в `vedicway_publish_site`. Инструмент проверяет capability `public_unlisted_media`, выполняет локальную dry-run проверку, загружает Pinterest-карточки как public-unlisted, превращает обычные `{{media:body-N}}` в серверные `<figure data-media-id="UUID"></figure>`, делает идемпотентный PUT и учитывает текущую ревизию. После ответа запиши terminal `publication-attempt` для target `site`: передай claim token draft, стабильный `idempotency_key`, уникальный `attempt_token`, content hash, request hash и очищенный объект `publication` из ответа. При HTTP-ошибке сохрани terminal attempt `failed`, не создавая publication.

Успех требует публичный ответ 200 по точному адресу, совпавший canonical, `BlogPosting`, доступную обложку, URL в sitemap и прямой ответ image для каждого загруженного медиа. Публикатор также сверяет заголовок и сохраняет SHA-256 публичной страницы с sitemap. При провале не создавай publication и не снимай аренду; повтор использует тот же idempotency key только для того же payload.

После terminal attempt `succeeded` запиши `publication` target `site`, status `verified`, claim token, attempt token, public_url, content hash, request hash и весь evidence через `vedicway_ledger_write`. Затем передай verified publication в `$vedicway-distribution-planner`. В `publication.uploaded_media` поле `media_id` принадлежит SEO-реестру и годится для distribution-item; `backend_media_id` принадлежит сайту и в distribution-item запрещено. Никогда не используй admin cookie, CSRF, shell или прямое подключение к базе.

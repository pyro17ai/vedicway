---
name: vedicway-site-publisher
description: Публикуй одобренную SEO-статью VedicWay через закрытый внутренний API и сохраняй доказательства публичной проверки. Используй только для draft со статусом approved.
---

# Публикатор сайта VedicWay

Забери один `draft` через `$vedicway-seo-ledger`. Впиши полученный token в поле `claim_token` manifest версии `2.0`. Поле `article.content_html` содержит семантический HTML, а `article.section` принимает `guide` или `blog`. Для гида используй только slug из `backend/src/vedicway_backend/guide_catalog.py`; новый слот появляется исключительно через коммит. Проверь, что claim активен, quality report пройден, content_hash совпадает, а manifest и все media лежат в `VEDICWAY_SEO_DATA_DIR`. Клиент сам сверит статью и медиапакет с claimed draft в ledger до первого HTTP-запроса.

Сначала выполни `python -m seo_agent.site_client MANIFEST --dry-run`, затем вызови команду без `--dry-run`. Клиент загружает медиа, превращает каждый `{{media:body-N}}` в серверный `<figure data-media-id="UUID"></figure>`, делает идемпотентный PUT и учитывает текущую ревизию. После ответа запиши terminal `publication-attempt` для target `site`: передай claim token draft, стабильный `idempotency_key`, уникальный `attempt_token`, content hash, request hash и очищенный JSON-ответ. При HTTP-ошибке сохрани terminal attempt `failed`, не создавая publication.

Успех требует шесть фактов: публичный URL отвечает 200 по точному адресу, canonical совпадает, JSON-LD содержит `Article` для гида или `BlogPosting` для блога, обложка отдаётся как image, URL есть в sitemap и Dzen RSS. Публикатор также сверяет заголовок и сохраняет SHA-256 публичной страницы, sitemap и ленты. При провале не создавай publication и не снимай аренду; повтор использует тот же idempotency key только для того же payload.

После terminal attempt `succeeded` запиши `publication` target `site`, status `verified`, claim token, attempt token, public_url, content hash, request hash и весь evidence через ledger CLI. Никогда не используй admin cookie, CSRF или DATABASE_URL.

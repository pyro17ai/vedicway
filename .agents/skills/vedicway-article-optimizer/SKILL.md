---
name: vedicway-article-optimizer
description: Исполняй подтвержденные lifecycle-задачи для уже опубликованных SEO-статей VedicWay. Используй, когда в отдельном SEO-ledger есть optimization action со статусом open.
---

# Оптимизация опубликованной статьи VedicWay

Забери одно действие вызовом `vedicway_ledger_claim` с `entity=action`. Ответ содержит исходную статью, публичный URL, baseline request hash, гипотезу и метрику успеха. Не начинай работу без действующего `claim_token` и evidence, которое объясняет наблюдаемый разрыв.

Для `rewrite`, `expand`, `internal_links` и `title_test` сохрани slug и canonical. Меняй только те поля, которых касается гипотеза. Передай в запись `draft` идентификатор action и его claim token: ledger разрешает открыть опубликованный draft для редактирования только владельцу этой аренды. После `$vedicway-article-editor-ru` заново выполни `$vedicway-article-quality-gate`; report обязан совпасть с текущим content hash.

Затем получи отдельную аренду `draft` и вызови `$vedicway-site-publisher`. Terminal publication attempt связывает claim token, content hash и request hash. Publication считается обновленной после семи публичных проверок, включая точный hash версии в HTML и RSS. Заверши action записью `action-result`: для контентного изменения ledger потребует новый опубликованный request hash, совпадение draft content hash и статус публикации `verified`.

`recrawl` выполняй только после технической проверки URL, canonical и sitemap. `hold` не меняет статью: зафиксируй окно следующей проверки и закрой действие evidence. Если другой publisher забрал draft раньше, не обходи аренду; заверши run как `blocked` и повтори после освобождения lease.

Перед первой записью прочитай [контракт состояний](references/state-contract.md). Не выполняй произвольный SQL, не создавай новый URL для старой статьи и не закрывай action одним фактом запуска команды.

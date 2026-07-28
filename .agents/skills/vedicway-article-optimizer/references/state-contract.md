# Контракт оптимизации

`claim action` возвращает `id`, `claim_token`, `action_type`, `publication_id`, `draft_id`, `brief_id`, `slug`, поля текущей статьи, `published_content_hash`, `published_request_hash`, гипотезу и метрику успеха.

Обновленный `draft` повторяет обычный контракт writer и дополнительно содержит `action_id` и `action_claim_token`. `draft-quality.report.passed` и `draft-quality.report.content_hash` должны буквально совпасть с записываемым исходом и текущим draft.

Terminal `publication-attempt` содержит `draft_id`, `target=site`, `claim_token`, стабильный `idempotency_key`, уникальный `attempt_token`, `status`, `content_hash`, `request_hash` и очищенный `response`. `publication` повторяет `claim_token`, `attempt_token`, оба hash и объект `evidence.checks` с истинными `canonical`, `article_schema`, `title`, `request_hash`, `sitemap`, `dzen_feed`, `cover`.

`action-result` содержит `action_id`, исходный action `claim_token`, статус `completed` или `rejected` и объект evidence. Контентные типы нельзя завершить, пока request hash проверенной site-публикации равен baseline.

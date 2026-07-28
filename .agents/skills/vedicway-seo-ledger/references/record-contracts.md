# Контракт `seo_agent.cli write`

Команда читает один JSON-объект из `--json-file`; без файла она читает одну строку stdin. Значения секретов запрещены во всех payload.

Поддерживаемые типы: `source-document`, `tool-response`, `query`, `serp-snapshot`, `cluster`, `brief`, `draft`, `draft-quality`, `media`, `publication-attempt`, `publication`, `performance`, `action`, `action-result`.

`serp-snapshot` требует существующий `query_id`, тот же `region_id`, непустой массив `results`, время запроса и SHA-256 канонического JSON результатов. Повтор того же query/time допустим только при неизменном checksum.

`brief` требует `cluster_id`, действующий `claim_token`, `title`, `primary_query`, `audience_problem`, `search_intent`, 4-8 разделов `outline`, минимум две записи `evidence`, минимум две `internal_links`, непустой `prohibited_claims` и SHA-256 канонического JSON этих восьми содержательных полей.

`draft` требует `brief_id`, `slug`, `title`, `excerpt`, `content_markdown`, `seo_title`, `meta_description`, `focus_keyphrase`, `category`, точный SHA-256 `content_hash`. Для изменения опубликованного draft нужны `action_id` и действующий `action_claim_token`. `draft-quality` принимает `draft_id`, boolean `passed` и объект `report`; report outcome и content hash должны совпасть буквально. Для `passed=true` объект `manual_checks` содержит только истинные `brief_alignment`, `evidence_verified`, `originality_reviewed`, `prohibited_claims_reviewed`.

`publication-attempt` требует `draft_id`, target `site` или `dzen`, `claim_token` для сайта, стабильный `idempotency_key`, уникальный `attempt_token`, terminal status, `content_hash`, `request_hash`, объект `response`. Тот же idempotency key можно повторить только с теми же hash. `publication` допустим после конкретного attempt со статусом `succeeded`; обязательны `claim_token`, `attempt_token`, `draft_id`, `target`, `public_url`, оба hash и объект `evidence`.

`action-result` требует `action_id`, действующий `claim_token`, статус `completed` или `rejected` и evidence. Контентное действие завершится только после verified site-публикации с новым request hash.

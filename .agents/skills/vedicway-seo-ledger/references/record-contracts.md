# Контракт `seo_agent.cli write`

Команда читает один JSON-объект из `--json-file`; без файла она читает одну строку stdin. Значения секретов запрещены во всех payload.

Поддерживаемые типы: `source-document`, `tool-response`, `query`, `serp-snapshot`, `cluster`, `brief`, `draft`, `draft-quality`, `media`, `publication-attempt`, `publication`, `performance`, `action`, `action-result`, `distribution-item`, `distribution-attempt`, `distribution-publication`.

Короткий лог run не относится к `ledger_write`. Запиши его отдельным инструментом `vedicway_record_run_log`, передав единственное поле `log_text` длиной до 4000 символов. Для одного `cron_run` принимается ровно одна запись в `seo_agent.run_logs`.

`tool-response` требует `provider`, `tool_name`, `request_hash` и исходный JSON в `response`. Допустимые внешние provider: `yandex-search`, `wordstat`, `webmaster`, `metrika`, `site`, `dzen`, `vk`, `pinterest`; формы `yandex_search`, `yandex_wordstat`, `yandex_webmaster`, `yandex_metrika` нормализуются автоматически. Ответы `vedicway-control` сюда не записываются.

`serp-snapshot` требует существующий `query_id`, тот же `region_id`, непустой массив `results` и время запроса. Не передавай `checksum`: реестр сам вычисляет SHA-256 канонического JSON и возвращает его. Повтор того же query/time допустим только при неизменных результатах.

`brief` требует `cluster_id`, действующий `claim_token`, `title`, `primary_query`, `audience_problem`, `search_intent`, 4-8 разделов `outline`, минимум две записи `evidence`, минимум две `internal_links` и непустой `prohibited_claims`. Поле `checksum` не передавай: реестр вычисляет и возвращает его.

`draft` требует `brief_id`, `slug`, `title`, `excerpt`, `content_markdown`, `seo_title`, `meta_description`, `focus_keyphrase` и `category`. Поле `content_hash` не передавай: реестр вычисляет SHA-256 точного текста и возвращает его. Для изменения опубликованного draft нужны `action_id` и действующий `action_claim_token`. `draft-quality` принимает `draft_id`, boolean `passed` и объект `report`; report outcome и возвращенный content hash должны совпасть буквально. Для `passed=true` объект `manual_checks` содержит только истинные `brief_alignment`, `evidence_verified`, `originality_reviewed`, `prohibited_claims_reviewed`.

`publication-attempt` требует `draft_id`, target `site` или `dzen`, `claim_token` для сайта, стабильный `idempotency_key`, уникальный `attempt_token`, terminal status, `content_hash`, `request_hash`, объект `response`. Тот же idempotency key можно повторить только с теми же hash. `publication` допустим после конкретного attempt со статусом `succeeded`; обязательны `claim_token`, `attempt_token`, `draft_id`, `target`, `public_url`, оба hash и объект `evidence`. Site evidence требует `all_media_public=true`; Dzen evidence требует `cover_present=true` вместе с повторной проверкой редактора и публичного URL.

`action-result` требует `action_id`, действующий `claim_token`, статус `completed` или `rejected` и evidence. Контентное действие завершится только после verified site-публикации с новым request hash.

`media` требует принадлежащий draft, `purpose`, путь внутри `VEDICWAY_SEO_DATA_DIR`, alt, source kind, license note и SHA-256 файла. Pinterest-карточка дополнительно получает `distribution_role=pinterest`; реестр сам читает фактический размер и принимает только 1000x1500.

`distribution-item` требует verified `source_publication_id`, пару platform/kind (`vk/article_digest` либо `pinterest/astrology_card`), title, body, точный blog target URL, фактические media dimensions и alt. VK использует `media_role=cover`; Pinterest передает явный `media_id` карточки и `media_role=pinterest`. Возвращенный `content_hash` служит idempotency key.

`distribution-attempt` требует `item_id`, действующий claim token, уникальный attempt token, `idempotency_key=content_hash`, terminal status, request hash и очищенный response. Для succeeded нужны external ID и HTTPS URL. `distribution-publication` повторяет item, claim, attempt, request hash, внешний ID/URL и `evidence.external_state_verified=true`.

`performance` требует publication ID, одинаковое окно `window_start`/`window_end` и отдельные JSON `webmaster` и `metrika`. `action` требует verified site publication, допустимый action type, одну гипотезу, success metric и evidence.

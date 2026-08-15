---
name: vedicway-seo-ledger
description: Веди реестр SEO-агента VedicWay в отдельной схеме PostgreSQL через типизированный CLI. Используй в начале и конце каждого cron-run, при аренде кластера, сохранении сырого ответа MCP, брифа, статьи, публикации, метрик или задачи на оптимизацию.
---

# SEO-реестр VedicWay

Этот Skill задает единственную границу записи служебного состояния. Работай только через CLI и не выполняй произвольный SQL над схемой `seo_agent`.

## Обязательный порядок

1. Проверь реестр командой `python -m seo_agent.cli init`, затем `python -m seo_agent.cli health`. Подключение берется из `VEDICWAY_SEO_DATABASE_URL`, `DATABASE_URL` или `VEDICWAY_DATABASE_URL`.
2. Scheduler уже создал `cron_run` и передал `VEDICWAY_SEO_RUN_ID`. Для эксклюзивной работы вызови `python -m seo_agent.cli claim cluster`, `claim draft` или `claim action`. Сохрани `claim_token`; без него нельзя превратить кластер в бриф.
3. Каждый ответ Yandex MCP сначала запиши как `tool-response`, затем извлекай запросы или метрики. Для всех остальных сущностей используй `python -m seo_agent.cli write TYPE --json-file FILE`.
4. Заверши run ровно одной командой `record-result`. Для `completed` обязательно передай `--artifact-json` с идентификаторами созданных записей или подтвержденной публикацией; пустой объект отклоняется. `skipped` допустим только при доказанном отсутствии готовых сущностей. Недостающие доступы дают `blocked` с именами секретов без их значений.

## Запреты

Не изменяй таблицы через Python REPL, `psql` или GUI. Не меняй terminal-состояние публикации задним числом. Не переиспользуй `attempt_token`, `idempotency_key` или просроченный `claim_token`. Не записывай токены, cookie, персональные данные и полные HTTP-заголовки.

Перед записью сущностей прочитай [контракт записей](references/record-contracts.md).

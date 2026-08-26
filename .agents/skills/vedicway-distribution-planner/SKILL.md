---
name: vedicway-distribution-planner
description: Готовь один ежедневный материал для VK и десять Pinterest-карточек из проверенной публикации блога VedicWay. Используй после успешной site publication, до отдельных заданий публикации в соцсетях.
---

# Планировщик дистрибуции VedicWay

Работай только с публикацией `target=site`, `status=verified` и URL вида `https://vedicway.ru/blog/{slug}`. Получи `publication_id` из результата `$vedicway-site-publisher`. Не читай PostgreSQL напрямую.

## VK

Подготовь один `distribution-item` с `platform=vk`, `kind=article_digest` и `media_role=cover`. Сожми главный практический вывод статьи в 300-900 знаков, не добавляя новых фактов. Заверши текст до ссылки: публикатор добавит URL отдельной строкой. Передай фактические размеры обложки 1200x630 и содержательный alt.

## Pinterest

Подготовь ровно 10 `distribution-item` с `platform=pinterest`, `kind=astrology_card` и `media_role=pinterest`. Каждая item обязана передавать явный канонический `media_id` своей вертикальной памятки 1000x1500 из `publication.uploaded_media`; `backend_media_id` для этого поля не подходит. Карточка публикуется как public-unlisted и в HTML статьи не входит. Не повторяй media ID, заголовок, описание или alt внутри пачки. Заголовок называет конкретный навык, порядок или памятку. Описание объясняет пользу карточки без прогнозов и обещаний. Укажи `metadata.topic_scope=astrology-education` и точный alt.

Для каждой item вызови `vedicway_ledger_write` с `record_type=distribution-item` и готовым объектом `payload`. Промежуточные файлы и shell-команды не используй.

Повтор с тем же содержимым обязан вернуть прежний item. В recovery-run учитывай `distribution_counts` и существующие `distribution_items`: создавай только отсутствующую часть. Заверши run, когда у site publication есть один durable ID VK и десять Pinterest.

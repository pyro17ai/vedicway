---
name: vedicway-pinterest-card-image
description: Генерируй самостоятельные обучающие Pinterest-карточки VedicWay через встроенный Image Gen в Codex. Используй для ежедневной пачки из десяти карточек.
---

# Pinterest-карточка VedicWay

Сначала примени `$vedicway-create-image` вместе с системным `$imagegen`. Для каждой карточки сделай отдельный вызов встроенного `image_gen`, проверь текст и затем вызови `vedicway_import_generated_image` с `kind=pinterest-card` и путём `media/{draft_id}-pin-{index}.webp`. Если встроенный инструмент не вернул `source_path`, передай только `kind` и `output`: control найдёт свежий, ещё не импортированный файл текущего run. В prompt передай точный заголовок и короткий проверенный совет по астрологии, попроси крупную русскую типографику, вертикальную инфографику и свободные поля. Карточка обязана быть понятной без перехода на статью. Запрещены чужие логотипы, водяные знаки и выдуманные факты.

Сделай ровно десять отдельных встроенных вызовов, по одному на финальную карточку; исправление через дополнительный вызов допустимо, но брак не сохраняй. Прими результат только при `generator=codex-imagegen`, размере 1000x1500 и уникальном SHA-256. Каждую картинку запиши как distribution-only body media с `distribution_role=pinterest`, `source_kind=generated` и `license_note=Generated for VedicWay with Codex Image Gen`; placeholder в HTML статьи не добавляй.

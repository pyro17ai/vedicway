---
name: vedicway-article-cover-image
description: Генерируй одну обложку статьи VedicWay через встроенный Image Gen в Codex. Используй при подготовке нового материала или обоснованном обновлении обложки.
---

# Обложка статьи VedicWay

Сначала примени `$vedicway-create-image` вместе с системным `$imagegen`. Создай обложку отдельным вызовом встроенного `image_gen`, затем вызови `vedicway_import_generated_image` с `kind=article-cover` и уникальным путём `media/{draft_id}-cover.webp`. Если встроенный инструмент не вернул `source_path`, передай только `kind` и `output`: control найдёт свежий файл текущего run. Prompt должен описывать тему статьи, спокойную ведическую эстетику и широкую композицию с читаемым центром. Текст на обложке не обязателен; если он нужен, передай точную короткую строку и потребуй воспроизвести её без изменений.

Прими результат только при `generator=codex-imagegen`, размере 1200x630 и непустом SHA-256. Запиши одну cover media с осмысленным alt, `source_kind=generated` и `license_note=Generated for VedicWay with Codex Image Gen`.

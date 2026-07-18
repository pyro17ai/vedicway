# VedicWay backend

Сервис реализует путь от формы рождения до вычисленного снимка D1, бесплатных объяснений, тестовой оплаты и PDF. Для вычислений он импортирует собственный пакет `pyjhora_mcp`; астрологические формулы в этот репозиторий не копируются.

## Локальный запуск

Укажите путь к исходникам собственного PyJHora MCP и используйте Python 3.11 из его виртуального окружения:

```powershell
$env:PYTHONPATH = "D:\CODEX_WORK\VedicWay\backend\src"
$env:VEDICWAY_PYJHORA_SOURCE = "C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\src"
$env:VEDICWAY_TEST_PAYMENTS = "1"
C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\.venv311\Scripts\python.exe -m uvicorn vedicway_backend.main:app --host 127.0.0.1 --port 8000
```

`VEDICWAY_TEST_PAYMENTS=1` открывает только локальный тестовый провайдер. Production-процесс принимает реальный payment adapter по конфигурации и не подтверждает оплату браузерным query-параметром.

Для production также задайте `VEDICWAY_PLACE_DATASET_PATH`: это путь к лицензированному JSON-справочнику городов, который хранится рядом с приложением. Каждая запись содержит `place_id`, отображаемое имя, код страны, координаты, IANA `tzid` и необязательный массив `alternate_names`. Бэкенд не отправляет поисковый запрос в публичный геокодер; без этого файла production-процесс не стартует.

## Границы

- SQLite используется для локального runnable-контура. Миграция PostgreSQL лежит в `migrations/001_chart_result.sql` и повторяет production-модель из спецификации.
- `DevelopmentInterpretationProvider` создаёт проверяемые локальные тексты для разработки. `CodexExecProvider` реализован как изолированный one-shot adapter и включается только конфигурацией в контейнере без пользовательского `CODEX_HOME`.
- PDF создаёт Node/Playwright worker через `scripts/render_pdf.mjs`. Он строит HTML из экранированных строк и SVG D1, без model HTML и внешней сети.

# VedicWay backend

Сервис реализует путь от формы рождения до вычисленного снимка D1, бесплатных объяснений, тестовой оплаты и PDF. Для вычислений он импортирует собственный пакет `pyjhora_mcp`; астрологические формулы в этот репозиторий не копируются.

## Локальный запуск

Для локального интерфейса с настоящими персональными объяснениями запускайте готовый изолированный контур. Первый запуск копирует только файл авторизации в отдельный `CODEX_HOME`; пользовательские настройки, skills, MCP, память и рабочие файлы runner не видит:

```powershell
.\scripts\Start-VedicWayCodexBackend.ps1 -Port 8015 -BootstrapAuthFromCurrentUser
```

Следующие запуски не требуют bootstrap-флага:

```powershell
.\scripts\Start-VedicWayCodexBackend.ps1 -Port 8015
```

Скрипт находит настоящий `codex.exe`, потому что npm-обёртку `codex.cmd` нельзя безопасно запустить через `subprocess` с `shell=False`. Он создаёт пустой read-only workdir в `%LOCALAPPDATA%\VedicWay\codex-runner`, включает `VEDICWAY_INTERPRETATION_PROVIDER=codex` и хранит локальную БД отдельно от основной рабочей копии.

Для запуска только расчётного контура без персонального текста укажите путь к исходникам собственного PyJHora MCP и используйте Python 3.11 из его виртуального окружения:

```powershell
$env:PYTHONPATH = "D:\CODEX_WORK\VedicWay\backend\src"
$env:VEDICWAY_PYJHORA_SOURCE = "C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\src"
$env:VEDICWAY_TEST_PAYMENTS = "1"
$env:VEDICWAY_INTERPRETATION_PROVIDER = "stub" # только локальные контрактные тесты
C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\.venv311\Scripts\python.exe -m uvicorn vedicway_backend.main:app --host 127.0.0.1 --port 8000
```

`VEDICWAY_TEST_PAYMENTS=1` открывает только локальный тестовый провайдер. Production-процесс принимает реальный payment adapter по конфигурации и не подтверждает оплату браузерным query-параметром.

Для production также задайте `VEDICWAY_PLACE_DATASET_PATH`: это путь к лицензированному JSON-справочнику городов, который хранится рядом с приложением. Каждая запись содержит `place_id`, отображаемое имя, код страны, координаты, IANA `tzid` и необязательный массив `alternate_names`. Бэкенд не отправляет поисковый запрос в публичный геокодер; без этого файла production-процесс не стартует.

## Границы

- SQLite используется для локального runnable-контура. Миграция PostgreSQL лежит в `migrations/001_chart_result.sql` и повторяет production-модель из спецификации.
- `DevelopmentInterpretationProvider` служит только явным контрактным stub в тестах. Рабочий процесс не подставляет его при сбое: D1 остаётся доступной, а вкладка объяснений получает локальную retryable-ошибку. `CodexExecProvider` делает до двух one-shot вызовов: основной и один repair после schema/semantic validation.
- PDF создаёт Node/Playwright worker через `scripts/render_pdf.mjs`. Он строит HTML из экранированных строк и SVG D1, без model HTML и внешней сети.

# VedicWay

VedicWay — веб-сервис для расчёта ведической натальной карты и подготовки персонального объяснения. Frontend работает на React и Vite, backend — на FastAPI с PostgreSQL, расчётным контуром PyJHora и отдельным SEO-агентом.

## Что находится в репозитории

- `src/` — интерфейс расчёта карты, рабочее пространство результата, юридические страницы и платный доступ.
- `backend/` — API, расчёты, хранение карт и отчётов, платежи, восстановление доступа и фоновые задачи.
- `content/` и `public/` — статьи гида, SEO-страницы, карта сайта и публичные данные.
- `seo_agent/` — контур публикации и аналитики SEO в отдельной схеме PostgreSQL.
- `docker/`, `compose.production.yml` и `deploy/` — production-сборка и конфигурация reverse proxy.

## Быстрый старт frontend

Требуются Node.js 22 и npm.

```powershell
npm ci
npm run dev
```

Проверки frontend выполняются командами:

```powershell
npm run test:run
npm run build
npm run check:seo
```

`npm run build` собирает Vite-приложение и пререндерит публичные SEO-страницы. `npm run check:seo` проверяет маршруты, метаданные, sitemap и опубликованный корпус статей.

## Локальный backend

Backend использует PostgreSQL. SQLite-контур для приложения больше не поддерживается. Установите Python 3.11 и создайте окружение:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Перед запуском задайте URL локальной PostgreSQL-базы и примените миграции:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://vedicway:password@127.0.0.1:5432/vedicway"
$env:VEDICWAY_DATABASE_URL = $env:DATABASE_URL
$env:TEST_DATABASE_URL = $env:DATABASE_URL

.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
cd ..
.\backend\.venv\Scripts\python.exe -m pytest backend/tests seo_agent/tests
```

Для запуска API из корня репозитория:

```powershell
$env:PYTHONPATH = "D:\VedicWay\backend\src"
.\backend\.venv\Scripts\python.exe -m uvicorn vedicway_backend.main:app --host 127.0.0.1 --port 8000
```

## Production

Production запускается через `compose.production.yml`. Скопируйте `.env.production.example` в `.env.production`, заполните конфигурацию и создайте secret-файлы по инструкции. Настоящие ключи, токены, пароли и файл авторизации Codex нельзя добавлять в Git.

Подробные инструкции:

- [Production deployment](docs/PRODUCTION_DEPLOYMENT_RU.md)
- [Контент и юридические страницы](docs/PRODUCTION_CONTENT_LEGAL_RUNBOOK_RU.md)
- [SEO-agent](docs/SEO_AGENT_PRODUCTION_RU.md)
- [Восстановление и хранение данных](docs/RECOVERY_RETENTION_RUNBOOK_RU.md)

## Данные и лицензии

Расчётный контур использует PyJHora и Swiss Ephemeris, а справочник мест — GeoNames. Источники и лицензии перечислены в [`public/data-sources.txt`](public/data-sources.txt). Лицензированные исходники и wheelhouse подключаются на этапе production-сборки и не заменяют проверку лицензий перед выпуском.

## Безопасность

Файлы `.env.production`, `.env.local` и содержимое `secrets/*.txt` исключены из Git. Перед публикацией проверяйте staged-дерево командой `git diff --cached --check` и не добавляйте в коммит реальные credentials.

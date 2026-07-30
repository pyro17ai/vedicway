# Публикация статей через Codex

Сайт принимает UTF-8 HTML только через закрытый контентный шлюз. Для гида разрешены 202 адреса из `backend/src/vedicway_backend/guide_catalog_data.json`; они сгруппированы в четыре раздела и меняются только коммитом. Блог принимает новые корректные slug без правки каталога.

Исходник статьи лежит в `content/astrology-guide/articles/{slug}`: `article.html` без H1 и внешней оболочки, `manifest.json`, `sources.json`, Markdown-копия и `cover.webp`. Manifest хранит раздел, уровень сложности, canonical, поисковые поля и дополнения Schema.org. Сервер очищает HTML, создаёт responsive WebP, добавляет H1, хлебные крошки, два CTA, прогресс чтения, комментарии и три разные рекомендации.

Корпус из worktree подготавливается одной воспроизводимой командой:

```powershell
uv run --project backend python scripts/prepare_astrology_guide.py `
  --source D:\VedicWay\VedicWay-work3\content\astrology-guide
```

Перед публикацией Codex запускает полный сухой прогон. Он проверяет 202 canonical, уникальные SEO title, meta description и focus keyphrase, все внутренние ссылки, обложки от 1200×630 и совпадение manifest с кодовым каталогом:

```powershell
uv run --project backend python scripts/publish_astrology_guide.py
```

После проверки агент задаёт `VEDICWAY_SEO_AGENT_TOKEN` и адрес backend. Флаг `--publish` идемпотентно загружает все обложки и статьи, затем открывает каждую публичную статью, проверяет JSON-LD, sitemap, CTA, рекомендации и фактическую выдачу WebP:

```powershell
$env:VEDICWAY_SEO_AGENT_BASE_URL = "https://vedicway.ru"
$env:VEDICWAY_SEO_AGENT_TOKEN = "<секрет не короче 32 байт>"
uv run --project backend python scripts/publish_astrology_guide.py --publish
```

Одиночная статья отправляется через `PUT /internal/content-agent/guide/articles/{slug}` или `PUT /internal/content-agent/blog/articles/{slug}`. Обложка и иллюстрации сначала проходят через `POST /internal/content-agent/media`; шлюз требует Bearer-токен, связанный с содержимым `Idempotency-Key`, `X-Content-SHA256` и актуальный `If-Match` при обновлении.

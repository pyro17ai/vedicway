# VedicWay: контракт изображений для статей

## Граница

Изображения загружает только Codex через `POST /internal/content-agent/media`. Браузерный редактор, административная сессия и локальный fallback удалены. Агент передаёт Bearer-токен, связанный с содержимым `Idempotency-Key`, SHA-256 файла и `multipart/form-data`.

Шлюз принимает JPEG, PNG, WebP или AVIF до 12 МБ и 40 млн пикселей. Он проверяет сигнатуру, повторно кодирует изображение в WebP без EXIF/GPS и создаёт варианты шириной 640, 960, 1280 и 1600 px без увеличения исходника. `storageKey` строится из серверного UUID, поэтому имя исходного файла не влияет на публичный путь.

Обязательные поля: `file`, `purpose=cover|body` и осмысленный `alt`. Поля `title` и `caption` необязательны. Production manifest хранит `source_kind`, `source_url` при наличии и точную `license_note`; `site_client` сверяет эти сведения с media ledger до загрузки.

## Использование

Одна статья получает одну обложку шириной не меньше 1200 px. Для иллюстрации текста Codex ставит отдельный `{{media:body-N}}` между верхнеуровневыми HTML-блоками. Публикатор заменяет placeholder на `<figure data-media-id="UUID"></figure>`, а backend связывает UUID только с media этой статьи.

Публичный рендер создаёт `<figure>`, `<img>` и `<figcaption>`, добавляет неизменные `width` и `height`, `srcset`, `sizes`, `loading="lazy"` и `decoding="async"`. Обложка получает `fetchpriority="high"`; внутренние иллюстрации загружаются лениво. URL имеет вид `/media/articles/{asset_uuid}/{width}.webp` и отдаётся с `Cache-Control: public, max-age=31536000, immutable`.

Сырой HTML может ссылаться только на локальные `/assets/*` и `/media/articles/*`. Внешний `img`, `data:`, SVG и исполняемые форматы очистит входной шлюз. Внешнюю картинку сначала нужно легально получить, записать происхождение в ledger и загрузить через media API.

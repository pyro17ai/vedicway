# Запуск админки, статей и правового контура VedicWay

## Что хранится где

SQLAlchemy-контур хранит в PostgreSQL пользователей, административные сессии, статьи, метаданные изображений и журнал согласий. Схему создаёт Alembic. Переменная `VEDICWAY_DATABASE_URL` действительно используется приложением; SQLite остаётся только локальным вариантом разработки.

Расчёты, задания, покупки, outbox и PDF пока обслуживает класс `Store` через зашифрованный SQLite-файл. Поэтому поддерживаемый production-профиль называется `single-node-sqlite`: один API/worker-процесс, один постоянный российский диск, резервное копирование всего `VEDICWAY_DATA_DIR`. Горизонтальное масштабирование и несколько worker-инстансов запрещены до переноса `Store` на PostgreSQL. Наличие SQL-файла `backend/migrations/001_chart_result.sql` само по себе не переключает runtime на PostgreSQL.

## Обязательные переменные

В production задаются реальные значения без заглушек:

```dotenv
VEDICWAY_ENV=production
VEDICWAY_PUBLIC_ORIGIN=https://vedicway.ru
VEDICWAY_PUBLIC_BASE_URL=https://vedicway.ru
VEDICWAY_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/vedicway
VEDICWAY_RUNTIME_PROFILE=single-node-sqlite
VEDICWAY_DATA_DIR=/srv/vedicway/runtime
VEDICWAY_MEDIA_DIR=/srv/vedicway/media
VEDICWAY_DATA_KEY=<Fernet key>
VEDICWAY_SIGNING_KEY=<random secret, at least 32 bytes>
VEDICWAY_LEGAL_OPERATOR_NAME=<реальный оператор>
VEDICWAY_LEGAL_OPERATOR_ADDRESS=<реальный адрес>
VEDICWAY_LEGAL_OPERATOR_INN=<реальный ИНН>
VEDICWAY_LEGAL_OPERATOR_OGRN=<реальный ОГРН или ОГРНИП>
VEDICWAY_PRIVACY_EMAIL=<рабочий адрес обращений субъектов>
VEDICWAY_OFFER_VERSION=<версия опубликованного пользовательского соглашения>
VEDICWAY_OFFER_URL=https://vedicway.ru/legal/user-agreement
VEDICWAY_PRIVACY_URL=https://vedicway.ru/legal/privacy-policy
```

Frontend получает `VITE_YANDEX_METRIKA_ID` во время production-сборки. Пререндер сохраняет публичный ID в meta-теге главной страницы и гида; meta-тег не загружает Метрику и нужен для строгой сверки release contract. Без согласия посетителя скрипт Метрики не загружается. Вебвизор выключен. CSP разрешает `yastatic.net` только в `script-src`, как требует внешний режим загрузки Метрики.

Reverse proxy должен отдавать `/sitemap.xml` из backend endpoint, потому что он включает только опубликованные статьи и обновляет `lastmod`. Файл `public/sitemap.xml` служит безопасным запасным вариантом для главной страницы и гида, но не заменяет динамическую карту сайта после публикации материалов.

Endpoint `/api/v1/health/ready` возвращает 503, пока отсутствуют реквизиты, PostgreSQL, явный single-node профиль или постоянные пути. Production также блокируется, если в окружении остался bootstrap-пароль администратора.

## Миграция и первый администратор

Перед запуском API выполняется миграция из каталога `backend`:

```powershell
uv sync --frozen --extra test
uv run alembic upgrade head
```

Первого администратора создаёт отдельный одноразовый процесс после миграции и до запуска API. Только этому процессу передаются `VEDICWAY_BOOTSTRAP_ADMIN_EMAIL`, `VEDICWAY_BOOTSTRAP_ADMIN_PASSWORD` длиной от 16 символов и `VEDICWAY_BOOTSTRAP_ADMIN_NAME`:

```powershell
uv run python -m vedicway_backend.bootstrap_admin
```

Команда проверяет Alembic revision, создаёт ровно одну запись с ролью `admin` и завершает работу; пароль хранится как Argon2id. Долгоживущие backend и frontend запускаются уже без bootstrap-переменных. Если пароль остался в их окружении, `/api/v1/health/ready` намеренно отвечает 503. Повторный one-shot с тем же email не меняет пароль и сообщает `admin_already_exists`.

Админка доступна по `/admin`. Сессия живёт 8 часов в HttpOnly Secure cookie с SameSite Strict. Все изменения статей и медиа требуют CSRF-токен и ту же origin. Обычная роль `user` получает 403.

## Изображения статей

Media API принимает JPEG, PNG, WebP и AVIF до 12 МБ. Файл декодируется, метаданные удаляются повторным кодированием в WebP, варианты 640, 960, 1280 и 1600 пикселей создаются без увеличения исходника. Файлы размещаются в `VEDICWAY_MEDIA_DIR/articles/<uuid>`, а в PostgreSQL хранится метадата. Удаление используемого статьёй файла отвечает 409.

Каталог `VEDICWAY_MEDIA_DIR` монтируется как постоянный том и резервируется вместе с базой. Публичный URL имеет вид `/media/articles/{asset_uuid}/{width}.webp`; API проверяет UUID и имя варианта. Reverse proxy направляет этот путь в backend либо раздаёт тот же каталог сам, сохраняя `Cache-Control: public, max-age=31536000, immutable`. Для media-контура обязательны постоянный `VEDICWAY_MEDIA_DIR` и совпадающий публичный `VEDICWAY_PUBLIC_ORIGIN`.

## Правовой release gate

До публичного трафика владелец передаёт юристу заполненные версии пользовательского соглашения, политики персональных данных, отдельного согласия и политики cookies. Техническая реализация уже разделяет согласие на обработку данных и принятие соглашения, не создаёт карту без обеих отметок и записывает версии документов в журнал. Юрист должен подтвердить сроки хранения, состав подрядчиков и порядок возврата именно для фактической бизнес-модели.

Оператор отдельно проверяет уведомление Роскомнадзора, размещение первичных баз персональных данных граждан России в России, договоры с хостингом, платёжным оператором и Яндексом. Эти организационные действия нельзя выполнить кодом и нельзя считать завершёнными по наличию страниц на сайте.

## Сроки хранения и удаление

Неоплаченные карты и связанные анонимные сессии удаляются через 30 дней. Ежедневная служебная задача запускает `uv run python -m vedicway_backend.privacy_ops cleanup-unpaid --older-than-days 30`. Административные сессии действуют 8 часов. Оплаченный отчёт доступен владельцу по ссылке восстановления до удаления по обращению; сроки доступа и дальнейшего архивного хранения оператор фиксирует в утверждённой политике до запуска.

После подтверждения личности и связи заявителя с расчётом оператор выполняет `uv run python -m vedicway_backend.privacy_ops erase-chart <chart_id> --confirm <chart_id>`. Команда удаляет карту, объяснения, вопросы, ссылки доступа и PDF. Если по карте была оплата, она обезличивает астрологические данные и отзывает доступ, но сохраняет платёжные и фискальные записи на обязательный срок, установленный бухгалтерским и налоговым законодательством. Результат команды не содержит исходные персональные данные и пригоден для журнала обращения.

Cookies-баннер разрешает отклонить аналитику одним действием, повторно открыть настройки из подвала и загружает Метрику только после согласия. Яндекс.Вебмастер не требует клиентского счётчика. Для Метрики используется официальный механизм отложенной загрузки и `disableYaCounter<ID>` при отзыве.

## Проверка перед релизом

Backend проверяется командами `uv run pytest` и `uv run alembic upgrade head` на пустой базе. Frontend проверяется через `npm run build` и `npm run test:run`. В браузерном прогоне нужно подтвердить четыре сценария: отказ от аналитики не создаёт запросов к `mc.yandex.ru`; форма не отправляется без двух отдельных отметок; обычный пользователь не открывает admin API; опубликованная статья и её обложка доступны после новой сессии.

Официальные источники: [статья 9 Федерального закона № 152-ФЗ](https://www.consultant.ru/document/cons_doc_LAW_61801/6c94959bc017ac80140621762d2ac59f6006b08c/), [Федеральный закон № 156-ФЗ от 24.06.2025](http://publication.pravo.gov.ru/document/0001202506240021), [отложенная загрузка Яндекс.Метрики](https://yandex.ru/support/metrica/ru/general/notification), [cookies Яндекс.Метрики](https://yandex.ru/support/metrica/ru/general/cookie-usage), [отключение счётчика](https://yandex.ru/support/metrica/ru/general/user-opt-out).

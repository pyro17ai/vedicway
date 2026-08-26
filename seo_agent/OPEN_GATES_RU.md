# Что нужно перед первым запуском SEO-агента

Production-профиль остается выключенным через `VEDICWAY_SEO_AGENT_ENABLED=0`. Схема и очередь стартуют пустыми: данные, cookie, токены и Chromium-профили донорского проекта в VedicWay не входят.

Для ежедневной публикации VK требует числовой ID сообщества в `VEDICWAY_VK_GROUP_ID`, токен сообщества для `wall.post` и пользовательский токен для `photos.getWallUploadServer`; они лежат в `secrets/vedicway_vk_group_access_token.txt` и `secrets/vedicway_vk_user_access_token.txt`. Дзен и Pinterest работают через два отдельных постоянных профиля Playwright. В `.env.production` задается только название Pinterest-доски `VEDICWAY_PINTEREST_BOARD_NAME`; токен Pinterest API больше не используется.

Сайт использует внутренний bearer-токен `secrets/vedicway_seo_agent_token.txt` длиной не меньше 32 случайных байт. Codex CLI читает отдельный `auth.json` из production-секрета и постоянного `CODEX_HOME`. Изображения создаёт встроенный `$imagegen`; `OPENAI_API_KEY` и отдельный imagegen-MCP SEO-контуру не нужны. Значения секретов нельзя писать в `.env.production`, лог запуска или ledger.

Исследование тем требует VedicWay Search API key и folder ID в `secrets/vedicway_yandex_search_api_key.txt` и `secrets/vedicway_yandex_folder_id.txt`. Wordstat служит базовым источником спроса. Если за последние 28 полных дней Metrika показывает меньше 100 органических визитов либо Webmaster возвращает меньше 30 показов, агент ранжирует темы по Wordstat, интенту выдачи и каннибализации.

Webmaster и Metrika подключаются только к подтвержденным ресурсам VedicWay. Точный host ID хранится в `VEDICWAY_YANDEX_HOST_ID`, numeric counter ID совпадает в `VEDICWAY_METRIKA_COUNTER_ID` и `VITE_YANDEX_METRIKA_ID`. Ошибка идентичности блокирует соответствующий отчет, но не мешает свежему Wordstat-исследованию.

До первого ежедневного запуска владелец должен один раз авторизовать пустой профиль VedicWay в Дзен, открыть существующий канал и проверить доступ к Студии. Pinterest-профиль должен быть авторизован как Business и видеть доску из `VEDICWAY_PINTEREST_BOARD_NAME` вместе с `#csv-input` на странице массовой загрузки. Ежедневный Pinterest-run стартует в 12:00 по Москве и передает десять карточек со слотами 13:00-22:00.

# Доступы, которых сейчас нет

Код SEO-контура готов к активации, но production-профиль намеренно остается выключенным через `VEDICWAY_SEO_AGENT_ENABLED=0`. Текущие Yandex MCP относятся к проекту Ивана, поэтому я ни разу не вызывал их для VedicWay и не переносил их токены.

Для запуска нужны точный Webmaster host ID домена VedicWay и OAuth-токен аккаунта, в котором этот сайт подтвержден. В `VEDICWAY_YANDEX_HOST_ID` нельзя подставлять первый сайт из `list_hosts`: Skill сверяет ID и домен буквально.

Нужен отдельный счетчик Metrika для публичного домена VedicWay. Его numeric ID одновременно записывается в `VITE_YANDEX_METRIKA_ID` и `VEDICWAY_METRIKA_COUNTER_ID`; OAuth-токен лежит в `secrets/vedicway_yandex_metrika_token.txt`. Расхождение двух ID блокирует SEO release-check.

Для Yandex Search API и Wordstat v2 нужны API key и folder ID VedicWay в `secrets/vedicway_yandex_search_api_key.txt` и `secrets/vedicway_yandex_folder_id.txt`. Код использует один Search API key для обоих MCP, как допускает установленный Wordstat server. Ключ должен иметь требуемый scope и роль Search API в указанном каталоге.

Внутренний bearer-токен `secrets/vedicway_seo_agent_token.txt` создается локально, содержит не меньше 32 случайных байт и монтируется только в backend и seo-agent. Нужен Codex API key для автономных запусков. В открытые env-файлы значения этих секретов не записываются.

Для Дзена владелец создает канал, набирает минимум 10 подписчиков, подтверждает домен VedicWay и добавляет `https://vedicway.ru/feed/dzen.xml`. До ручной приемки сохраняется `VEDICWAY_DZEN_PUBLICATION_MODE=native-draft`. Первый RSS должен содержать минимум 10 статей, а за предыдущие 30 дней на сайте должны выйти хотя бы три материала.

Resolved Compose проверяется с `--profile "*"` перед включением профиля `seo`; без этого Docker Compose исключает профильные сервисы из результата и контракт получается неполным. Сборка Linux-образа остаётся обязательной проверкой CI и сервера.

# Identity guard

Разрешенный Webmaster ID хранится только в `VEDICWAY_YANDEX_HOST_ID`, разрешенный счетчик Metrika в `VEDICWAY_METRIKA_COUNTER_ID`. Значения из MCP считаются недоверенными до точного сравнения.

Порядок Webmaster: `list_hosts` -> найти точное совпадение host_id и домена VedicWay -> использовать найденный ID во всех остальных инструментах. Порядок Metrika: `get_counters` -> найти точный numeric ID и домен VedicWay -> использовать его в отчетах. Ноль или несколько совпадений блокируют run.

Wordstat и Search используют отдельные VedicWay API key/folder ID. Минимальная свежесть: SERP 14 дней, Wordstat 30 дней, performance snapshot 7 дней. В записи обязательно хранить регион и время наблюдения.

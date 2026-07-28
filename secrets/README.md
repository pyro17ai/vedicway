# Production secrets

SEO-контур добавляет пять файлов: `vedicway_seo_agent_token.txt`, `vedicway_yandex_search_api_key.txt`, `vedicway_yandex_folder_id.txt`, `vedicway_yandex_webmaster_token.txt`, `vedicway_yandex_metrika_token.txt`. Внутренний SEO token генерируется локально и содержит не меньше 32 случайных байт. Yandex-файлы принадлежат только VedicWay; перенос токенов из другого сайта запрещен. Backend монтирует только внутренний SEO token, а сервис `seo-agent` получает Codex key, внутренний token и четыре Yandex credentials. Полный список внешних условий находится в [seo_agent/OPEN_GATES_RU.md](../seo_agent/OPEN_GATES_RU.md).

Каталог хранит только локальные secret-файлы и не попадает в Git. Скопируйте `.env.production.example` в `.env.production`, затем создайте пятнадцать постоянных файлов, перечисленных в шаблоне. В каждом файле должно лежать одно значение без имени переменной и без кавычек.

`vedicway_data_key.txt` содержит URL-safe Fernet key. Его создаёт команда `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Пароли PostgreSQL и SMTP, signing key, operations token и metrics token создавайте менеджером секретов; минимальная длина signing/operations token составляет 32 случайных байта. Реальные YooKassa и Codex credentials сюда копирует только оператор релиза.

`backup_encryption_key.txt` содержит отдельный URL-safe base64 ключ из 32 байт. Его можно создать той же командой Fernet, но повторно использовать `vedicway_data_key.txt` запрещено. Ключ резервных копий хранится вне узла приложения; без него paired bundle `.vwb` не восстанавливается.

`admin_bootstrap_email.txt` и `admin_bootstrap_password.txt` нужны только для одноразового запуска профиля `bootstrap`. Пароль содержит минимум 16 символов. После успешного создания администратора удалите оба файла: штатные процессы их не монтируют. Роли изолированы жёстко: API не получает Codex и SMTP, worker не получает платежи и SMTP, а `email` видит только data/signing keys и `smtp_password.txt`.

Права на Linux-хосте: `chmod 700 secrets && chmod 600 secrets/*.txt`. Не печатайте содержимое через `docker compose config`, CI logs или support ticket.

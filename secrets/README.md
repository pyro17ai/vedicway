# Production secrets

Каталог хранит только локальные secret-файлы и не попадает в Git. Скопируйте `.env.production.example` в `.env.production`, затем создайте девять постоянных файлов, перечисленных в шаблоне. В каждом файле должно лежать одно значение без имени переменной и без кавычек.

`vedicway_data_key.txt` содержит URL-safe Fernet key. Его создаёт команда `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Пароли PostgreSQL и SMTP, signing key, operations token и metrics token создавайте менеджером секретов; минимальная длина signing/operations token составляет 32 случайных байта. Реальные YooKassa и Codex credentials сюда копирует только оператор релиза.

`admin_bootstrap_email.txt` и `admin_bootstrap_password.txt` нужны только для одноразового запуска профиля `bootstrap`. Пароль содержит минимум 16 символов. После успешного создания администратора удалите оба файла: штатные процессы их не монтируют. Роли изолированы жёстко: API не получает Codex и SMTP, worker не получает платежи и SMTP, а `email` видит только data/signing keys и `smtp_password.txt`.

Права на Linux-хосте: `chmod 700 secrets && chmod 600 secrets/*.txt`. Не печатайте содержимое через `docker compose config`, CI logs или support ticket.

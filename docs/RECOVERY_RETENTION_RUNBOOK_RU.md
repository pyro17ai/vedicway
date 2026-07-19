# Recovery email и жизненный цикл персональных данных

## Что уже реализовано

Runtime хранит email покупки только в Fernet ciphertext, а поиск выполняет по HMAC, вычисленному независимым `VEDICWAY_SIGNING_KEY`. `POST /api/v1/access/recovery` одинаково отвечает `202 {"status":"accepted"}` для известного и неизвестного адреса. Известная оплаченная карта получает одноразовую ссылку на веб-результат и отдельную ссылку `download_pdf`, привязанную к неизменяемому `render_request_id`. Повторное открытие ссылки возвращает `401`; сырой bearer не хранится в БД.

После первого успешного PDF render расчётный worker создаёт одну запись `purchase_ready` на покупку. Её забирает только отдельный процесс `python -m vedicway_backend.email_worker`; API и расчётный worker не получают SMTP-пароль и не могут потребить очередь писем. `email_deliveries` повторяет временную SMTP-ошибку не более трёх раз и не создаёт второе письмо при повторной обработке webhook, PDF job или последующем рендере с другими настройками. SMTP не используется для маркетинга. При неопределённом сетевом исходе сам SMTP не даёт строгой exactly-once гарантии, поэтому production-провайдер должен возвращать стабильный Message-ID и предоставлять журнал доставки.

Owned `DELETE /api/v1/charts/{chart_id}` сначала проверяет session ownership и отказывает при активном `running/validating` job. В одной SQLite-транзакции создаётся `erasure_tombstones`, удаляются расчёт, заметки, magic links и доступ; финансовая запись сохраняется без email и provider payload. После commit удаляются только файлы, чей resolved path находится внутри `VEDICWAY_DATA_DIR/reports`. Ошибка unlink остаётся в tombstone со статусом `pending_files`, следующий lifecycle run повторяет операцию.

`POST /api/v1/privacy/requests` принимает `access`, `erase` или `withdraw`, всегда возвращает одинаковый `202` и хранит адрес зашифрованным. Intake не исполняет удаление автоматически: сотрудник сначала подтверждает личность заявителя по утверждённой процедуре, затем запускает `python -m vedicway_backend.privacy_ops erase-chart CHART_ID --confirm CHART_ID`. Это предохраняет от удаления по письму злоумышленника.

## Production-настройка SMTP

Обязательны `VEDICWAY_SMTP_HOST`, `VEDICWAY_SMTP_PORT`, `VEDICWAY_SMTP_USERNAME`, `VEDICWAY_SMTP_FROM_EMAIL` и HTTPS-origin в `VEDICWAY_PUBLIC_ORIGIN`. Пароль хранится только в `secrets/smtp_password.txt`; Compose монтирует его лишь в сервис `email`, чей отдельный `email-egress` network не соединён с API, worker и PostgreSQL. Для 587 включается `VEDICWAY_SMTP_STARTTLS=1`; для 465 используется `VEDICWAY_SMTP_SSL=1`. Одновременно разрешён ровно один TLS-режим. API readiness проверяет публичные SMTP-параметры, а `email` завершает запуск при отсутствующем пароле или небезопасной конфигурации.

Перед включением доставки владелец домена публикует SPF для выбранного провайдера, DKIM-ключ из его панели и DMARC сначала в режиме наблюдения. Затем выполняются отправка на внешний ящик, проверка SPF/DKIM/DMARC headers, тест одноразового chart link, тест точного PDF link и replay. Nginx полностью отключает access log для `/api/v1/magic-links/{token}`; redirect дополнительно получает `Cache-Control: no-store`.

## Сроки и ежедневный запуск

Production не получает молчаливых юридических сроков. До запуска оператор явно задаёт `VEDICWAY_RETENTION_ANONYMOUS_CHART_DAYS`, `VEDICWAY_RETENTION_REPORT_DAYS`, `VEDICWAY_RETENTION_SECURITY_LOG_DAYS`, `VEDICWAY_RETENTION_FINANCIAL_RECORD_DAYS` и `VEDICWAY_RETENTION_BACKUP_DAYS` по утверждённой политике. Без любого значения readiness остаётся красным.

Локально безопасный просмотр запускается так:

```powershell
python backend/scripts/data_lifecycle.py --dry-run
```

После сверки числа кандидатов выполняется:

```powershell
python backend/scripts/data_lifecycle.py --apply
```

В production используются изолированные one-shot сервисы. Они работают без сети и получают только ключи runtime:

```powershell
docker compose --env-file .env.production -f compose.production.yml --profile ops run --rm retention-dry-run
docker compose --env-file .env.production -f compose.production.yml --profile ops run --rm retention-apply
```

Ежедневный запуск закрепляется через `/etc/systemd/system/vedicway-retention.service`:

```ini
[Unit]
Description=VedicWay daily personal-data lifecycle
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/vedicway
ExecStart=/usr/bin/docker compose --env-file .env.production -f compose.production.yml --profile ops run --rm retention-apply
```

Таймер `/etc/systemd/system/vedicway-retention.timer`:

```ini
[Unit]
Description=Run VedicWay data lifecycle every night

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true
RandomizedDelaySec=900
Unit=vedicway-retention.service

[Install]
WantedBy=timers.target
```

После ручного `retention-dry-run` оператор включает расписание командами `systemctl daemon-reload` и `systemctl enable --now vedicway-retention.timer`. Мониторинг обязан сигнализировать о failed-состоянии `vedicway-retention.service`; проверка расписания выполняется через `systemctl list-timers vedicway-retention.timer`.

Команда идемпотентна, записывает `retention_runs`, стирает истёкшие анонимные карты и PDF, чистит старые rate-limit buckets и повторяет pending unlink. Финансовые записи автоматически не удаляются: их срок задаёт политика, а отдельную процедуру архивного удаления оператор утверждает до production. Tombstones резервируются отдельно от обычного runtime backup; после восстановления старого backup сначала импортируется более новый tombstone ledger и повторяется `--apply`. Автоматический внешний импорт tombstones остаётся инфраструктурным release gate.

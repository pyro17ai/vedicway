# Brief contract

`outline` содержит объекты `heading`, `question`, `evidence_ids`, `takeaway`. Заголовки не дублируют друг друга.

`evidence` содержит `source_id`, `claim`, `source_url`, `observed_at`, `source_kind`. Для расчетов добавляются входные параметры и версия инструмента.

`internal_links` содержит существующий `url`, anchor и причину перехода. `prohibited_claims` перечисляет конкретные обещания и медицинские формулировки, которые нельзя допускать в тексте.

Checksum считается от JSON с сортированными ключами и без пробелов. В объект входят ровно `title`, `primary_query`, `audience_problem`, `search_intent`, `outline`, `evidence`, `internal_links`, `prohibited_claims`. Статус `approved` означает, что все URL проверены и все claims имеют evidence.

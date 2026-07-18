from __future__ import annotations

from vedicway_backend.store import Store


def test_rate_limit_is_shared_by_store_instances(tmp_path) -> None:
    first = Store(tmp_path / "runtime")
    second = Store(tmp_path / "runtime")

    assert first.record_rate_limit_hit("hashed-client", 2, 3600) == 0
    assert second.record_rate_limit_hit("hashed-client", 2, 3600) == 0
    retry_after = first.record_rate_limit_hit("hashed-client", 2, 3600)

    assert 1 <= retry_after <= 3600
    assert second.record_rate_limit_hit("another-client", 2, 3600) == 0


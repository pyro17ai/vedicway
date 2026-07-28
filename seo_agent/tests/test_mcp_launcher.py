from __future__ import annotations

import pytest

from seo_agent.db import LedgerError
from seo_agent.mcp_launcher import isolated_environment


def test_launcher_replaces_inherited_yandex_credentials_with_vedicway_values() -> None:
    source = {
        "PATH": "runtime",
        "YANDEX_SEARCH_API_KEY": "ivan-search-key",
        "YANDEX_FOLDER_ID": "ivan-folder",
        "YANDEX_CLIENT_SECRET": "ivan-oauth-secret",
        "VEDICWAY_YANDEX_SEARCH_API_KEY": "vedicway-search-key",
        "VEDICWAY_YANDEX_FOLDER_ID": "vedicway-folder",
    }
    environment = isolated_environment("search", source)
    assert environment == {
        "PATH": "runtime",
        "YANDEX_SEARCH_API_KEY": "vedicway-search-key",
        "YANDEX_FOLDER_ID": "vedicway-folder",
    }


def test_launcher_fails_closed_without_vedicway_credentials() -> None:
    with pytest.raises(LedgerError, match="VEDICWAY_YANDEX_WEBMASTER_TOKEN"):
        isolated_environment(
            "webmaster",
            {"YANDEX_WEBMASTER_TOKEN": "inherited-ivan-token"},
        )

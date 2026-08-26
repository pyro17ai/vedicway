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


def test_api_pinterest_launcher_is_removed() -> None:
    with pytest.raises(LedgerError, match="Unsupported VedicWay MCP target"):
        isolated_environment("pinterest", {"VEDICWAY_PINTEREST_ACCESS_TOKEN": "old"})


def test_control_launcher_gets_codex_home_without_openai_api_key() -> None:
    environment = isolated_environment(
        "control",
        {
            "PATH": "runtime",
            "CODEX_HOME": "/owned/codex-home",
            "OPENAI_API_KEY": "must-not-leak",
            "VEDICWAY_SEO_DATA_DIR": "/owned/data",
            "VEDICWAY_SEO_AGENT_TOKEN": "internal-token",
            "VEDICWAY_VK_GROUP_ACCESS_TOKEN": "must-not-leak",
        },
    )
    assert environment == {
        "PATH": "runtime",
        "CODEX_HOME": "/owned/codex-home",
        "VEDICWAY_SEO_DATA_DIR": "/owned/data",
        "VEDICWAY_SEO_AGENT_TOKEN": "internal-token",
    }

    with pytest.raises(LedgerError, match="Unsupported VedicWay MCP target"):
        isolated_environment("imagegen", {"OPENAI_API_KEY": "foreign"})

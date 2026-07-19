from __future__ import annotations

import os

LEGAL_DOCUMENT_VERSIONS = {
    "terms": "2026-07-19",
    "privacy": "2026-07-19",
    "personal_data_consent": "2026-07-19",
    "cookies": "2026-07-19",
}


def public_legal_config() -> dict[str, object]:
    values = {
        "operator_name": os.environ.get("VEDICWAY_LEGAL_OPERATOR_NAME", "[НАИМЕНОВАНИЕ ОПЕРАТОРА]"),
        "operator_address": os.environ.get(
            "VEDICWAY_LEGAL_OPERATOR_ADDRESS", "[ЮРИДИЧЕСКИЙ АДРЕС]"
        ),
        "inn": os.environ.get("VEDICWAY_LEGAL_OPERATOR_INN", "[ИНН]"),
        "ogrn": os.environ.get("VEDICWAY_LEGAL_OPERATOR_OGRN", "[ОГРН/ОГРНИП]"),
        "privacy_email": os.environ.get("VEDICWAY_PRIVACY_EMAIL", "[EMAIL ДЛЯ ОБРАЩЕНИЙ]"),
    }
    configured = all(not str(value).startswith("[") for value in values.values())
    return {**values, "versions": LEGAL_DOCUMENT_VERSIONS, "configured": configured}

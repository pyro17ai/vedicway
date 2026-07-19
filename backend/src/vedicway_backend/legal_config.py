from __future__ import annotations

import os

LEGAL_DOCUMENT_VERSIONS = {
    "terms": "2026-07-19",
    "privacy": "2026-07-19-v2",
    "personal_data_consent": "2026-07-19-v2",
    "cookies": "2026-07-19",
}

INTERPRETATION_PROCESSOR_ENV = (
    "VEDICWAY_INTERPRETATION_PROCESSOR_NAME",
    "VEDICWAY_INTERPRETATION_PROCESSOR_ADDRESS",
    "VEDICWAY_INTERPRETATION_PROCESSOR_COUNTRY",
    "VEDICWAY_INTERPRETATION_PROCESSOR_PURPOSE",
    "VEDICWAY_INTERPRETATION_PROCESSOR_DATA_CATEGORIES",
)


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().casefold()
    return (
        not normalized
        or normalized.startswith("[")
        or "replace_with" in normalized
        or normalized in {"replace", "placeholder", "change_me"}
    )


def interpretation_processor_config() -> dict[str, object]:
    raw_values = {
        "name": os.environ.get(
            "VEDICWAY_INTERPRETATION_PROCESSOR_NAME",
            "[НАИМЕНОВАНИЕ ОБРАБОТЧИКА ОБЪЯСНЕНИЙ]",
        ).strip(),
        "address": os.environ.get(
            "VEDICWAY_INTERPRETATION_PROCESSOR_ADDRESS",
            "[АДРЕС ОБРАБОТЧИКА ОБЪЯСНЕНИЙ]",
        ).strip(),
        "country": os.environ.get(
            "VEDICWAY_INTERPRETATION_PROCESSOR_COUNTRY",
            "[СТРАНА ОБРАБОТЧИКА ОБЪЯСНЕНИЙ]",
        ).strip(),
        "purpose": os.environ.get(
            "VEDICWAY_INTERPRETATION_PROCESSOR_PURPOSE",
            "[ЦЕЛЬ ПЕРЕДАЧИ ОБРАБОТЧИКУ ОБЪЯСНЕНИЙ]",
        ).strip(),
    }
    categories_raw = os.environ.get(
        "VEDICWAY_INTERPRETATION_PROCESSOR_DATA_CATEGORIES", ""
    ).strip()
    categories = [item.strip() for item in categories_raw.split("|") if item.strip()]
    cross_border_raw = os.environ.get(
        "VEDICWAY_INTERPRETATION_PROCESSOR_CROSS_BORDER", ""
    ).strip()
    configured = (
        all(not _is_placeholder(str(value)) for value in raw_values.values())
        and bool(categories)
        and not any(_is_placeholder(item) for item in categories)
        and cross_border_raw in {"0", "1"}
    )
    return {
        **raw_values,
        "data_categories": categories,
        "cross_border": cross_border_raw == "1" if cross_border_raw in {"0", "1"} else None,
        "configured": configured,
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
    processor = interpretation_processor_config()
    processor_enabled = (
        os.environ.get("VEDICWAY_INTERPRETATION_PROVIDER", "").strip().casefold() == "codex"
    )
    operator_configured = all(not _is_placeholder(str(value)) for value in values.values())
    configured = operator_configured and (
        not processor_enabled or bool(processor["configured"])
    )
    return {
        **values,
        "versions": LEGAL_DOCUMENT_VERSIONS,
        "configured": configured,
        "interpretation_processor_enabled": processor_enabled,
        "interpretation_processor_configured": processor["configured"],
        "interpretation_processor_name": processor["name"],
        "interpretation_processor_address": processor["address"],
        "interpretation_processor_country": processor["country"],
        "interpretation_processor_purpose": processor["purpose"],
        "interpretation_processor_data_categories": processor["data_categories"],
        "interpretation_processor_cross_border": processor["cross_border"],
    }

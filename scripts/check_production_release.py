from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from wheelhouse_contract import validate_wheelhouse

REQUIRED_VALUES = (
    "RELEASE_TAG",
    "VEDICWAY_PUBLIC_BASE_URL",
    "VEDICWAY_PUBLIC_ORIGIN",
    "VEDICWAY_RUNTIME_PROFILE",
    "VEDICWAY_LEGAL_OPERATOR_NAME",
    "VEDICWAY_LEGAL_OPERATOR_ADDRESS",
    "VEDICWAY_LEGAL_OPERATOR_INN",
    "VEDICWAY_LEGAL_OPERATOR_OGRN",
    "VEDICWAY_PRIVACY_EMAIL",
    "VEDICWAY_INTERPRETATION_PROVIDER",
    "VEDICWAY_INTERPRETATION_PROCESSOR_NAME",
    "VEDICWAY_INTERPRETATION_PROCESSOR_ADDRESS",
    "VEDICWAY_INTERPRETATION_PROCESSOR_COUNTRY",
    "VEDICWAY_INTERPRETATION_PROCESSOR_PURPOSE",
    "VEDICWAY_INTERPRETATION_PROCESSOR_DATA_CATEGORIES",
    "VEDICWAY_INTERPRETATION_PROCESSOR_CROSS_BORDER",
    "VITE_YANDEX_METRIKA_ID",
    "VEDICWAY_OPERATIONS_CIDRS",
    "VEDICWAY_PLACE_DATASET_FILE",
    "PYJHORA_WHEELHOUSE_DIR",
    "VEDICWAY_OFFER_VERSION",
    "VEDICWAY_OFFER_URL",
    "VEDICWAY_PRIVACY_URL",
    "YOOKASSA_VAT_CODE",
    "VEDICWAY_SMTP_HOST",
    "VEDICWAY_SMTP_PORT",
    "VEDICWAY_SMTP_USERNAME",
    "VEDICWAY_SMTP_FROM_EMAIL",
    "VEDICWAY_RETENTION_ANONYMOUS_CHART_DAYS",
    "VEDICWAY_RETENTION_REPORT_DAYS",
    "VEDICWAY_RETENTION_SECURITY_LOG_DAYS",
    "VEDICWAY_RETENTION_FINANCIAL_RECORD_DAYS",
    "VEDICWAY_RETENTION_BACKUP_DAYS",
)

SECRET_PATHS = {
    "POSTGRES_PASSWORD_FILE": 16,
    "VEDICWAY_DATA_KEY_FILE": 40,
    "VEDICWAY_SIGNING_KEY_FILE": 32,
    "VEDICWAY_OPERATIONS_TOKEN_FILE": 32,
    "VEDICWAY_METRICS_TOKEN_FILE": 32,
    "YOOKASSA_SHOP_ID_FILE": 1,
    "YOOKASSA_SECRET_KEY_FILE": 16,
    "OPENAI_API_KEY_FILE": 16,
    "VEDICWAY_SMTP_PASSWORD_FILE": 8,
    "VEDICWAY_BACKUP_KEY_FILE": 40,
}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected NAME=value")
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values


def resolve_input(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def reject_placeholder(name: str, value: str, errors: list[str]) -> None:
    folded = value.casefold()
    if not value or "replace" in folded or ".example" in folded:
        errors.append(f"{name} contains a placeholder")


def check_url(name: str, value: str, errors: list[str]) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        errors.append(f"{name} must be an absolute public HTTPS URL without credentials")


def check_wheelhouse(path: Path, errors: list[str]) -> None:
    errors.extend(validate_wheelhouse(path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed VedicWay production input check")
    parser.add_argument("--env-file", default=".env.production")
    args = parser.parse_args()

    env_path = Path(args.env_file).resolve()
    root = env_path.parent
    errors: list[str] = []
    if not env_path.is_file():
        print(f"Missing env file: {env_path}", file=sys.stderr)
        return 2

    try:
        values = parse_env(env_path)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2

    for name in REQUIRED_VALUES:
        reject_placeholder(name, values.get(name, ""), errors)
    for name in (
        "VEDICWAY_PUBLIC_BASE_URL",
        "VEDICWAY_PUBLIC_ORIGIN",
        "VEDICWAY_OFFER_URL",
        "VEDICWAY_PRIVACY_URL",
    ):
        check_url(name, values.get(name, ""), errors)

    public_url = urlsplit(values.get("VEDICWAY_PUBLIC_BASE_URL", ""))
    if public_url.path not in {"", "/"} or public_url.query or public_url.fragment:
        errors.append("VEDICWAY_PUBLIC_BASE_URL must contain only the HTTPS origin")
    if values.get("VEDICWAY_PUBLIC_ORIGIN", "").rstrip("/") != values.get("VEDICWAY_PUBLIC_BASE_URL", "").rstrip("/"):
        errors.append("VEDICWAY_PUBLIC_ORIGIN must equal VEDICWAY_PUBLIC_BASE_URL")
    for name in ("VEDICWAY_OFFER_URL", "VEDICWAY_PRIVACY_URL"):
        if urlsplit(values.get(name, "")).hostname != public_url.hostname:
            errors.append(f"{name} must use the public VedicWay host")

    if not re.fullmatch(r"[0-9a-f]{7,40}", values.get("RELEASE_TAG", ""), flags=re.IGNORECASE):
        errors.append("RELEASE_TAG must be the immutable Git commit SHA")
    for name in ("VEDICWAY_OPERATIONS_CIDRS", "VEDICWAY_TRUSTED_PROXY_CIDRS", "VEDICWAY_DOCKER_SUBNET"):
        try:
            networks = [ipaddress.ip_network(item.strip()) for item in values.get(name, "").split(",") if item.strip()]
            if not networks:
                raise ValueError
        except ValueError:
            errors.append(f"{name} must contain valid CIDR values")

    if values.get("VEDICWAY_TEST_PAYMENTS") != "0":
        errors.append("VEDICWAY_TEST_PAYMENTS must equal 0")
    if values.get("VEDICWAY_INTERPRETATION_PROVIDER") != "codex":
        errors.append("VEDICWAY_INTERPRETATION_PROVIDER must equal codex")
    if values.get("VEDICWAY_INTERPRETATION_PROCESSOR_CROSS_BORDER") not in {"0", "1"}:
        errors.append("VEDICWAY_INTERPRETATION_PROCESSOR_CROSS_BORDER must equal 0 or 1")
    if values.get("VEDICWAY_PAYMENT_PROVIDER") != "yookassa":
        errors.append("VEDICWAY_PAYMENT_PROVIDER must equal yookassa")
    if values.get("VEDICWAY_RUNTIME_PROFILE") != "single-node-sqlite":
        errors.append("VEDICWAY_RUNTIME_PROFILE must equal single-node-sqlite")
    if values.get("PUBLIC_HTTP_BIND") not in {"127.0.0.1", "::1"}:
        errors.append("PUBLIC_HTTP_BIND must stay on loopback behind TLS ingress")
    try:
        vat_code = int(values.get("YOOKASSA_VAT_CODE", ""))
        if vat_code not in range(1, 13):
            raise ValueError
    except ValueError:
        errors.append("YOOKASSA_VAT_CODE must be a confirmed integer from 1 to 12")
    if not re.fullmatch(r"\d+", values.get("VITE_YANDEX_METRIKA_ID", "")):
        errors.append("VITE_YANDEX_METRIKA_ID must contain a numeric counter id")
    if not re.fullmatch(r"(?:\d{10}|\d{12})", values.get("VEDICWAY_LEGAL_OPERATOR_INN", "")):
        errors.append("VEDICWAY_LEGAL_OPERATOR_INN must contain a 10- or 12-digit INN")
    if not re.fullmatch(r"(?:\d{13}|\d{15})", values.get("VEDICWAY_LEGAL_OPERATOR_OGRN", "")):
        errors.append("VEDICWAY_LEGAL_OPERATOR_OGRN must contain a 13- or 15-digit OGRN/OGRNIP")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values.get("VEDICWAY_PRIVACY_EMAIL", "")):
        errors.append("VEDICWAY_PRIVACY_EMAIL must contain an email address")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values.get("VEDICWAY_SMTP_FROM_EMAIL", "")):
        errors.append("VEDICWAY_SMTP_FROM_EMAIL must contain an email address")
    try:
        smtp_port = int(values.get("VEDICWAY_SMTP_PORT", ""))
        if not 1 <= smtp_port <= 65535:
            raise ValueError
    except ValueError:
        errors.append("VEDICWAY_SMTP_PORT must contain a port from 1 to 65535")
    if values.get("VEDICWAY_SMTP_SSL") not in {"0", "1"}:
        errors.append("VEDICWAY_SMTP_SSL must equal 0 or 1")
    if values.get("VEDICWAY_SMTP_STARTTLS") not in {"0", "1"}:
        errors.append("VEDICWAY_SMTP_STARTTLS must equal 0 or 1")
    if values.get("VEDICWAY_SMTP_SSL") == values.get("VEDICWAY_SMTP_STARTTLS"):
        errors.append("exactly one of VEDICWAY_SMTP_SSL or VEDICWAY_SMTP_STARTTLS must equal 1")
    try:
        timeout = float(values.get("VEDICWAY_SMTP_TIMEOUT_SECONDS", ""))
        if timeout <= 0 or timeout > 60:
            raise ValueError
    except ValueError:
        errors.append("VEDICWAY_SMTP_TIMEOUT_SECONDS must be greater than 0 and at most 60")
    for name in (
        "VEDICWAY_RETENTION_ANONYMOUS_CHART_DAYS",
        "VEDICWAY_RETENTION_REPORT_DAYS",
        "VEDICWAY_RETENTION_SECURITY_LOG_DAYS",
        "VEDICWAY_RETENTION_FINANCIAL_RECORD_DAYS",
        "VEDICWAY_RETENTION_BACKUP_DAYS",
    ):
        try:
            if int(values.get(name, "")) < 1:
                raise ValueError
        except ValueError:
            errors.append(f"{name} must contain approved positive days")

    secret_values: dict[str, str] = {}
    for name, minimum in SECRET_PATHS.items():
        raw_path = values.get(name, "")
        if not raw_path:
            errors.append(f"{name} is missing")
            continue
        path = resolve_input(root, raw_path)
        if not path.is_file():
            errors.append(f"secret file is missing for {name}")
            continue
        if os.name == "posix" and path.stat().st_mode & 0o077:
            errors.append(f"secret file permissions are too broad for {name}; expected 0600")
        secret = path.read_text(encoding="utf-8").strip()
        if len(secret) < minimum:
            errors.append(f"secret in {name} is shorter than {minimum} characters")
        secret_values[name] = secret

    data_key = secret_values.get("VEDICWAY_DATA_KEY_FILE", "")
    try:
        if len(base64.urlsafe_b64decode(data_key.encode("ascii"))) != 32:
            raise ValueError
    except (ValueError, UnicodeEncodeError):
        errors.append("VEDICWAY_DATA_KEY_FILE does not contain a Fernet key")
    backup_key = secret_values.get("VEDICWAY_BACKUP_KEY_FILE", "")
    try:
        if len(base64.urlsafe_b64decode(backup_key.encode("ascii"))) != 32:
            raise ValueError
    except (ValueError, UnicodeEncodeError):
        errors.append("VEDICWAY_BACKUP_KEY_FILE must contain a URL-safe base64 encoded 32-byte key")
    if secret_values.get("YOOKASSA_SHOP_ID_FILE") and not secret_values["YOOKASSA_SHOP_ID_FILE"].isdigit():
        errors.append("YOOKASSA_SHOP_ID_FILE must contain a numeric shop id")

    places_path = resolve_input(root, values.get("VEDICWAY_PLACE_DATASET_FILE", ""))
    try:
        payload = json.loads(places_path.read_text(encoding="utf-8"))
        records = payload.get("places") if isinstance(payload, dict) else payload
        if not isinstance(records, list) or not records:
            raise ValueError("empty places collection")
        required = {"place_id", "display_name", "country_code", "latitude", "longitude", "tzid"}
        if any(not isinstance(record, dict) or not required.issubset(record) for record in records):
            raise ValueError("invalid place record")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        errors.append(f"place dataset failed structural validation: {error}")

    wheelhouse = resolve_input(root, values.get("PYJHORA_WHEELHOUSE_DIR", ""))
    check_wheelhouse(wheelhouse, errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Production inputs passed structural validation; no secret values were printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

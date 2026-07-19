from __future__ import annotations

import argparse
import json
from pathlib import Path

ROLE_CONTRACTS = {
    "backend": {
        "profile": "api",
        "secrets": {
            "postgres_password",
            "vedicway_data_key",
            "vedicway_signing_key",
            "vedicway_operations_token",
            "vedicway_metrics_token",
            "yookassa_shop_id",
            "yookassa_secret_key",
        },
        "files": {
            "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
            "VEDICWAY_DATA_KEY_FILE": "/run/secrets/vedicway_data_key",
            "VEDICWAY_SIGNING_KEY_FILE": "/run/secrets/vedicway_signing_key",
            "VEDICWAY_OPERATIONS_TOKEN_FILE": "/run/secrets/vedicway_operations_token",
            "VEDICWAY_METRICS_TOKEN_FILE": "/run/secrets/vedicway_metrics_token",
            "YOOKASSA_SHOP_ID_FILE": "/run/secrets/yookassa_shop_id",
            "YOOKASSA_SECRET_KEY_FILE": "/run/secrets/yookassa_secret_key",
        },
    },
    "worker": {
        "profile": "worker",
        "secrets": {
            "postgres_password",
            "vedicway_data_key",
            "vedicway_signing_key",
            "codex_api_key",
        },
        "files": {
            "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
            "VEDICWAY_DATA_KEY_FILE": "/run/secrets/vedicway_data_key",
            "VEDICWAY_SIGNING_KEY_FILE": "/run/secrets/vedicway_signing_key",
            "OPENAI_API_KEY_FILE": "/run/secrets/codex_api_key",
        },
    },
    "email": {
        "profile": "email",
        "secrets": {"vedicway_data_key", "vedicway_signing_key", "smtp_password"},
        "files": {
            "VEDICWAY_DATA_KEY_FILE": "/run/secrets/vedicway_data_key",
            "VEDICWAY_SIGNING_KEY_FILE": "/run/secrets/vedicway_signing_key",
            "VEDICWAY_SMTP_PASSWORD_FILE": "/run/secrets/smtp_password",
        },
    },
}

REQUIRED_RECOVERY_ENV = {
    "VEDICWAY_PUBLIC_ORIGIN",
    "VEDICWAY_SMTP_HOST",
    "VEDICWAY_SMTP_PORT",
    "VEDICWAY_SMTP_USERNAME",
    "VEDICWAY_SMTP_FROM_EMAIL",
    "VEDICWAY_SMTP_STARTTLS",
    "VEDICWAY_SMTP_SSL",
    "VEDICWAY_SMTP_TIMEOUT_SECONDS",
    "VEDICWAY_RETENTION_ANONYMOUS_CHART_DAYS",
    "VEDICWAY_RETENTION_REPORT_DAYS",
    "VEDICWAY_RETENTION_SECURITY_LOG_DAYS",
    "VEDICWAY_RETENTION_FINANCIAL_RECORD_DAYS",
    "VEDICWAY_RETENTION_BACKUP_DAYS",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate resolved production Compose contract")
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    services = payload.get("services", {})
    required = {
        "postgres",
        "migrate",
        "content-migrate",
        "backend",
        "worker",
        "email",
        "frontend",
        "retention-dry-run",
        "retention-apply",
    }
    missing = required.difference(services)
    if missing:
        raise SystemExit(f"Missing production services: {', '.join(sorted(missing))}")

    for service_name, contract in ROLE_CONTRACTS.items():
        service = services[service_name]
        environment = service.get("environment", {})
        if environment.get("VEDICWAY_SECRET_PROFILE") != contract["profile"]:
            raise SystemExit(f"{service_name} must use the {contract['profile']} secret profile")
        for name, expected in contract["files"].items():
            if environment.get(name) != expected:
                raise SystemExit(f"{service_name}.{name} must resolve to {expected}")
        mounted_secrets = {
            item.get("source") if isinstance(item, dict) else item
            for item in service.get("secrets", [])
        }
        if mounted_secrets != contract["secrets"]:
            raise SystemExit(f"{service_name} has an invalid secret mount set")
        if "VEDICWAY_SMTP_PASSWORD" in environment:
            raise SystemExit(f"{service_name} must not receive an SMTP password through plain environment")

    for service_name in ("backend", "email"):
        missing_environment = REQUIRED_RECOVERY_ENV.difference(
            services[service_name].get("environment", {})
        )
        if missing_environment:
            raise SystemExit(
                f"{service_name} is missing recovery environment: "
                f"{', '.join(sorted(missing_environment))}"
            )

    for service_name in ("backend", "worker"):
        service = services[service_name]
        environment = service.get("environment", {})
        if environment.get("VEDICWAY_RUNTIME_PROFILE") != "single-node-sqlite":
            raise SystemExit(f"{service_name} must use the single-node-sqlite runtime profile")
        if int(service.get("deploy", {}).get("replicas", 1)) != 1:
            raise SystemExit(f"{service_name} must have exactly one replica")

    dependencies = services["backend"].get("depends_on", {})
    if "content-migrate" not in dependencies:
        raise SystemExit("backend must wait for content-migrate")
    ports = services["frontend"].get("ports", [])
    published_hosts = {str(item.get("host_ip", "")) for item in ports if isinstance(item, dict)}
    if not published_hosts or not published_hosts.issubset({"127.0.0.1", "::1"}):
        raise SystemExit("frontend production port must bind only to loopback")

    entrypoint = (Path(__file__).resolve().parents[1] / "docker/backend/entrypoint.sh").read_text(
        encoding="utf-8"
    )
    if "read_secret OPENAI_API_KEY" not in entrypoint or "read_secret CODEX_API_KEY" in entrypoint:
        raise SystemExit("backend entrypoint must export the Codex secret as OPENAI_API_KEY")
    if 'if [ "$profile" = "email" ]' not in entrypoint:
        raise SystemExit("backend entrypoint must isolate the email secret profile")
    if "read_secret VEDICWAY_SMTP_PASSWORD" not in entrypoint:
        raise SystemExit("backend entrypoint must load the SMTP password from a mounted secret")

    email = services["email"]
    if "vedicway_backend.email_worker" not in " ".join(email.get("command", [])):
        raise SystemExit("email service must run the dedicated transactional email worker")
    if set(email.get("networks", {})) != {"email-egress"}:
        raise SystemExit("email service must use only the isolated egress network")
    if int(email.get("deploy", {}).get("replicas", 1)) != 1:
        raise SystemExit("email service must have exactly one replica")

    for service_name, mode in (("retention-dry-run", "--dry-run"), ("retention-apply", "--apply")):
        service = services[service_name]
        command = service.get("command", [])
        if mode not in command or "data_lifecycle.py" not in " ".join(command):
            raise SystemExit(f"{service_name} must run data_lifecycle.py {mode}")
        if service.get("network_mode") != "none":
            raise SystemExit(f"{service_name} must not have network access")
        if service.get("environment", {}).get("VEDICWAY_SECRET_PROFILE") != "lifecycle":
            raise SystemExit(f"{service_name} must use the lifecycle secret profile")
        mounted_secrets = {
            item.get("source") if isinstance(item, dict) else item
            for item in service.get("secrets", [])
        }
        if mounted_secrets != {"vedicway_data_key", "vedicway_signing_key"}:
            raise SystemExit(f"{service_name} must mount only runtime encryption secrets")
    print("Resolved production Compose contract passed.")


if __name__ == "__main__":
    main()

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
            "vedicway_seo_agent_token",
            "yookassa_shop_id",
            "yookassa_secret_key",
        },
        "files": {
            "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
            "VEDICWAY_DATA_KEY_FILE": "/run/secrets/vedicway_data_key",
            "VEDICWAY_SIGNING_KEY_FILE": "/run/secrets/vedicway_signing_key",
            "VEDICWAY_OPERATIONS_TOKEN_FILE": "/run/secrets/vedicway_operations_token",
            "VEDICWAY_METRICS_TOKEN_FILE": "/run/secrets/vedicway_metrics_token",
            "VEDICWAY_SEO_AGENT_TOKEN_FILE": "/run/secrets/vedicway_seo_agent_token",
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
    "seo-agent": {
        "profile": "seo-agent",
        "secrets": {
            "codex_api_key",
            "vedicway_seo_agent_token",
            "yandex_search_api_key",
            "yandex_folder_id",
            "yandex_webmaster_token",
            "yandex_metrika_token",
        },
        "files": {
            "OPENAI_API_KEY_FILE": "/run/secrets/codex_api_key",
            "VEDICWAY_SEO_AGENT_TOKEN_FILE": "/run/secrets/vedicway_seo_agent_token",
            "VEDICWAY_YANDEX_SEARCH_API_KEY_FILE": "/run/secrets/yandex_search_api_key",
            "VEDICWAY_YANDEX_FOLDER_ID_FILE": "/run/secrets/yandex_folder_id",
            "VEDICWAY_YANDEX_WEBMASTER_TOKEN_FILE": "/run/secrets/yandex_webmaster_token",
            "VEDICWAY_YANDEX_METRIKA_TOKEN_FILE": "/run/secrets/yandex_metrika_token",
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


def _secret_sources(service: dict[str, object]) -> set[str]:
    sources: set[str] = set()
    for item in service.get("secrets", []):
        if isinstance(item, str):
            sources.add(item)
        elif isinstance(item, dict) and item.get("source"):
            sources.add(str(item["source"]))
    return sources


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
        "ops-gateway",
        "backup-bundle",
        "seo-agent",
        "seo-agent-backup",
        "seo-agent-restore",
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

    api_secrets = _secret_sources(services["backend"])
    worker_secrets = _secret_sources(services["worker"])
    if "codex_api_key" in api_secrets:
        raise SystemExit("backend API must not mount the Codex key")
    forbidden_worker = {"vedicway_operations_token", "vedicway_metrics_token", "vedicway_seo_agent_token", "yookassa_shop_id", "yookassa_secret_key"}
    if worker_secrets.intersection(forbidden_worker):
        raise SystemExit("worker mounts API-only operations or payment secrets")
    if worker_secrets != {"postgres_password", "vedicway_data_key", "vedicway_signing_key", "codex_api_key"}:
        raise SystemExit("worker secret mount set is not least-privilege")

    seo = services["seo-agent"]
    if set(seo.get("networks", {})) != {"edge", "seo-egress"}:
        raise SystemExit("SEO agent must use only the internal edge and dedicated SEO egress networks")
    if "data" in seo.get("networks", {}) or "POSTGRES_PASSWORD_FILE" in seo.get("environment", {}):
        raise SystemExit("SEO agent must not receive the PostgreSQL network or credentials")
    if "seo" not in seo.get("profiles", []):
        raise SystemExit("SEO agent must stay behind the explicit seo Compose profile")
    if "seo_agent.scheduler" not in " ".join(seo.get("command", [])):
        raise SystemExit("SEO agent must run its dedicated scheduler")
    seo_environment = seo.get("environment", {})
    if (
        seo_environment.get("CODEX_HOME") != "/var/lib/vedicway/seo-codex-home"
        or seo_environment.get("VEDICWAY_SEO_CODEX_HOME")
        != "/var/lib/vedicway/seo-codex-home"
    ):
        raise SystemExit("SEO agent must use its dedicated Codex home")

    worker_networks = set(services["worker"].get("networks", {}))
    backend_networks = set(services["backend"].get("networks", {}))
    if "edge" in worker_networks or "api-egress" in worker_networks or "worker-egress" not in worker_networks:
        raise SystemExit("worker must use only its dedicated egress contour plus data")
    if "worker-egress" in backend_networks or not {"edge", "data", "api-egress", "ops"}.issubset(backend_networks):
        raise SystemExit("backend API network separation is incomplete")

    dependencies = services["backend"].get("depends_on", {})
    if "content-migrate" not in dependencies:
        raise SystemExit("backend must wait for content-migrate")
    ports = services["frontend"].get("ports", [])
    published_hosts = {str(item.get("host_ip", "")) for item in ports if isinstance(item, dict)}
    if not published_hosts or not published_hosts.issubset({"127.0.0.1", "::1"}):
        raise SystemExit("frontend production port must bind only to loopback")
    ops_ports = services["ops-gateway"].get("ports", [])
    ops_hosts = {str(item.get("host_ip", "")) for item in ops_ports if isinstance(item, dict)}
    if not ops_hosts or not ops_hosts.issubset({"127.0.0.1", "::1"}):
        raise SystemExit("ops gateway must bind only to loopback")
    if set(services["ops-gateway"].get("networks", {})) != {"ops"}:
        raise SystemExit("ops gateway must live only on the isolated ops network")
    if services["backup-bundle"].get("network_mode") != "none":
        raise SystemExit("backup bundle service must have networking disabled")
    if _secret_sources(services["backup-bundle"]) != {"backup_encryption_key"}:
        raise SystemExit("backup bundle service must mount only the backup encryption key")

    entrypoint = (Path(__file__).resolve().parents[1] / "docker/backend/entrypoint.sh").read_text(
        encoding="utf-8"
    )
    if '"$profile" = "worker"' not in entrypoint or "read_secret OPENAI_API_KEY" not in entrypoint or "read_secret CODEX_API_KEY" in entrypoint:
        raise SystemExit("backend entrypoint must export the Codex secret as OPENAI_API_KEY")
    if 'if [ "$profile" = "email" ]' not in entrypoint:
        raise SystemExit("backend entrypoint must isolate the email secret profile")
    if "read_secret VEDICWAY_SMTP_PASSWORD" not in entrypoint:
        raise SystemExit("backend entrypoint must load the SMTP password from a mounted secret")
    if 'if [ "$profile" = "seo-agent" ]' not in entrypoint:
        raise SystemExit("backend entrypoint must isolate the SEO agent secret profile")
    if "read_secret VEDICWAY_SEO_AGENT_TOKEN" not in entrypoint:
        raise SystemExit("backend entrypoint must load the internal SEO bearer token from a secret")

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
    for service_name in ("seo-agent-backup", "seo-agent-restore"):
        if services[service_name].get("network_mode") != "none":
            raise SystemExit(f"{service_name} must not have network access")
        if _secret_sources(services[service_name]):
            raise SystemExit(f"{service_name} must not mount application secrets")
    print("Resolved production Compose contract passed.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
from pathlib import Path

CONTAINER_SECRET_PATHS = {
    "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
    "VEDICWAY_DATA_KEY_FILE": "/run/secrets/vedicway_data_key",
    "VEDICWAY_SIGNING_KEY_FILE": "/run/secrets/vedicway_signing_key",
    "VEDICWAY_OPERATIONS_TOKEN_FILE": "/run/secrets/vedicway_operations_token",
    "VEDICWAY_METRICS_TOKEN_FILE": "/run/secrets/vedicway_metrics_token",
    "YOOKASSA_SHOP_ID_FILE": "/run/secrets/yookassa_shop_id",
    "YOOKASSA_SECRET_KEY_FILE": "/run/secrets/yookassa_secret_key",
    "OPENAI_API_KEY_FILE": "/run/secrets/codex_api_key",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate resolved production Compose contract")
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    services = payload.get("services", {})
    required = {"postgres", "migrate", "content-migrate", "backend", "worker", "frontend"}
    missing = required.difference(services)
    if missing:
        raise SystemExit(f"Missing production services: {', '.join(sorted(missing))}")

    for service_name in ("backend", "worker"):
        service = services[service_name]
        environment = service.get("environment", {})
        for name, expected in CONTAINER_SECRET_PATHS.items():
            if environment.get(name) != expected:
                raise SystemExit(f"{service_name}.{name} must resolve to {expected}")
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
    print("Resolved production Compose contract passed.")


if __name__ == "__main__":
    main()

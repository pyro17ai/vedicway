from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .store import Store

RETENTION_ENV = {
    "anonymous_chart_days": "VEDICWAY_RETENTION_ANONYMOUS_CHART_DAYS",
    "report_days": "VEDICWAY_RETENTION_REPORT_DAYS",
    "security_log_days": "VEDICWAY_RETENTION_SECURITY_LOG_DAYS",
    "financial_record_days": "VEDICWAY_RETENTION_FINANCIAL_RECORD_DAYS",
    "backup_days": "VEDICWAY_RETENTION_BACKUP_DAYS",
}


def _positive_int(name: str, *, default: int | None = None) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class RetentionSettings:
    anonymous_chart_days: int
    report_days: int
    security_log_days: int
    financial_record_days: int | None
    backup_days: int | None

    @classmethod
    def from_environment(cls) -> RetentionSettings:
        production = os.environ.get("VEDICWAY_ENV", "development").casefold() == "production"
        anonymous = _positive_int(
            RETENTION_ENV["anonymous_chart_days"], default=None if production else 30
        )
        reports = _positive_int(RETENTION_ENV["report_days"], default=None if production else 30)
        security = _positive_int(
            RETENTION_ENV["security_log_days"], default=None if production else 30
        )
        if anonymous is None or reports is None or security is None:
            raise RuntimeError("production retention periods must be configured explicitly")
        financial = _positive_int(RETENTION_ENV["financial_record_days"])
        backups = _positive_int(RETENTION_ENV["backup_days"])
        if production and (financial is None or backups is None):
            raise RuntimeError("production financial and backup retention periods must be configured")
        return cls(
            anonymous_chart_days=anonymous,
            report_days=reports,
            security_log_days=security,
            financial_record_days=financial,
            backup_days=backups,
        )


def production_retention_configuration_errors() -> list[str]:
    if os.environ.get("VEDICWAY_ENV", "development").casefold() != "production":
        return []
    errors: list[str] = []
    for env_name in RETENTION_ENV.values():
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            errors.append(f"missing:{env_name}")
            continue
        try:
            if int(raw) < 1:
                raise ValueError
        except ValueError:
            errors.append(f"invalid:{env_name}")
    return errors


def lifecycle_plan(store: Store, settings: RetentionSettings) -> dict[str, Any]:
    return store.retention_plan(
        anonymous_chart_days=settings.anonymous_chart_days,
        report_days=settings.report_days,
    )


def run_lifecycle(store: Store, settings: RetentionSettings, *, apply: bool) -> dict[str, Any]:
    plan = lifecycle_plan(store, settings)
    summary = {
        "mode": "apply" if apply else "dry-run",
        "anonymous_chart_candidates": len(plan["anonymous_chart_ids"]),
        "expired_report_candidates": len(plan["expired_reports"]),
        "pending_tombstones": len(plan["pending_tombstone_chart_ids"]),
        "financial_record_days": settings.financial_record_days,
        "backup_days": settings.backup_days,
    }
    if not apply:
        return summary
    return {**summary, **store.apply_retention_plan(plan, security_log_days=settings.security_log_days)}

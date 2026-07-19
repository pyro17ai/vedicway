from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from vedicway_backend.email_delivery import (
    EmailDispatcher,
    EmailSettings,
    production_email_configuration_errors,
)
from vedicway_backend.email_worker import EmailWorker
from vedicway_backend.errors import DomainError
from vedicway_backend.main import create_app
from vedicway_backend.places import PlaceRegistry
from vedicway_backend.retention import (
    RetentionSettings,
    production_retention_configuration_errors,
    run_lifecycle,
)
from vedicway_backend.schemas import ChartCreateRequest, PdfRenderPreferences
from vedicway_backend.store import Store
from vedicway_backend.time_normalization import resolve_birth_input
from vedicway_backend.worker import ChartWorker


class RecordingEmailProvider:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send(self, *, recipient: str, subject: str, text: str, html_body: str) -> str:
        self.messages.append(
            {
                "recipient": recipient,
                "subject": subject,
                "text": text,
                "html": html_body,
            }
        )
        return f"message-{len(self.messages)}"


class NoopWorker:
    def drain(self, _limit: int) -> int:
        return 0


def _birth():
    request = ChartCreateRequest(
        local_date=date(1998, 9, 15),
        local_time="17:28",
        place_id="ru-moscow-524901",
    )
    return resolve_birth_input(request, PlaceRegistry().get(request.place_id))


def _email_settings() -> EmailSettings:
    return EmailSettings(
        host="smtp.test",
        port=587,
        username="user",
        password="secret",
        from_email="no-reply@vedicway.test",
        from_name="VedicWay",
        public_origin="https://vedicway.test",
        use_ssl=False,
        starttls=True,
        timeout_seconds=1,
    )


def _ready_paid_chart(store: Store, email: str = "buyer@example.com") -> tuple[str, str, str]:
    session_id, _ = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "chart-ready")
    purchase, _ = store.create_purchase(chart_id, "purchase-ready", email)
    assert store.confirm_purchase(purchase["id"], "event-ready") == chart_id
    _, render_request_id = store.enqueue_pdf_job(
        chart_id, PdfRenderPreferences().model_dump(mode="json")
    )
    path = store.reports_dir / f"{render_request_id}.pdf"
    path.write_bytes(b"%PDF-1.4\n%%EOF")
    render = store.get_pdf_render_request(render_request_id)
    assert render is not None
    store.commit_report_event(
        chart_id,
        "ready",
        {"render_request_id": render_request_id},
        path=str(path),
        checksum="sha256:test",
        size_bytes=path.stat().st_size,
        pages=1,
        render_request_id=render_request_id,
        preferences_checksum=render["preferences_checksum"],
    )
    return chart_id, str(purchase["id"]), render_request_id


def test_recovery_response_does_not_enumerate_known_email(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    _ready_paid_chart(store)
    app = create_app(store=store, worker=NoopWorker())
    with TestClient(app) as client:
        known = client.post("/api/v1/access/recovery", json={"email": "buyer@example.com"})
        unknown = client.post("/api/v1/access/recovery", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"status": "accepted"}


def test_store_exposes_no_direct_magic_link_redemption_bypass() -> None:
    assert not hasattr(Store, "consume_magic_link")
    assert not hasattr(Store, "redeem_magic_link")
    assert hasattr(Store, "consume_magic_link_confirmation")


def test_magic_confirmation_validation_never_reports_birth_form_error(tmp_path) -> None:
    app = create_app(store=Store(tmp_path / "runtime"), worker=NoopWorker())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/magic-links/confirm",
            data={},
            headers={"Origin": "http://testserver"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Подтверждение ссылки устарело"


def test_recovery_email_uses_scoped_single_use_links_and_sends_once(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    chart_id, purchase_id, render_request_id = _ready_paid_chart(store)
    provider = RecordingEmailProvider()
    dispatcher = EmailDispatcher(store, settings=_email_settings(), provider=provider)

    store.enqueue_access_recovery(" BUYER@example.com ")
    assert dispatcher.process_once()
    assert len(provider.messages) == 1
    assert provider.messages[0]["recipient"] == "buyer@example.com"
    assert "buyer@example.com" not in provider.messages[0]["html"]
    assert b"buyer@example.com" not in store.db_path.read_bytes()

    links = re.findall(r'href="([^"]+/api/v1/magic-links/[^"]+)"', provider.messages[0]["html"])
    assert len(links) == 2
    app = create_app(store=store, worker=NoopWorker())
    chart_path = urlsplit(links[0]).path
    with store._connection() as connection:
        access_count_before = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM chart_access WHERE chart_id = ?", (chart_id,)
            ).fetchone()["count"]
        )

    with TestClient(app) as scanner:
        prefetched = scanner.get(chart_path, follow_redirects=False)
        assert prefetched.status_code == 303
        assert prefetched.headers["location"] == "/access/confirm"
        assert prefetched.headers["referrer-policy"] == "no-referrer"
        assert scanner.cookies.get("vw_session") is None
        scanner_nonce = scanner.cookies.get("vw_magic_preauth")
        scanner_csrf = scanner.cookies.get("vw_magic_csrf")
        assert scanner_nonce and scanner_csrf
        with store._connection() as connection:
            assert connection.execute(
                "SELECT used_at FROM magic_links ORDER BY created_at LIMIT 1"
            ).fetchone()["used_at"] is None
            assert int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM chart_access WHERE chart_id = ?", (chart_id,)
                ).fetchone()["count"]
            ) == access_count_before

        rejected_origins = (
            {"Origin": "null"},
            {
                "Origin": "null",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "no-cors",
            },
        )
        for headers in rejected_origins:
            rejected = scanner.post(
                "/api/v1/magic-links/confirm",
                data={"csrf_token": scanner_csrf},
                headers=headers,
                follow_redirects=False,
            )
            assert rejected.status_code == 403
            assert scanner.cookies.get("vw_session") is None
            with store._connection() as connection:
                assert connection.execute(
                    "SELECT used_at FROM magic_links ORDER BY created_at LIMIT 1"
                ).fetchone()["used_at"] is None
                assert int(
                    connection.execute(
                        "SELECT COUNT(*) AS count FROM magic_link_confirmations "
                        "WHERE used_at IS NOT NULL"
                    ).fetchone()["count"]
                ) == 0
                assert int(
                    connection.execute(
                        "SELECT COUNT(*) AS count FROM chart_access WHERE chart_id = ?",
                        (chart_id,),
                    ).fetchone()["count"]
                ) == access_count_before

        with TestClient(app) as visitor:
            chart_link = visitor.get(chart_path, follow_redirects=False)
            assert chart_link.status_code == 303
            assert chart_link.headers["location"] == "/access/confirm"
            nonce = visitor.cookies.get("vw_magic_preauth")
            csrf = visitor.cookies.get("vw_magic_csrf")
            assert nonce and csrf
            confirmed = visitor.post(
                "/api/v1/magic-links/confirm",
                data={"csrf_token": csrf},
                headers={"Origin": "http://testserver"},
                follow_redirects=False,
            )
            assert confirmed.status_code == 303
            assert confirmed.headers["location"] == f"/chart/{chart_id}"
            assert visitor.cookies.get("vw_session")
            assert visitor.cookies.get("vw_magic_preauth") is None
            assert visitor.get(f"/api/v1/charts/{chart_id}").status_code == 200
            assert visitor.get(chart_path, follow_redirects=False).status_code == 401

        replay = scanner.post(
            "/api/v1/magic-links/confirm",
            data={"csrf_token": scanner_csrf},
            headers={"Origin": "http://testserver"},
            follow_redirects=False,
        )
        assert replay.status_code == 401
        assert scanner.cookies.get("vw_session") is None

    with TestClient(app) as visitor:
        pdf_link = visitor.get(urlsplit(links[1]).path, follow_redirects=False)
        assert pdf_link.status_code == 303
        csrf = visitor.cookies.get("vw_magic_csrf")
        assert csrf
        pdf_confirmed = visitor.post(
            "/api/v1/magic-links/confirm",
            data={"csrf_token": csrf},
            headers={"Origin": "http://testserver"},
            follow_redirects=False,
        )
        assert pdf_confirmed.status_code == 303
        assert f"render_request_id={render_request_id}" in pdf_confirmed.headers["location"]

    first = store.enqueue_purchase_ready_email(chart_id, render_request_id)
    duplicate = store.enqueue_purchase_ready_email(chart_id, render_request_id)
    later_render = store.enqueue_purchase_ready_email(chart_id, "pdfreq-later")
    assert first is not None and duplicate is None and later_render is None
    assert dispatcher.process_once()
    assert len(provider.messages) == 2
    with store._connection() as connection:
        deliveries = connection.execute(
            "SELECT COUNT(*) AS count FROM email_deliveries WHERE purchase_id = ? AND purpose = 'purchase_ready'",
            (purchase_id,),
        ).fetchone()
    assert int(deliveries["count"]) == 1


def test_unknown_recovery_is_a_no_match_without_sending(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    provider = RecordingEmailProvider()
    dispatcher = EmailDispatcher(store, settings=_email_settings(), provider=provider)
    delivery_id = store.enqueue_access_recovery("unknown@example.com")
    assert dispatcher.process_once() == delivery_id
    assert provider.messages == []
    with store._connection() as connection:
        delivery = connection.execute(
            "SELECT status FROM email_deliveries WHERE id = ?", (delivery_id,)
        ).fetchone()
    assert delivery["status"] == "no_match"


def test_calculation_worker_cannot_claim_transactional_email(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    delivery_id = store.enqueue_access_recovery("unknown@example.com")
    outcome = ChartWorker(store).process_once()
    assert outcome.handled is False
    with store._connection() as connection:
        pending = connection.execute(
            "SELECT status FROM email_deliveries WHERE id = ?", (delivery_id,)
        ).fetchone()
    assert pending["status"] == "queued"

    provider = RecordingEmailProvider()
    email_worker = EmailWorker(
        EmailDispatcher(store, settings=_email_settings(), provider=provider)
    )
    assert email_worker.process_once() is True
    assert provider.messages == []
    with store._connection() as connection:
        completed = connection.execute(
            "SELECT status FROM email_deliveries WHERE id = ?", (delivery_id,)
        ).fetchone()
    assert completed["status"] == "no_match"


def test_owned_delete_is_private_transactional_and_never_unlinks_outside_reports(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    owner_session, owner_token = store.create_session()
    chart_id, _ = store.create_chart(owner_session, _birth(), "owned-delete")
    safe_path = store.reports_dir / "safe.pdf"
    safe_path.write_bytes(b"safe")
    outside_path = tmp_path / "outside.pdf"
    outside_path.write_bytes(b"outside")
    _, request_id = store.enqueue_pdf_job(
        chart_id, PdfRenderPreferences().model_dump(mode="json")
    )
    with store._connection() as connection:
        connection.execute(
            "UPDATE pdf_render_requests SET status = 'ready', path = ? WHERE id = ?",
            (str(safe_path), request_id),
        )
        connection.execute(
            "UPDATE reports SET status = 'ready', path = ? WHERE chart_id = ?",
            (str(outside_path), chart_id),
        )
    other_session, other_token = store.create_session()
    assert other_session != owner_session
    app = create_app(store=store, worker=NoopWorker())
    with TestClient(app) as client:
        client.cookies.set("vw_session", other_token)
        assert client.delete(f"/api/v1/charts/{chart_id}").status_code == 404
        client.cookies.set("vw_session", owner_token)
        response = client.delete(f"/api/v1/charts/{chart_id}")
        assert response.status_code == 204
        assert client.get(f"/api/v1/charts/{chart_id}").status_code in {401, 404}
    assert not safe_path.exists()
    assert outside_path.exists()
    with store._connection() as connection:
        tombstone = connection.execute(
            "SELECT status, last_error_code FROM erasure_tombstones WHERE chart_id = ?", (chart_id,)
        ).fetchone()
    assert tombstone["status"] == "pending_files"
    assert tombstone["last_error_code"] == "UNSAFE_REPORT_PATH"


def test_privacy_intake_is_encrypted_and_lifecycle_is_dry_run_then_idempotent_apply(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    session_id, _ = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "retention")
    old = (datetime.now(UTC) - timedelta(days=40)).replace(microsecond=0).isoformat()
    with store._connection() as connection:
        connection.execute(
            "UPDATE charts SET created_at = ?, updated_at = ? WHERE id = ?", (old, old, chart_id)
        )
    app = create_app(store=store, worker=NoopWorker())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/privacy/requests",
            json={"type": "erase", "email": "privacy@example.com"},
        )
    assert response.status_code == 202
    assert b"privacy@example.com" not in store.db_path.read_bytes()

    settings = RetentionSettings(
        anonymous_chart_days=30,
        report_days=30,
        security_log_days=30,
        financial_record_days=None,
        backup_days=None,
    )
    dry_run = run_lifecycle(store, settings, apply=False)
    assert dry_run["anonymous_chart_candidates"] == 1
    assert store.chart_owned_by(chart_id, session_id)
    applied = run_lifecycle(store, settings, apply=True)
    assert applied["erased_anonymous_charts"] == 1
    second = run_lifecycle(store, settings, apply=True)
    assert second["erased_anonymous_charts"] == 0


def test_erasure_refuses_a_running_job_and_preserves_the_chart(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    session_id, _ = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "active-job")
    with store._connection() as connection:
        connection.execute(
            "UPDATE jobs SET status = 'running' WHERE chart_id = ?", (chart_id,)
        )
    with pytest.raises(DomainError) as raised:
        store.erase_chart_personal_data(chart_id)
    assert raised.value.code == "ERASURE_JOB_ACTIVE"
    assert store.chart_owned_by(chart_id, session_id)


def test_production_retention_preflight_requires_explicit_periods(monkeypatch) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    for name in (
        "VEDICWAY_RETENTION_ANONYMOUS_CHART_DAYS",
        "VEDICWAY_RETENTION_REPORT_DAYS",
        "VEDICWAY_RETENTION_SECURITY_LOG_DAYS",
        "VEDICWAY_RETENTION_FINANCIAL_RECORD_DAYS",
        "VEDICWAY_RETENTION_BACKUP_DAYS",
    ):
        monkeypatch.delenv(name, raising=False)
    errors = production_retention_configuration_errors()
    assert len(errors) == 5
    assert "missing:VEDICWAY_RETENTION_FINANCIAL_RECORD_DAYS" in errors
    email_errors = production_email_configuration_errors()
    assert "missing:VEDICWAY_SMTP_HOST" in email_errors
    assert "missing:VEDICWAY_SMTP_PASSWORD" in email_errors
    api_email_errors = production_email_configuration_errors(require_password=False)
    assert "missing:VEDICWAY_SMTP_PASSWORD" not in api_email_errors


def test_production_email_preflight_accepts_only_https_and_one_tls_mode(monkeypatch) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    values = {
        "VEDICWAY_SMTP_HOST": "smtp.vedicway.test",
        "VEDICWAY_SMTP_PORT": "587",
        "VEDICWAY_SMTP_USERNAME": "transactional",
        "VEDICWAY_SMTP_PASSWORD": "secret-password",
        "VEDICWAY_SMTP_FROM_EMAIL": "no-reply@vedicway.test",
        "VEDICWAY_PUBLIC_ORIGIN": "https://vedicway.test",
        "VEDICWAY_SMTP_SSL": "0",
        "VEDICWAY_SMTP_STARTTLS": "1",
        "VEDICWAY_SMTP_TIMEOUT_SECONDS": "10",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    assert production_email_configuration_errors() == []

    monkeypatch.setenv("VEDICWAY_PUBLIC_ORIGIN", "http://vedicway.test")
    monkeypatch.setenv("VEDICWAY_SMTP_SSL", "1")
    errors = production_email_configuration_errors()
    assert "invalid:VEDICWAY_PUBLIC_ORIGIN" in errors
    assert "invalid:VEDICWAY_SMTP_TRANSPORT_SECURITY" in errors


def test_production_files_wire_smtp_secret_recovery_routes_and_lifecycle_jobs() -> None:
    root = Path(__file__).resolve().parents[2]
    production_env = (root / ".env.production.example").read_text(encoding="utf-8")
    compose = (root / "compose.production.yml").read_text(encoding="utf-8")
    entrypoint = (root / "docker/backend/entrypoint.sh").read_text(encoding="utf-8")
    backend_dockerfile = (root / "docker/backend/Dockerfile").read_text(encoding="utf-8")
    nginx = (root / "docker/nginx/nginx.conf").read_text(encoding="utf-8")

    assert "VEDICWAY_SMTP_PASSWORD_FILE=./secrets/smtp_password.txt" in production_env
    for name in (
        "VEDICWAY_RETENTION_ANONYMOUS_CHART_DAYS",
        "VEDICWAY_RETENTION_REPORT_DAYS",
        "VEDICWAY_RETENTION_SECURITY_LOG_DAYS",
        "VEDICWAY_RETENTION_FINANCIAL_RECORD_DAYS",
        "VEDICWAY_RETENTION_BACKUP_DAYS",
    ):
        assert f"{name}=" in production_env
    assert "read_secret VEDICWAY_SMTP_PASSWORD" in entrypoint
    assert "VEDICWAY_SECRET_PROFILE: email" in compose
    assert "vedicway_backend.email_worker" in compose
    assert "retention-dry-run:" in compose
    assert "retention-apply:" in compose
    assert "network_mode: none" in compose
    assert "location ^~ /api/v1/magic-links/" in nginx
    assert nginx.count("access_log off;") >= 2
    assert '"--no-access-log"' in backend_dockerfile
    assert 'location = /access/recovery {' in nginx
    assert 'location = /access/confirm {' in nginx
    assert 'location = /privacy/request {' in nginx

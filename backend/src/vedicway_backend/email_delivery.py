from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol
from urllib.parse import urlsplit

from .pdf import rectification_report_pdf
from .schemas import RectificationResult
from .store import Store

logger = logging.getLogger(__name__)


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class EmailSettings:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    from_name: str
    public_origin: str
    use_ssl: bool
    starttls: bool
    timeout_seconds: float

    @property
    def configured(self) -> bool:
        return bool(
            self.host
            and self.from_email
            and self.public_origin
            and 1 <= self.port <= 65535
            and self.timeout_seconds > 0
        )

    @classmethod
    def from_environment(cls) -> EmailSettings:
        use_ssl = _enabled(os.environ.get("VEDICWAY_SMTP_SSL"))
        raw_port = os.environ.get("VEDICWAY_SMTP_PORT", "465" if use_ssl else "587")
        raw_timeout = os.environ.get("VEDICWAY_SMTP_TIMEOUT_SECONDS", "10")
        try:
            port = int(raw_port)
        except ValueError:
            port = 0
        try:
            timeout_seconds = float(raw_timeout)
        except ValueError:
            timeout_seconds = 0
        configured_origin = (
            os.environ.get("VEDICWAY_PUBLIC_ORIGIN")
            or os.environ.get("VEDICWAY_PUBLIC_BASE_URL")
            or ""
        ).rstrip("/")
        if not configured_origin and os.environ.get("VEDICWAY_ENV", "development").casefold() != "production":
            configured_origin = "http://127.0.0.1:5173"
        return cls(
            host=os.environ.get("VEDICWAY_SMTP_HOST", "").strip(),
            port=port,
            username=os.environ.get("VEDICWAY_SMTP_USERNAME", "").strip(),
            password=os.environ.get("VEDICWAY_SMTP_PASSWORD", ""),
            from_email=os.environ.get("VEDICWAY_SMTP_FROM_EMAIL", "").strip(),
            from_name=os.environ.get("VEDICWAY_SMTP_FROM_NAME", "VedicWay").strip() or "VedicWay",
            public_origin=configured_origin,
            use_ssl=use_ssl,
            starttls=_enabled(os.environ.get("VEDICWAY_SMTP_STARTTLS"), default=not use_ssl),
            timeout_seconds=timeout_seconds,
        )


def production_email_configuration_errors(*, require_password: bool = True) -> list[str]:
    if os.environ.get("VEDICWAY_ENV", "development").casefold() != "production":
        return []
    required = (
        "VEDICWAY_SMTP_HOST",
        "VEDICWAY_SMTP_PORT",
        "VEDICWAY_SMTP_USERNAME",
        "VEDICWAY_SMTP_FROM_EMAIL",
        "VEDICWAY_PUBLIC_ORIGIN",
    )
    if require_password:
        required = (*required, "VEDICWAY_SMTP_PASSWORD")
    errors = [f"missing:{name}" for name in required if not os.environ.get(name, "").strip()]
    try:
        port = int(os.environ.get("VEDICWAY_SMTP_PORT", "0"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        if "missing:VEDICWAY_SMTP_PORT" not in errors:
            errors.append("invalid:VEDICWAY_SMTP_PORT")
    origin = urlsplit(os.environ.get("VEDICWAY_PUBLIC_ORIGIN", ""))
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
    ):
        errors.append("invalid:VEDICWAY_PUBLIC_ORIGIN")
    from_email = os.environ.get("VEDICWAY_SMTP_FROM_EMAIL", "")
    if from_email.count("@") != 1 or "." not in from_email.rpartition("@")[2]:
        errors.append("invalid:VEDICWAY_SMTP_FROM_EMAIL")
    use_ssl = _enabled(os.environ.get("VEDICWAY_SMTP_SSL"))
    use_starttls = _enabled(os.environ.get("VEDICWAY_SMTP_STARTTLS"))
    if use_ssl == use_starttls:
        errors.append("invalid:VEDICWAY_SMTP_TRANSPORT_SECURITY")
    try:
        timeout = float(os.environ.get("VEDICWAY_SMTP_TIMEOUT_SECONDS", ""))
        if timeout <= 0 or timeout > 60:
            raise ValueError
    except ValueError:
        errors.append("invalid:VEDICWAY_SMTP_TIMEOUT_SECONDS")
    return errors


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    content: bytes


class EmailProvider(Protocol):
    def send(
        self,
        *,
        recipient: str,
        subject: str,
        text: str,
        html_body: str,
        attachments: tuple[EmailAttachment, ...] = (),
    ) -> str: ...


class SmtpEmailProvider:
    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    def send(
        self,
        *,
        recipient: str,
        subject: str,
        text: str,
        html_body: str,
        attachments: tuple[EmailAttachment, ...] = (),
    ) -> str:
        settings = self.settings
        message = EmailMessage()
        message["From"] = formataddr((settings.from_name, settings.from_email))
        message["To"] = recipient
        message["Subject"] = subject
        message_id = make_msgid(domain=settings.from_email.rpartition("@")[2] or None)
        message["Message-ID"] = message_id
        message.set_content(text)
        message.add_alternative(html_body, subtype="html")
        for attachment in attachments:
            message.add_attachment(
                attachment.content,
                maintype="application",
                subtype="pdf",
                filename=attachment.filename,
            )
        context = ssl.create_default_context()
        if settings.use_ssl:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.host,
                settings.port,
                timeout=settings.timeout_seconds,
                context=context,
            )
        else:
            client = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout_seconds)
        with client:
            if settings.starttls and not settings.use_ssl:
                client.starttls(context=context)
            if settings.username:
                client.login(settings.username, settings.password)
            client.send_message(message)
        return message_id


class EmailDispatcher:
    def __init__(
        self,
        store: Store,
        *,
        settings: EmailSettings | None = None,
        provider: EmailProvider | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or EmailSettings.from_environment()
        self.provider = provider or (
            SmtpEmailProvider(self.settings) if self.settings.configured else None
        )

    def process_once(self) -> str | None:
        delivery = self.store.claim_next_email_delivery()
        if not delivery:
            return None
        delivery_id = str(delivery["id"])
        if self.provider is None:
            self.store.finish_email_delivery(
                delivery_id,
                status="blocked_configuration",
                error_code="SMTP_NOT_CONFIGURED",
            )
            return delivery_id
        tokens: list[str] = []
        try:
            purpose = str(delivery["purpose"])
            links: list[tuple[str, str | None]] = []
            message: tuple[str, str] | None = None
            attachments: tuple[EmailAttachment, ...] = ()
            if purpose == "access_recovery":
                targets = self.store.recovery_targets(str(delivery["email_lookup_hmac"]))
                if not targets:
                    self.store.finish_email_delivery(delivery_id, status="no_match")
                    return delivery_id
                recipient = str(targets[0]["email"])
                for target in targets[:10]:
                    chart_token = self.store.create_magic_link(
                        str(target["chart_id"]), scope=str(target["scope"])
                    )
                    tokens.append(chart_token)
                    chart_url = f"{self.settings.public_origin}/api/v1/magic-links/{chart_token}"
                    pdf_url: str | None = None
                    if target["render_request_id"]:
                        pdf_token = self.store.create_magic_link(
                            str(target["chart_id"]),
                            scope="download_pdf",
                            render_request_id=str(target["render_request_id"]),
                        )
                        tokens.append(pdf_token)
                        pdf_url = f"{self.settings.public_origin}/api/v1/magic-links/{pdf_token}"
                    links.append((chart_url, pdf_url))
                subject = "Доступ к вашим материалам VedicWay"
            elif purpose == "purchase_ready":
                target = self.store.purchase_ready_target(
                    str(delivery["purchase_id"]), str(delivery["render_request_id"])
                )
                if target is None:
                    self.store.finish_email_delivery(delivery_id, status="no_match")
                    return delivery_id
                recipient = str(target["email"])
                chart_token = self.store.create_magic_link(
                    str(target["chart_id"]), scope="read_chart"
                )
                tokens.append(chart_token)
                links = [
                    (
                        f"{self.settings.public_origin}/api/v1/magic-links/{chart_token}",
                        None,
                    )
                ]
                report_path = self.store.report_file_path(
                    str(target["chart_id"]), str(target["render_request_id"])
                )
                if report_path is None or not report_path.is_file():
                    raise FileNotFoundError(str(target["render_request_id"]))
                attachments = (
                    EmailAttachment("vedicway-full-report.pdf", report_path.read_bytes()),
                )
                message = self._access_message(links, pdf_attached=True)
                subject = "Ваш полный разбор VedicWay готов"
            elif purpose == "rectification_ready":
                target = self.store.rectification_ready_target(str(delivery["purchase_id"]))
                if target is None:
                    self.store.finish_email_delivery(delivery_id, status="no_match")
                    return delivery_id
                recipient = str(target["email"])
                chart_token = self.store.create_magic_link(
                    str(target["chart_id"]), scope="read_rectification"
                )
                tokens.append(chart_token)
                rectification_url = (
                    f"{self.settings.public_origin}/api/v1/magic-links/{chart_token}"
                )
                result = RectificationResult.model_validate(target["result"])
                subject = "Ректификация времени рождения VedicWay готова"
                message = self._rectification_message(rectification_url, result)
                attachments = (
                    EmailAttachment(
                        "vedicway-birth-time-report.pdf",
                        rectification_report_pdf(
                            self.store.get_birth(str(target["chart_id"])), result
                        ),
                    ),
                )
            else:
                self.store.finish_email_delivery(
                    delivery_id, status="failed", error_code="EMAIL_PURPOSE_UNKNOWN"
                )
                return delivery_id
            text, html_body = message or self._access_message(links)
            provider_message_id = self.provider.send(
                recipient=recipient,
                subject=subject,
                text=text,
                html_body=html_body,
                attachments=attachments,
            )
            self.store.finish_email_delivery(
                delivery_id,
                status="succeeded",
                provider_message_id=provider_message_id,
            )
        except Exception as exc:
            logger.exception(
                "Transactional email delivery failed: delivery_id=%s purpose=%s error_type=%s",
                delivery_id,
                delivery.get("purpose"),
                type(exc).__name__,
            )
            self.store.revoke_magic_links(tokens)
            self.store.finish_email_delivery(
                delivery_id,
                status="failed",
                error_code="SMTP_DELIVERY_FAILED",
                retryable=True,
            )
        return delivery_id

    @staticmethod
    def _access_message(
        links: list[tuple[str, str | None]], *, pdf_attached: bool = False
    ) -> tuple[str, str]:
        text_lines = [
            "Ваши материалы VedicWay доступны по одноразовым ссылкам.",
            "Ссылки действуют 1 час и перестают работать после подтверждения доступа на сайте.",
        ]
        if pdf_attached:
            text_lines.insert(0, "Готовый PDF-отчёт приложен к письму.")
        html_items: list[str] = []
        for index, (chart_url, pdf_url) in enumerate(links, start=1):
            text_lines.append(f"Карта {index}: {chart_url}")
            html_line = f'<a href="{html.escape(chart_url)}">Открыть карту {index}</a>'
            if pdf_url:
                text_lines.append(f"PDF {index}: {pdf_url}")
                html_line += f' · <a href="{html.escape(pdf_url)}">Скачать PDF</a>'
            html_items.append(f"<li>{html_line}</li>")
        text_lines.append("Если вы не запрашивали письмо, просто проигнорируйте его.")
        html_body = (
            ("<p><strong>Готовый PDF-отчёт приложен к письму.</strong></p>" if pdf_attached else "")
            + "<p>Ваши материалы VedicWay доступны по одноразовым ссылкам.</p>"
            "<p>Ссылки действуют 1 час и перестают работать после подтверждения доступа на сайте.</p>"
            f"<ul>{''.join(html_items)}</ul>"
            "<p>Если вы не запрашивали письмо, просто проигнорируйте его.</p>"
        )
        return "\n\n".join(text_lines), html_body

    @staticmethod
    def _rectification_message(url: str, result: RectificationResult) -> tuple[str, str]:
        uncertainty_text = f"±{result.uncertainty_minutes} минут"
        text = (
            "Ректификация времени рождения завершена.\n\n"
            f"Выбранное время: {result.selected_time}.\n"
            f"Диапазон неопределённости: {uncertainty_text}.\n"
            f"Лагна: {result.lagna}.\n\n"
            "PDF-отчёт приложен к письму.\n\n"
            f"Открыть полный результат: {url}\n\n"
            "Ссылка действует 1 час и перестаёт работать после подтверждения доступа на сайте."
        )
        html_body = (
            "<p>Ректификация времени рождения завершена.</p>"
            f"<p><strong>Выбранное время: {html.escape(result.selected_time)}</strong><br>"
            f"Диапазон неопределённости: {html.escape(uncertainty_text)}.<br>"
            f"Лагна: {html.escape(result.lagna)}.</p>"
            "<p>PDF-отчёт приложен к письму.</p>"
            f'<p><a href="{html.escape(url)}">Открыть полный результат</a></p>'
            "<p>Ссылка действует 1 час и перестаёт работать после подтверждения доступа на сайте.</p>"
        )
        return text, html_body

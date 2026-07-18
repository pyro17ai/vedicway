from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import Body, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware

from .calculator import warm_instant_runtime
from .errors import DomainError
from .payment_config import PaymentSettings
from .payment_security import effective_client_ip, is_yookassa_source
from .payments import PaymentProvider, PaymentStatus, payment_provider_from_settings
from .places import PlaceRegistry
from .observability import Metrics
from .schemas import ChartAccepted, ChartCreateRequest, PurchaseRequest, PurchaseResponse
from .store import Store
from .time_normalization import resolve_birth_input
from .worker import ChartWorker

LOGGER = logging.getLogger("vedicway.api")
SESSION_COOKIE = "vw_session"
ALLOWED_SECTIONS = {"d1", "vargas", "panchanga", "dashas", "strength", "combinations", "interpretation", "questions"}
ALLOWED_JOB_TYPES = {"instant_v1", "evidence_free_v1", "expert_extended_v1", "interpretation_free_v1", "paid_report_v1", "pdf_v1"}


@dataclass(slots=True)
class RateLimiter:
    entries: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def check(self, key: str, limit: int = 12, window_seconds: float = 60) -> None:
        now = time.monotonic()
        async with self.lock:
            bucket = self.entries[key]
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                raise DomainError("RATE_LIMITED", "Слишком много запросов. Попробуйте через час.", status_code=429)
            bucket.append(now)


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", uuid.uuid4().hex)


def _error_response(error: DomainError, trace_id: str) -> JSONResponse:
    headers = {"X-Trace-ID": trace_id}
    if error.code == "RATE_LIMITED":
        headers["Retry-After"] = "3600"
    return JSONResponse(status_code=error.status_code, content=error.as_payload(trace_id), headers=headers)


def _sse_frame(event: str | None = None, data: dict[str, Any] | None = None, event_id: int | None = None, retry: int | None = None, comment: str | None = None) -> str:
    lines: list[str] = []
    if comment:
        lines.append(f": {comment}")
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    if retry is not None:
        lines.append(f"retry: {retry}")
    if data is not None:
        lines.extend(f"data: {line}" for line in json.dumps(data, ensure_ascii=False, separators=(",", ":")).splitlines())
    return "\n".join(lines) + "\n\n"


async def _launch_worker(app: FastAPI) -> None:
    task = getattr(app.state, "worker_task", None)
    if task and not task.done():
        return

    async def run() -> None:
        await asyncio.to_thread(app.state.worker.drain, 16)

    app.state.worker_task = asyncio.create_task(run())


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(warm_instant_runtime)
    except DomainError:
        LOGGER.warning("instant calculation runtime will be retried by the worker", exc_info=True)
    try:
        yield
    finally:
        await app.state.payment_provider.aclose()


def create_app(
    store: Store | None = None,
    worker: ChartWorker | None = None,
    *,
    payment_settings: PaymentSettings | None = None,
    payment_provider: PaymentProvider | None = None,
) -> FastAPI:
    app = FastAPI(title="VedicWay BFF", version="1.0.0", docs_url=None, redoc_url=None, lifespan=_lifespan)
    app.state.store = store or Store()
    app.state.metrics = Metrics()
    app.state.worker = worker or ChartWorker(app.state.store, metrics=app.state.metrics)
    app.state.places = PlaceRegistry()
    app.state.limiter = RateLimiter()
    app.state.payment_settings = payment_settings or PaymentSettings.from_environment()
    app.state.payment_provider = payment_provider or payment_provider_from_settings(app.state.payment_settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key", "If-None-Match", "Last-Event-ID", "X-Client-Version"],
    )

    @app.middleware("http")
    async def trace_and_errors(request: Request, call_next):
        request.state.trace_id = uuid.uuid4().hex
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except DomainError as error:
            response = _error_response(error, _trace_id(request))
        except HTTPException as error:
            response = JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers={"X-Trace-ID": _trace_id(request)})
        except Exception:
            LOGGER.exception("unexpected_api_error trace_id=%s path=%s", _trace_id(request), request.url.path)
            response = _error_response(
                DomainError("INTERNAL_ERROR", "Сервис временно недоступен", recoverable=True, status_code=500),
                _trace_id(request),
            )
        response.headers["X-Trace-ID"] = _trace_id(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if os.environ.get("VEDICWAY_ENV") == "production":
            response.headers["Content-Security-Policy"] = "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; connect-src 'self'"
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        app.state.metrics.increment("http_requests_total", {"method": request.method, "route": route_path, "status": str(response.status_code)})
        app.state.metrics.observe("http_request_duration_seconds", time.perf_counter() - started, {"method": request.method, "route": route_path})
        return response

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return _error_response(DomainError("REQUEST_INVALID", "Проверьте дату, время и выбранный город", status_code=400), _trace_id(request))

    def session(request: Request, response: Response | None = None, create: bool = False) -> str:
        token = request.cookies.get(SESSION_COOKIE)
        session_id = app.state.store.session_for_token(token)
        if session_id:
            return session_id
        if not create:
            raise DomainError("AUTH_REQUIRED", "Откройте карту по своей ссылке", status_code=401)
        session_id, token = app.state.store.create_session()
        if response is not None:
            response.set_cookie(
                SESSION_COOKIE,
                token,
                httponly=True,
                secure=os.environ.get("VEDICWAY_ENV") == "production",
                samesite="lax",
                max_age=60 * 60 * 24 * 30,
                path="/",
            )
        return session_id

    def assert_owned(chart_id: str, session_id: str) -> None:
        if not app.state.store.chart_owned_by(chart_id, session_id):
            raise DomainError("CHART_NOT_FOUND", "Карта не найдена", recoverable=False, status_code=404)

    def public_purchase(purchase: dict[str, Any]) -> PurchaseResponse:
        status_value = str(purchase["status"])
        return PurchaseResponse(
            purchase_id=str(purchase["id"]),
            chart_id=str(purchase["chart_id"]),
            product_code="full_report_v1",
            status=status_value,
            checkout_url=purchase.get("checkout_url"),
            price_minor=int(purchase["amount_minor"]),
            currency=str(purchase["currency"]),
            retryable=status_value in {"created", "pending", "unknown"},
        )

    def validate_provider_intent(purchase: dict[str, Any], intent: Any) -> None:
        expected_payment_id = purchase.get("provider_payment_id")
        if expected_payment_id and intent.provider_payment_id != expected_payment_id:
            raise DomainError(
                "PAYMENT_MISMATCH",
                "Платёжный сервис вернул другую операцию",
                recoverable=False,
                status_code=409,
            )
        if intent.amount_minor != int(purchase["amount_minor"]):
            raise DomainError(
                "PAYMENT_MISMATCH",
                "Сумма платежа не совпадает с суммой заказа",
                recoverable=False,
                status_code=409,
            )
        if intent.currency.upper() != str(purchase["currency"]).upper():
            raise DomainError(
                "PAYMENT_MISMATCH",
                "Валюта платежа не совпадает с валютой заказа",
                recoverable=False,
                status_code=409,
            )
        expected_metadata = {
            "purchase_id": str(purchase["id"]),
            "chart_id": str(purchase["chart_id"]),
            "product_code": str(purchase["product_code"]),
        }
        for key, expected in expected_metadata.items():
            actual = intent.metadata.get(key)
            if actual is not None and actual != expected:
                raise DomainError(
                    "PAYMENT_MISMATCH",
                    f"Поле metadata.{key} не совпадает с заказом",
                    recoverable=False,
                    status_code=409,
                )
        if intent.status == PaymentStatus.SUCCEEDED and (not intent.paid or not intent.captured):
            raise DomainError(
                "PAYMENT_MISMATCH",
                "Платёж не подтверждён как оплаченный и захваченный",
                recoverable=False,
                status_code=409,
            )

    async def apply_verified_payment(
        purchase: dict[str, Any],
        intent: Any,
        *,
        provider_event_id: str,
        event_type: str,
        payload_checksum: str,
        trace_id: str,
        incident_category: str,
    ) -> dict[str, Any]:
        try:
            validate_provider_intent(purchase, intent)
            transition = app.state.store.apply_payment_event(
                str(purchase["id"]),
                provider_event_id=provider_event_id,
                event_type=event_type,
                object_id=str(intent.provider_payment_id),
                payload_checksum=payload_checksum,
                status=intent.status.value,
                provider_status=intent.status.value,
                provider_payment_id=str(intent.provider_payment_id),
                amount_minor=intent.amount_minor,
                currency=intent.currency,
                metadata=intent.metadata,
                failure_code=intent.failure_code,
                receipt_registration=str(intent.redacted_payload.get("receipt_registration") or "") or None,
            )
        except DomainError as error:
            if error.code == "PAYMENT_MISMATCH":
                app.state.store.record_payment_incident(
                    str(purchase["id"]),
                    incident_category,
                    {"code": error.code, "event_type": event_type},
                    trace_id,
                )
            raise
        if transition["entitlement_changed"]:
            await _launch_worker(app)
        return transition

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready")
    async def readiness() -> JSONResponse:
        try:
            app.state.store.events_since("health", 0)
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return JSONResponse(content={"status": "ready"})

    @app.get("/internal/metrics")
    async def metrics(request: Request) -> PlainTextResponse:
        token = os.environ.get("VEDICWAY_METRICS_TOKEN")
        if not token or not hmac.compare_digest(request.headers.get("X-Internal-Token", ""), token):
            raise DomainError("METRICS_FORBIDDEN", "Метрики недоступны", recoverable=False, status_code=404)
        return PlainTextResponse(app.state.metrics.render_prometheus(), media_type="text/plain; version=0.0.4")

    @app.get("/api/v1/places/search")
    async def search_places(q: str = Query(min_length=2, max_length=160)) -> dict[str, Any]:
        return {"items": [place.model_dump(mode="json") for place in app.state.places.search(q)]}

    @app.post("/api/v1/charts", status_code=status.HTTP_202_ACCEPTED, response_model=ChartAccepted)
    async def create_chart(
        request: Request,
        payload: ChartCreateRequest,
        response: Response,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ChartAccepted:
        if not idempotency_key or len(idempotency_key) > 200:
            raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Добавьте ключ защиты от повтора запроса", status_code=400)
        if os.environ.get("VEDICWAY_ENV", "development").casefold() == "production":
            rate_key = request.client.host if request.client else "unknown"
            await app.state.limiter.check(f"chart-hour:{rate_key}", limit=5, window_seconds=60 * 60)
            await app.state.limiter.check(f"chart-day:{rate_key}", limit=20, window_seconds=60 * 60 * 24)
        current_session = session(request, response, create=True)
        place = app.state.places.get(payload.place_id)
        if place is None and payload.place is not None:
            if payload.place.place_id != payload.place_id:
                raise DomainError("PLACE_MISMATCH", "Данные выбранного города устарели. Выберите город ещё раз.", status_code=422)
            place = payload.place
        if not place:
            raise DomainError("PLACE_NOT_FOUND", "Выберите город из подсказок", status_code=422)
        birth = resolve_birth_input(payload, place)
        chart_id, created = app.state.store.create_chart(current_session, birth, idempotency_key)
        if created:
            await _launch_worker(app)
        resource = app.state.store.get_chart_resource(chart_id)
        return ChartAccepted(
            chart_id=chart_id,
            status_url=f"/api/v1/charts/{chart_id}",
            events_url=f"/api/v1/charts/{chart_id}/events",
            accepted_birth=resource["birth"],
            statuses=resource["sections"],
        )

    @app.get("/api/v1/charts/{chart_id}")
    async def get_chart(chart_id: str, request: Request) -> dict[str, Any]:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        return app.state.store.get_chart_resource(chart_id, include_paid=True)

    @app.get("/api/v1/charts/{chart_id}/sections/{section}")
    async def get_section(chart_id: str, section: str, request: Request) -> Response:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        if section not in ALLOWED_SECTIONS:
            raise DomainError("SECTION_NOT_FOUND", "Такой раздел недоступен", recoverable=False, status_code=404)
        value = app.state.store.get_section(chart_id, section, include_paid=True)
        if value is None:
            return JSONResponse(status_code=202, content={"section": section, "status": "queued"})
        etag = f'"{hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return JSONResponse(content=value, headers={"ETag": etag})

    @app.get("/api/v1/charts/{chart_id}/vargas/{varga}")
    async def get_varga(chart_id: str, varga: str, request: Request) -> Response:
        from .schemas import validate_varga

        current_session = session(request)
        assert_owned(chart_id, current_session)
        try:
            key = validate_varga(varga.upper())
        except ValueError as exc:
            raise DomainError("VARGA_NOT_ALLOWED", "Эта дробная карта недоступна", recoverable=False, status_code=404) from exc
        snapshot = app.state.store.get_snapshot(chart_id)
        if snapshot is None:
            return JSONResponse(status_code=202, content={"section": key, "status": "queued"})
        section = snapshot.sections.get("d1" if key == "D1" else key)
        if section is None and key not in {"D1", "D2", "D4", "D9", "D10", "D12", "D24"}:
            if os.environ.get("VEDICWAY_EXPERT_MODE") != "1":
                return JSONResponse(status_code=202, content={"section": key, "status": "queued", "requires": "expert_extended_v1"})
            app.state.store.enqueue_job(chart_id, "expert_extended_v1", priority=20)
            await _launch_worker(app)
            return JSONResponse(status_code=202, content={"section": key, "status": "queued"})
        if section is None:
            return JSONResponse(status_code=202, content={"section": key, "status": "queued"})
        return JSONResponse(content=section)

    @app.get("/api/v1/charts/{chart_id}/events")
    async def chart_events(chart_id: str, request: Request) -> StreamingResponse:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        try:
            last_id = max(0, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            last_id = 0

        async def stream() -> AsyncIterator[str]:
            nonlocal last_id
            while True:
                if await request.is_disconnected():
                    return
                events = await asyncio.to_thread(app.state.store.events_since, chart_id, last_id)
                for item in events:
                    last_id = item.id
                    yield _sse_frame(event=item.event, data=item.data, event_id=item.id, retry=3000)
                if not events:
                    yield _sse_frame(comment="keepalive")
                await asyncio.sleep(15)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v1/charts/{chart_id}/jobs/{job_type}/retry", status_code=status.HTTP_202_ACCEPTED)
    async def retry_job(chart_id: str, job_type: str, request: Request) -> dict[str, str]:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        if job_type not in ALLOWED_JOB_TYPES:
            raise DomainError("JOB_NOT_FOUND", "Такую задачу нельзя повторить", recoverable=False, status_code=404)
        await app.state.limiter.check(f"retry:{request.client.host if request.client else 'unknown'}", limit=2, window_seconds=60 * 60)
        job_id = app.state.store.retry_job(chart_id, job_type)
        if not job_id:
            raise DomainError("JOB_NOT_RETRYABLE", "Эта задача сейчас не требует повтора", status_code=409)
        await _launch_worker(app)
        return {"job_id": job_id, "status": "queued"}

    @app.post("/api/v1/charts/{chart_id}/purchases", response_model=PurchaseResponse, status_code=status.HTTP_202_ACCEPTED)
    async def create_purchase(
        chart_id: str,
        request: Request,
        payload: PurchaseRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> PurchaseResponse:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        if not idempotency_key:
            raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Добавьте ключ защиты от повтора оплаты", status_code=400)
        if len(idempotency_key) > 200:
            raise DomainError("IDEMPOTENCY_KEY_INVALID", "Ключ защиты от повтора оплаты слишком длинный", status_code=400)
        await app.state.limiter.check(f"purchase:{request.client.host if request.client else 'unknown'}", limit=5, window_seconds=60 * 60)
        if app.state.store.get_snapshot(chart_id) is None:
            raise DomainError("SNAPSHOT_MISSING", "Сначала дождитесь основной карты", status_code=409)
        if app.state.store.has_entitlement(chart_id):
            raise DomainError(
                "ALREADY_ENTITLED",
                "Полный отчёт для этой карты уже доступен",
                recoverable=False,
                status_code=409,
            )
        settings: PaymentSettings = app.state.payment_settings
        if payload.offer_version != settings.offer_version:
            raise DomainError(
                "OFFER_VERSION_MISMATCH",
                "Условия оферты обновились. Откройте их и подтвердите ещё раз",
                status_code=409,
                detail={"offer_version": settings.offer_version},
            )
        provider: PaymentProvider = app.state.payment_provider
        if provider.name == "disabled":
            raise DomainError("PAYMENT_PROVIDER_UNAVAILABLE", "Приём платежей временно недоступен", recoverable=True, status_code=503)
        product = settings.catalog.get(payload.product_code)
        purchase, _ = app.state.store.create_purchase(
            chart_id,
            idempotency_key,
            payload.email,
            product_code=product.code,
            provider=provider.name,
            offer_version=settings.offer_version,
            amount_minor=product.amount_minor,
            currency=product.currency,
        )
        if purchase.get("provider_payment_id") or purchase["status"] not in {"created", "unknown"}:
            return public_purchase(purchase)

        return_url = (
            f"{settings.public_base_url}/payment/return?purchase_id="
            f"{quote(str(purchase['id']), safe='')}"
        )
        try:
            intent = await provider.create_payment(
                purchase_id=str(purchase["id"]),
                chart_id=chart_id,
                product_code=product.code,
                idempotency_key=str(purchase["provider_idempotency_key"]),
                amount_minor=int(purchase["amount_minor"]),
                currency=str(purchase["currency"]),
                return_url=return_url,
                email=app.state.store.get_purchase_email(str(purchase["id"])) or payload.email,
            )
            if intent.amount_minor != int(purchase["amount_minor"]) or intent.currency.upper() != str(purchase["currency"]).upper():
                raise DomainError(
                    "PAYMENT_PROVIDER_MISMATCH",
                    "Платёжный сервис вернул другую сумму или валюту",
                    recoverable=False,
                    status_code=502,
                )
            expected_metadata = {
                "purchase_id": str(purchase["id"]),
                "chart_id": chart_id,
                "product_code": product.code,
            }
            for key, expected in expected_metadata.items():
                actual = intent.metadata.get(key)
                if actual is not None and actual != expected:
                    raise DomainError(
                        "PAYMENT_PROVIDER_MISMATCH",
                        "Платёжный сервис вернул заказ с другими параметрами",
                        recoverable=False,
                        status_code=502,
                    )
            if intent.checkout_url:
                parsed_checkout = urlsplit(intent.checkout_url)
                if provider.name == "yookassa" and parsed_checkout.scheme != "https":
                    raise DomainError(
                        "PAYMENT_PROVIDER_INVALID_RESPONSE",
                        "Платёжный сервис вернул небезопасный адрес оплаты",
                        status_code=502,
                    )
            if intent.status == PaymentStatus.SUCCEEDED and (not intent.paid or not intent.captured):
                raise DomainError(
                    "PAYMENT_PROVIDER_MISMATCH",
                    "Платёж отмечен завершённым без подтверждения списания",
                    recoverable=False,
                    status_code=502,
                )
            app.state.store.set_provider_payment(
                str(purchase["id"]),
                intent.provider,
                intent.provider_payment_id,
                status=intent.status.value,
                checkout_url=intent.checkout_url,
                provider_status=intent.status.value,
                redacted_payload=intent.redacted_payload,
                failure_code=intent.failure_code,
                receipt_registration=str(intent.redacted_payload.get("receipt_registration") or "") or None,
            )
            if intent.status == PaymentStatus.SUCCEEDED:
                app.state.store.apply_payment_event(
                    str(purchase["id"]),
                    provider_event_id=f"create:succeeded:{intent.provider_payment_id}",
                    event_type="payment.succeeded",
                    object_id=str(intent.provider_payment_id),
                    payload_checksum=hashlib.sha256(json.dumps(intent.redacted_payload, sort_keys=True).encode()).hexdigest(),
                    status="succeeded",
                    provider_status="succeeded",
                    provider_payment_id=str(intent.provider_payment_id),
                    amount_minor=intent.amount_minor,
                    currency=intent.currency,
                    metadata=intent.metadata,
                )
                await _launch_worker(app)
        except DomainError as error:
            recoverable = error.recoverable or error.code == "PAYMENT_PROVIDER_TEMPORARY"
            app.state.store.set_provider_payment(
                str(purchase["id"]),
                provider.name,
                None,
                status="unknown" if recoverable else "failed",
                provider_status="unknown" if recoverable else "failed",
                failure_code=error.code,
            )
            if not recoverable:
                raise
        saved = app.state.store.get_purchase(str(purchase["id"]))
        if not saved:
            raise DomainError("PURCHASE_NOT_FOUND", "Платёж не найден", recoverable=False, status_code=404)
        return public_purchase(saved)

    @app.get("/api/v1/purchases/{purchase_id}")
    async def get_purchase(purchase_id: str, request: Request) -> PurchaseResponse:
        current_session = session(request)
        purchase = app.state.store.get_purchase(purchase_id)
        if not purchase:
            raise DomainError("PURCHASE_NOT_FOUND", "Платёж не найден", recoverable=False, status_code=404)
        assert_owned(str(purchase["chart_id"]), current_session)
        if (
            purchase["provider"] == "yookassa"
            and purchase["status"] in {"pending", "unknown"}
            and purchase.get("provider_payment_id")
            and app.state.store.claim_purchase_reconciliation(purchase_id)
        ):
            try:
                intent = await app.state.payment_provider.get_payment(str(purchase["provider_payment_id"]))
                if intent.status in {PaymentStatus.SUCCEEDED, PaymentStatus.CANCELLED}:
                    await apply_verified_payment(
                        purchase,
                        intent,
                        provider_event_id=f"reconcile:{intent.status.value}:{intent.provider_payment_id}",
                        event_type=f"payment.{intent.status.value}",
                        payload_checksum=hashlib.sha256(
                            json.dumps(intent.redacted_payload, sort_keys=True, separators=(",", ":")).encode()
                        ).hexdigest(),
                        trace_id=_trace_id(request),
                        incident_category="reconciliation_mismatch",
                    )
                else:
                    validate_provider_intent(purchase, intent)
                    app.state.store.set_provider_payment(
                        purchase_id,
                        intent.provider,
                        intent.provider_payment_id,
                        status=intent.status.value,
                        provider_status=intent.status.value,
                        redacted_payload=intent.redacted_payload,
                        failure_code=intent.failure_code,
                    )
            except DomainError as error:
                if error.code == "PAYMENT_MISMATCH":
                    app.state.store.record_payment_incident(
                        purchase_id,
                        "reconciliation_mismatch",
                        {"code": error.code},
                        _trace_id(request),
                    )
                    app.state.store.set_provider_payment(
                        purchase_id,
                        "yookassa",
                        str(purchase["provider_payment_id"]),
                        status="unknown",
                        provider_status="unknown",
                        failure_code=error.code,
                    )
                elif error.code != "PAYMENT_PROVIDER_TEMPORARY":
                    raise
            purchase = app.state.store.get_purchase(purchase_id) or purchase
        return public_purchase(purchase)

    @app.post("/api/v1/test/purchases/{purchase_id}/confirm", status_code=status.HTTP_202_ACCEPTED)
    async def confirm_test_purchase(purchase_id: str, request: Request) -> dict[str, str]:
        if os.environ.get("VEDICWAY_TEST_PAYMENTS") != "1":
            raise DomainError("TEST_ENDPOINT_DISABLED", "Тестовый контур оплаты выключен", recoverable=False, status_code=404)
        current_session = session(request)
        purchase = app.state.store.get_purchase(purchase_id)
        if not purchase:
            raise DomainError("PURCHASE_NOT_FOUND", "Платёж не найден", recoverable=False, status_code=404)
        assert_owned(str(purchase["chart_id"]), current_session)
        chart_id = app.state.store.confirm_purchase(purchase_id, f"test_{purchase_id}")
        if not chart_id:
            raise DomainError("PURCHASE_NOT_FOUND", "Платёж не найден", recoverable=False, status_code=404)
        await _launch_worker(app)
        return {"purchase_id": purchase_id, "status": "succeeded"}

    @app.post("/api/v1/webhooks/payments/{provider}", status_code=status.HTTP_200_OK)
    async def payment_webhook(provider: str, request: Request) -> dict[str, str]:
        if provider != "yookassa":
            raise DomainError("WEBHOOK_PROVIDER_UNSUPPORTED", "Платёжный провайдер не поддерживается", recoverable=False, status_code=404)
        peer_ip = request.client.host if request.client else ""
        source_ip = effective_client_ip(
            peer_ip,
            request.headers.get("X-Forwarded-For"),
            app.state.payment_settings.trusted_proxy_networks,
        )
        if not is_yookassa_source(source_ip):
            raise DomainError(
                "WEBHOOK_SOURCE_FORBIDDEN",
                "Источник уведомления не прошёл проверку",
                recoverable=False,
                status_code=403,
            )
        raw = await request.body()
        if len(raw) > 64 * 1024:
            raise DomainError("WEBHOOK_INVALID", "Уведомление превышает допустимый размер", recoverable=False, status_code=413)
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get("type") != "notification":
                raise ValueError
            event_type = payload["event"]
            payment_object = payload["object"]
            if not isinstance(event_type, str) or not isinstance(payment_object, dict):
                raise ValueError
            provider_payment_id = payment_object["id"]
            if not isinstance(provider_payment_id, str) or not provider_payment_id:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DomainError("WEBHOOK_INVALID", "Событие платежа имеет неверный формат", recoverable=False, status_code=400) from exc
        if event_type not in {"payment.succeeded", "payment.canceled"}:
            return {"status": "ignored"}

        provider_event_id = f"{event_type}:{provider_payment_id}"
        if app.state.store.payment_event_exists("yookassa", provider_event_id):
            return {"status": "duplicate"}
        purchase = app.state.store.get_purchase_by_provider_payment_id("yookassa", provider_payment_id)
        if not purchase:
            raise DomainError("PURCHASE_NOT_FOUND", "Платёж не найден", recoverable=False, status_code=404)
        intent = await app.state.payment_provider.get_payment(provider_payment_id)
        expected_status = PaymentStatus.SUCCEEDED if event_type == "payment.succeeded" else PaymentStatus.CANCELLED
        if intent.status != expected_status:
            app.state.store.record_payment_incident(
                str(purchase["id"]),
                "webhook_mismatch",
                {"event_type": event_type, "provider_status": intent.status.value},
                _trace_id(request),
            )
            raise DomainError(
                "PAYMENT_MISMATCH",
                "Статус платежа не совпадает с уведомлением",
                recoverable=False,
                status_code=409,
            )
        await apply_verified_payment(
            purchase,
            intent,
            provider_event_id=provider_event_id,
            event_type=event_type,
            payload_checksum=hashlib.sha256(raw).hexdigest(),
            trace_id=_trace_id(request),
            incident_category="webhook_mismatch",
        )
        return {"status": "accepted"}

    @app.get("/api/v1/charts/{chart_id}/entitlements")
    async def entitlements(chart_id: str, request: Request) -> dict[str, Any]:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        return {"report_full": app.state.store.has_entitlement(chart_id)}

    @app.put("/api/v1/charts/{chart_id}/questions/{question_id}")
    async def save_question(
        chart_id: str,
        question_id: str,
        request: Request,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        saved = bool(payload.get("saved", False))
        note = payload.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 4000):
            raise DomainError("NOTE_INVALID", "Заметка слишком длинная", status_code=400)
        reflection_status = payload.get("reflection_status", "saved")
        if reflection_status not in {"saved", "thinking", "return_later"}:
            raise DomainError("QUESTION_STATUS_INVALID", "Выберите допустимый статус вопроса", status_code=400)
        app.state.store.save_question(chart_id, question_id, saved, note, reflection_status)
        return {"question_id": question_id, "saved": saved, "reflection_status": reflection_status, "note": note}

    @app.get("/api/v1/charts/{chart_id}/questions/saved")
    async def saved_questions(chart_id: str, request: Request) -> dict[str, Any]:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        return {"items": app.state.store.saved_questions(chart_id)}

    @app.post("/api/v1/charts/{chart_id}/reports/pdf", status_code=status.HTTP_202_ACCEPTED)
    async def create_pdf(chart_id: str, request: Request) -> dict[str, Any]:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        if not app.state.store.has_entitlement(chart_id):
            raise DomainError("ENTITLEMENT_REQUIRED", "PDF входит в полный отчёт", recoverable=False, status_code=403)
        job_id = app.state.store.enqueue_job(chart_id, "pdf_v1", priority=60)
        await _launch_worker(app)
        return {"job_id": job_id, "status": app.state.store.get_report(chart_id)["status"]}

    @app.get("/api/v1/charts/{chart_id}/reports/pdf")
    async def get_pdf(chart_id: str, request: Request) -> Response:
        current_session = session(request)
        assert_owned(chart_id, current_session)
        report = app.state.store.get_report(chart_id)
        if report["status"] == "ready":
            token = app.state.store.issue_download_token(chart_id)
            return RedirectResponse(url=f"/api/v1/reports/download/{chart_id}?token={token}", status_code=303)
        return JSONResponse(status_code=202, content=report)

    @app.get("/api/v1/reports/download/{chart_id}")
    async def download_pdf(chart_id: str, token: str = Query(...)) -> FileResponse:
        if not app.state.store.validate_download_token(token, chart_id):
            raise DomainError("DOWNLOAD_TOKEN_INVALID", "Ссылка на файл устарела", recoverable=False, status_code=401)
        report = app.state.store.get_report(chart_id)
        if report["status"] != "ready":
            raise DomainError("PDF_NOT_READY", "PDF ещё готовится", status_code=409)
        path = app.state.store.report_file_path(chart_id)
        if path is None or not path.exists():
            raise DomainError("PDF_MISSING", "Файл отчёта не найден", recoverable=True, status_code=404)
        return FileResponse(path, media_type="application/pdf", filename="vedicway-report.pdf")

    @app.get("/api/v1/magic-links/{token}")
    async def redeem_magic_link(token: str) -> RedirectResponse:
        chart_id = app.state.store.redeem_magic_link(token)
        if not chart_id:
            raise DomainError("MAGIC_LINK_INVALID", "Ссылка для возврата устарела", recoverable=False, status_code=401)
        session_id, raw_token = app.state.store.create_session()
        app.state.store.grant_chart_access(chart_id, session_id)
        response = RedirectResponse(url=f"/chart/{chart_id}", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            raw_token,
            httponly=True,
            secure=os.environ.get("VEDICWAY_ENV") == "production",
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
            path="/",
        )
        return response

    return app


app = create_app()

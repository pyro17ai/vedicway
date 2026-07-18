from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import DOMAIN_ORDER, VARGA_ALLOWLIST, DomainSlug


class TimeAccuracy(StrEnum):
    EXACT = "exact"
    APPROXIMATE_15M = "approximate_15m"
    APPROXIMATE_HOUR = "approximate_hour"
    UNKNOWN = "unknown"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    VALIDATING = "validating"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    CANCELLED = "cancelled"


class SectionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    PARTIAL = "partial"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class Coverage(StrEnum):
    MULTIPLE_FACTORS = "multiple_factors"
    SINGLE_FACTOR = "single_factor"
    INSUFFICIENT = "insufficient"


class AccessLevel(StrEnum):
    FREE_SUMMARY = "free_summary"
    PAID_FULL = "paid_full"


class Place(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place_id: str
    display_name: str
    country_code: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    tzid: str


class ResolvedTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utc_offset_seconds: int
    utc_datetime: datetime
    resolution_source: str
    fold: int = Field(default=0, ge=0, le=1)


class BirthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["birth-input.v1"] = "birth-input.v1"
    local_datetime: datetime
    place: Place
    resolved_time: ResolvedTime
    ayanamsa: Literal["LAHIRI"] = "LAHIRI"
    time_accuracy: TimeAccuracy


class ChartCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_date: date
    local_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")
    place_id: str = Field(min_length=2, max_length=160)
    place: Place | None = None
    time_accuracy: TimeAccuracy = TimeAccuracy.EXACT
    fold: int | None = Field(default=None, ge=0, le=1)

    @field_validator("local_date")
    @classmethod
    def birth_date_must_not_be_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Дата рождения не может быть в будущем")
        return value


class ChartAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_id: str
    status_url: str
    events_url: str
    accepted_birth: dict[str, Any]
    statuses: dict[str, str]


class PlanetPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planet_code: str
    label: str
    short_label: str
    classical: bool
    sign_index: int = Field(ge=0, le=11)
    sign_label: str
    house_number: int = Field(ge=1, le=12)
    longitude_in_sign: float = Field(ge=0, lt=30)
    total_longitude: float = Field(ge=0, lt=360)
    nakshatra: str
    pada: int | None = Field(default=None, ge=1, le=4)
    retrograde: bool | None = None
    source_path: str


class ChartCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sign_index: int = Field(ge=0, le=11)
    sign_code: str
    sign_label: str
    house_number: int = Field(ge=1, le=12)
    is_lagna: bool
    planets: list[PlanetPosition]


class EventTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_date: date
    local_time: str
    day_offset: int
    iso_datetime: datetime
    raw_hours: float | None = None


class ChartSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["chart-snapshot.v1"] = "chart-snapshot.v1"
    snapshot_id: str
    chart_id: str
    revision: int
    engine: dict[str, str]
    method: dict[str, str]
    birth: dict[str, Any]
    cells: list[ChartCell]
    sections: dict[str, dict[str, Any]]
    created_at: datetime
    checksum: str


class EvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    subject: str
    chart: str
    sign: str | None = None
    house: int | None = None
    value: dict[str, Any] = Field(default_factory=dict)
    human_label_ru: str
    domains: list[DomainSlug]
    source_paths: list[str]
    rule_version: str = "evidence.v1"


class DomainEvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: DomainSlug
    primary_facts: list[str]
    confirming_facts: list[str]
    contradictions: list[str] = Field(default_factory=list)
    coverage: Coverage
    allowed_claim_scope: str
    missing_sections: list[str] = Field(default_factory=list)


class DomainInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: DomainSlug
    section_label: str
    title: str
    summary: str = Field(min_length=30, max_length=700)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)
    coverage: Coverage
    limitations: list[str] = Field(default_factory=list)
    paragraphs: list[str] = Field(default_factory=list, max_length=7)
    manifestations: list[str] = Field(default_factory=list)
    reflection_prompts: list[str] = Field(default_factory=list, max_length=2)


class ReflectionQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    domain: DomainSlug
    text: str = Field(min_length=18, max_length=320)
    rationale: str = Field(min_length=18, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=2)


class InterpretationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["interpretation.free.v1", "interpretation.paid.v1"]
    snapshot_id: str
    locale: Literal["ru-RU"] = "ru-RU"
    overview: DomainInterpretation
    domains: list[DomainInterpretation] = Field(min_length=8, max_length=8)
    questions: list[ReflectionQuestion]
    global_limitations: list[str] = Field(default_factory=list)
    synthesis: list[str] = Field(default_factory=list)

    @field_validator("domains")
    @classmethod
    def domain_order_must_be_canonical(cls, domains: list[DomainInterpretation]) -> list[DomainInterpretation]:
        if [domain.slug for domain in domains] != DOMAIN_ORDER:
            raise ValueError("Разделы отчёта должны идти в фиксированном порядке")
        return domains


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_code: Literal["full_report_v1"] = "full_report_v1"
    email: str | None = Field(default=None, max_length=320)


class PurchaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_id: str
    status: str
    checkout_url: str | None = None
    provider: str
    price_minor: int
    currency: str


class PdfStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["locked", "generating", "ready", "failed"]
    pages: int | None = None
    size_bytes: int | None = None
    download_url: str | None = None
    error_code: str | None = None


class ChartEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    event: str
    data: dict[str, Any]
    created_at: datetime


def section_model(section: str, status: SectionStatus, data: Any | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "section": section,
        "status": status.value,
        "data": data,
        "error": error,
    }


def validate_varga(varga: str) -> str:
    if varga not in VARGA_ALLOWLIST:
        raise ValueError("Недоступная дробная карта")
    return varga

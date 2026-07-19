from __future__ import annotations

import difflib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .constants import DOMAIN_LABELS_RU, DOMAIN_ORDER, DomainSlug
from .errors import DomainError
from .interpretation_prompt import (
    GLOBAL_LIMITATIONS,
    MODEL_CONFIG_VERSION,
    PROMPT_VERSION,
    build_interpretation_prompt,
    codex_output_schema,
)
from .schemas import (
    Coverage,
    DomainEvidencePacket,
    DomainInterpretation,
    EvidenceFact,
    InterpretationBundle,
    ReflectionQuestion,
)

LOGGER = logging.getLogger("vedicway.interpretation")

FORBIDDEN_PUBLIC_TERMS = (
    "codex",
    "pyjhora",
    "mcp",
    "prompt",
    "промпт",
    "json",
    "языковая модель",
    "модель сгенерировала",
    "внутренний агент",
)

FORBIDDEN_CLAIM_TERMS = (
    "вам суждено",
    "вам сужден",
    "судьбой предписано",
    "неизбежно произойд",
    "неизбежно случ",
    "неизбежный исход",
    "точно произойд",
    "обязательно случ",
    "гарантированно получите",
    "гарантирует вам",
    "гарантированный доход",
    "гарантированный результат",
    "вы никогда не сможете",
    "никогда не получится",
    "вы должны",
    "вам следует",
    "у вас диагноз",
    "вам поставлен диагноз",
    "совершите ритуал",
    "умрёте",
    "ваша смерть",
)

SECTION_TITLES = {
    DomainSlug.CHARACTER: "Воля, которая раскрывается через ясные границы",
    DomainSlug.INNER_SUPPORT: "Чувствительность как способ вернуть устойчивость",
    DomainSlug.RELATIONSHIPS: "Близость с сохранением собственного пространства",
    DomainSlug.FAMILY_HOME: "Свой ритм дома и потребность в надёжной опоре",
    DomainSlug.WORK: "Ответственность, которой нужен понятный результат",
    DomainSlug.MONEY: "Материальная опора через последовательные решения",
    DomainSlug.LEARNING: "Знание, которое закрепляется через практику",
    DomainSlug.CURRENT_PERIOD: "Тема периода как направление внимания",
}

DOMAIN_OBSERVATIONS = {
    DomainSlug.CHARACTER: "Такой рисунок полезно проверять по тому, как вы входите в новое дело и защищаете свою зону решения.",
    DomainSlug.INNER_SUPPORT: "Он заметнее всего в способах восстанавливаться после перегрузки и возвращать себе внутреннюю собранность.",
    DomainSlug.RELATIONSHIPS: "Связку стоит наблюдать в момент сближения, когда одновременно важны контакт и право оставаться собой.",
    DomainSlug.FAMILY_HOME: "Она проявляется в выборе домашнего ритма, степени близости и правил, которые создают ощущение своего места.",
    DomainSlug.WORK: "Её легче заметить в задачах, где нужно соотнести личную ответственность, темп и видимый результат.",
    DomainSlug.MONEY: "Она раскрывается в повседневных решениях о запасе, риске и способе создавать материальную устойчивость.",
    DomainSlug.LEARNING: "Такой рисунок виден по тому, что удерживает любопытство после первого интереса и превращает знание в навык.",
    DomainSlug.CURRENT_PERIOD: "Период задаёт фон внимания, который следует сверять с реальными обстоятельствами без прогноза точного события.",
}

QUESTION_STEMS = {
    DomainSlug.CHARACTER: "В каких ситуациях я начинаю действовать увереннее, когда заранее понимаю свои границы?",
    DomainSlug.INNER_SUPPORT: "Что действительно возвращает мне устойчивость после эмоционально насыщенного дня?",
    DomainSlug.RELATIONSHIPS: "Как я могу сохранять близость и одновременно не отказываться от собственного пространства?",
    DomainSlug.FAMILY_HOME: "Какие правила и ритм дома дают мне чувство опоры, а какие начинают стеснять?",
    DomainSlug.WORK: "В каких рабочих задачах ответственность помогает мне собраться, а в каких становится лишней нагрузкой?",
    DomainSlug.MONEY: "Какие решения о деньгах укрепляют моё чувство опоры без стремления контролировать всё заранее?",
    DomainSlug.LEARNING: "Какой способ учиться помогает мне сохранить интерес после первого всплеска любопытства?",
    DomainSlug.CURRENT_PERIOD: "Какая тема текущего периода чаще возвращает моё внимание в реальных событиях последних недель?",
}

REQUIRED_DOMAIN_CHART = {
    DomainSlug.CHARACTER: "D1",
    DomainSlug.INNER_SUPPORT: "D1",
    DomainSlug.RELATIONSHIPS: "D9",
    DomainSlug.FAMILY_HOME: "D4",
    DomainSlug.WORK: "D10",
    DomainSlug.MONEY: "D2",
    DomainSlug.LEARNING: "D24",
}

_MODEL_SLUG = re.compile(r"^[A-Za-z0-9._-]+$")
_CONFIG_TOKEN = re.compile(r"^[a-z0-9_-]+$")


def _facts_by_id(facts: list[EvidenceFact]) -> dict[str, EvidenceFact]:
    return {fact.id: fact for fact in facts}


def _packet_by_slug(packets: list[DomainEvidencePacket]) -> dict[DomainSlug, DomainEvidencePacket]:
    return {packet.slug: packet for packet in packets}


def _normalized_text(value: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", " ", value.casefold()).strip()


def _too_similar(left: str, right: str, threshold: float = 0.88) -> bool:
    return difflib.SequenceMatcher(None, _normalized_text(left), _normalized_text(right)).ratio() >= threshold


def _overview_coverage(packets: list[DomainEvidencePacket]) -> Coverage:
    fact_ids = {
        fact_id
        for packet in packets
        for fact_id in packet.primary_facts + packet.confirming_facts
    }
    if len(fact_ids) >= 2:
        return Coverage.MULTIPLE_FACTORS
    if fact_ids:
        return Coverage.SINGLE_FACTOR
    return Coverage.INSUFFICIENT


def _summary(slug: DomainSlug, evidence: list[EvidenceFact], coverage: Coverage) -> str:
    labels = "; ".join(fact.human_label_ru for fact in evidence[:2])
    if coverage == Coverage.INSUFFICIENT:
        return (
            "Для этой темы пока не хватает готового подтверждающего расчёта, поэтому подробный личный вывод был бы неточным. "
            "Раздел сохранит своё место и заполнится после повторной обработки нужной дробной карты. До этого момента здесь "
            "лучше не подменять данные общим описанием характера."
        )
    factor_note = (
        "Два рассчитанных ориентира складываются в один наблюдаемый рисунок"
        if coverage == Coverage.MULTIPLE_FACTORS
        else "В расчёте пока виден один основной ориентир"
    )
    return (
        f"{factor_note}: {labels}. {DOMAIN_OBSERVATIONS[slug]} "
        "Эта формулировка описывает склонность, которую имеет смысл сопоставлять со своим опытом и обстоятельствами, "
        "а не готовый сценарий будущего."
    )


class InterpretationProvider(ABC):
    prompt_version = "interpretation-provider.v1"

    @abstractmethod
    def generate(
        self,
        snapshot_id: str,
        facts: list[EvidenceFact],
        packets: list[DomainEvidencePacket],
        paid: bool,
    ) -> InterpretationBundle:
        raise NotImplementedError


class DevelopmentInterpretationProvider(InterpretationProvider):
    """Explicit contract stub for tests. It must never masquerade as personal output."""

    prompt_version = "interpretation-contract-stub.v2"

    def generate(
        self,
        snapshot_id: str,
        facts: list[EvidenceFact],
        packets: list[DomainEvidencePacket],
        paid: bool,
    ) -> InterpretationBundle:
        by_id = _facts_by_id(facts)
        domains: list[DomainInterpretation] = []
        for packet in packets:
            evidence_ids = packet.primary_facts + packet.confirming_facts
            evidence = [by_id[item] for item in evidence_ids if item in by_id]
            limitations: list[str] = []
            if packet.coverage == Coverage.INSUFFICIENT:
                limitations.append("Подтверждающий расчётный раздел пока не готов.")
            elif packet.coverage == Coverage.SINGLE_FACTOR:
                limitations.append("Формулировка опирается на один расчётный ориентир.")
            paragraphs: list[str] = []
            manifestations: list[str] = []
            reflection_prompts: list[str] = []
            if paid and packet.coverage != Coverage.INSUFFICIENT:
                evidence_names = ", ".join(fact.human_label_ru for fact in evidence)
                paragraphs = [
                    f"Центральный рисунок темы «{DOMAIN_LABELS_RU[packet.slug]}» возникает там, где личный способ действовать встречается с требованиями ситуации. Его полезно читать как повторяющуюся склонность, а не как закреплённую роль: человек сохраняет право выбирать форму проявления и менять привычный ответ.",
                    f"Основанием служат рассчитанные положения: {evidence_names}. Вместе они задают конкретную оптику для наблюдения за этой сферой. Каждое из них важно соотносить с другим, потому что один символ без подтверждения легко превращается в слишком широкое описание.",
                    f"Внутреннее напряжение темы «{DOMAIN_LABELS_RU[packet.slug]}» проявляется между привычным способом сохранить устойчивость и необходимостью откликнуться на новые обстоятельства. Такой разрыв не требует выбирать один полюс навсегда; он помогает увидеть момент, в котором автоматическая реакция перестаёт быть полезной.",
                    "В повседневности этот рисунок заметен через повторяющиеся решения, темп и границы ответственности. Наблюдение становится точнее, если сравнивать несколько реальных ситуаций, отмечая не только результат, но и условия, при которых появляется ясность или накапливается напряжение.",
                    f"Практический способ осмыслить раздел — вернуться к фактам после конкретного опыта и проверить, какая часть описания действительно проявилась. Вопрос «{QUESTION_STEMS[packet.slug]}» оставляет решение человеку и не превращает карту в директиву.",
                ]
                manifestations = [
                    f"Повторяющийся способ принимать решения в сфере «{DOMAIN_LABELS_RU[packet.slug]}».",
                    "Изменение внутреннего состояния при ясных или размытых границах ситуации.",
                ]
                reflection_prompts = [QUESTION_STEMS[packet.slug]]
            title = (
                "Для подробного вывода не хватает данных"
                if packet.coverage == Coverage.INSUFFICIENT
                else SECTION_TITLES[packet.slug]
            )
            domains.append(
                DomainInterpretation(
                    slug=packet.slug,
                    section_label=DOMAIN_LABELS_RU[packet.slug],
                    title=title,
                    summary=_summary(packet.slug, evidence, packet.coverage),
                    evidence_ids=evidence_ids,
                    coverage=packet.coverage,
                    limitations=limitations,
                    paragraphs=paragraphs,
                    manifestations=manifestations,
                    reflection_prompts=reflection_prompts,
                )
            )

        question_count = 12 if paid else 6
        selected_domains = list(DOMAIN_ORDER if paid else DOMAIN_ORDER[:6])
        questions: list[ReflectionQuestion] = []
        for index in range(question_count):
            slug = selected_domains[index % len(selected_domains)]
            packet = next(packet for packet in packets if packet.slug == slug)
            evidence_ids = (packet.primary_facts + packet.confirming_facts)[:2]
            if index < len(selected_domains):
                text = QUESTION_STEMS[slug]
            else:
                text = QUESTION_STEMS[slug][:-1] + ", если сравнить две похожие ситуации за последний месяц?"
            questions.append(
                ReflectionQuestion(
                    id=f"q_{index + 1:02d}",
                    domain=slug,
                    text=text,
                    rationale=(
                        "Вопрос связывает рассчитанные положения этой темы с наблюдаемым поведением и предлагает "
                        "проверить формулировку на собственном опыте без готового прогноза."
                    ),
                    evidence_ids=evidence_ids,
                )
            )

        overview_ids: list[str] = []
        for packet in packets:
            for fact_id in packet.primary_facts + packet.confirming_facts:
                if fact_id not in overview_ids:
                    overview_ids.append(fact_id)
                if len(overview_ids) == 4:
                    break
            if len(overview_ids) == 4:
                break
        overview = DomainInterpretation(
            slug=DomainSlug.CHARACTER,
            section_label="Главный рисунок",
            title="Собранность, которая опирается на чувствительность к контексту",
            summary=(
                "В карте одновременно заметны потребность действовать собранно и внимательность к меняющимся обстоятельствам. "
                "Такой рисунок может проявляться по-разному в работе, близости и восстановлении, поэтому восемь разделов ниже "
                "разводят общую тему по конкретным сферам и связывают каждую формулировку с рассчитанными положениями."
            ),
            evidence_ids=overview_ids,
            coverage=_overview_coverage(packets),
            limitations=[],
            paragraphs=[],
            manifestations=[],
            reflection_prompts=[],
        )
        return InterpretationBundle(
            schema_version="interpretation.paid.v1" if paid else "interpretation.free.v1",
            snapshot_id=snapshot_id,
            overview=overview,
            domains=domains,
            questions=questions,
            global_limitations=list(GLOBAL_LIMITATIONS),
            synthesis=(
                [
                    "Общий рисунок складывается из тем, которые повторяются в нескольких разделах и получают разное выражение в зависимости от жизненной сферы. Его полезно читать через реальные решения, сохраняя различие между рассчитанным положением и личной биографией.",
                    "Часть факторов усиливает стремление к определённости, другая оставляет больше места для чувствительности к контексту. Такое сочетание описывает рабочую развилку для наблюдения, а не противоречие, которое необходимо устранить.",
                    "В отношениях, работе и обращении с ресурсами один и тот же внутренний мотив может проявляться разными способами. Сравнение этих проявлений помогает увидеть условия, в которых привычная реакция поддерживает, и моменты, когда она становится слишком жёсткой.",
                    "Возвращение к двенадцати вопросам после конкретных событий делает чтение проверяемым личным опытом. Карта остаётся картой возможностей и языка наблюдения, а решения принимаются с учётом фактов реальной ситуации.",
                ]
                if paid
                else []
            ),
        )


class UnavailableInterpretationProvider(InterpretationProvider):
    prompt_version = PROMPT_VERSION

    def __init__(self, reason: str = "Поставщик объяснения не настроен") -> None:
        self.reason = reason

    def generate(
        self,
        snapshot_id: str,
        facts: list[EvidenceFact],
        packets: list[DomainEvidencePacket],
        paid: bool,
    ) -> InterpretationBundle:
        raise DomainError("INTERPRETATION_UNAVAILABLE", self.reason, recoverable=True, status_code=503)


def _required_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    try:
        value = float(raw) if raw is not None else default
    except ValueError as exc:
        raise DomainError("INTERPRETATION_CONFIG_INVALID", f"Некорректная настройка {name}", status_code=503) from exc
    if not minimum <= value <= maximum:
        raise DomainError("INTERPRETATION_CONFIG_INVALID", f"Настройка {name} вне допустимого диапазона", status_code=503)
    return value


def _resolve_codex_executable(configured: str | None) -> Path:
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    if os.name == "nt":
        npm_wrapper = shutil.which("codex.cmd")
        if npm_wrapper:
            npm_root = Path(npm_wrapper).resolve().parent
            native_pattern = Path(
                "node_modules/@openai/codex/node_modules/@openai/codex-win32-*/vendor/*/bin/codex.exe"
            )
            candidates.extend(str(path) for path in npm_root.glob(str(native_pattern)))
    candidates.extend(["codex.exe", "codex"] if os.name == "nt" else ["codex"])
    for candidate in candidates:
        expanded = Path(os.path.expandvars(candidate)).expanduser()
        resolved = str(expanded.resolve()) if expanded.exists() else shutil.which(candidate)
        if not resolved:
            continue
        path = Path(resolved).resolve()
        if os.name == "nt" and path.suffix.casefold() in {".cmd", ".bat", ".ps1"}:
            continue
        if path.is_file():
            return path
    raise DomainError("INTERPRETATION_CONFIG_INVALID", "Исполняемый файл Codex не найден", status_code=503)


@dataclass(frozen=True, slots=True)
class CodexExecSettings:
    codex_home: Path
    workdir: Path
    executable: Path
    free_model: str = "gpt-5.6-luna"
    paid_model: str = "gpt-5.6-terra"
    free_reasoning: str = "low"
    paid_reasoning: str = "medium"
    free_timeout_seconds: float = 35.0
    paid_timeout_seconds: float = 120.0
    service_tier: str = "fast"

    @classmethod
    def from_environment(cls) -> CodexExecSettings:
        codex_home_raw = os.environ.get("VEDICWAY_CODEX_HOME")
        workdir_raw = os.environ.get("VEDICWAY_AGENT_WORKDIR")
        if not codex_home_raw or not workdir_raw:
            raise DomainError(
                "INTERPRETATION_CONFIG_INVALID",
                "Не настроен изолированный контур объяснения",
                status_code=503,
            )
        codex_home = Path(os.path.expandvars(codex_home_raw)).expanduser().resolve()
        workdir = Path(os.path.expandvars(workdir_raw)).expanduser().resolve()
        if not codex_home.is_dir() or not workdir.is_dir():
            raise DomainError("INTERPRETATION_CONFIG_INVALID", "Каталоги контура объяснения не готовы", status_code=503)
        user_codex_home = (Path.home() / ".codex").resolve()
        if codex_home == user_codex_home and os.environ.get("VEDICWAY_ALLOW_USER_CODEX_HOME") != "1":
            raise DomainError(
                "INTERPRETATION_CONFIG_INVALID",
                "Для сервиса требуется отдельный CODEX_HOME",
                status_code=503,
            )
        if codex_home == workdir or codex_home in workdir.parents or workdir in codex_home.parents:
            raise DomainError("INTERPRETATION_CONFIG_INVALID", "Каталоги auth и sandbox должны быть разделены", status_code=503)
        if any(workdir.iterdir()):
            raise DomainError("INTERPRETATION_CONFIG_INVALID", "Рабочий каталог агента должен быть пустым", status_code=503)
        if not (codex_home / "auth.json").is_file() and not os.environ.get("OPENAI_API_KEY"):
            raise DomainError("INTERPRETATION_CONFIG_INVALID", "В отдельном CODEX_HOME нет авторизации", status_code=503)

        free_model = os.environ.get("VEDICWAY_CODEX_FREE_MODEL", "gpt-5.6-luna")
        paid_model = os.environ.get("VEDICWAY_CODEX_PAID_MODEL", "gpt-5.6-terra")
        free_reasoning = os.environ.get("VEDICWAY_CODEX_FREE_REASONING", "low")
        paid_reasoning = os.environ.get("VEDICWAY_CODEX_PAID_REASONING", "medium")
        service_tier = os.environ.get("VEDICWAY_CODEX_SERVICE_TIER", "fast").casefold()
        if not _MODEL_SLUG.fullmatch(free_model) or not _MODEL_SLUG.fullmatch(paid_model):
            raise DomainError("INTERPRETATION_CONFIG_INVALID", "Некорректное имя модели", status_code=503)
        if free_reasoning not in {"low", "medium", "high", "xhigh"} or paid_reasoning not in {"low", "medium", "high", "xhigh"}:
            raise DomainError("INTERPRETATION_CONFIG_INVALID", "Некорректный уровень рассуждения", status_code=503)
        if not _CONFIG_TOKEN.fullmatch(service_tier):
            raise DomainError("INTERPRETATION_CONFIG_INVALID", "Некорректный service tier", status_code=503)
        return cls(
            codex_home=codex_home,
            workdir=workdir,
            executable=_resolve_codex_executable(os.environ.get("VEDICWAY_CODEX_EXECUTABLE")),
            free_model=free_model,
            paid_model=paid_model,
            free_reasoning=free_reasoning,
            paid_reasoning=paid_reasoning,
            free_timeout_seconds=_required_float("VEDICWAY_CODEX_FREE_TIMEOUT_SECONDS", 35.0, 5.0, 300.0),
            paid_timeout_seconds=_required_float("VEDICWAY_CODEX_PAID_TIMEOUT_SECONDS", 120.0, 10.0, 600.0),
            service_tier=service_tier,
        )


class _BundleValidationFailure(Exception):
    def __init__(self, errors: list[str], raw_output: str) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors
        self.raw_output = raw_output


def _normalize_generated_contract(
    bundle: InterpretationBundle,
    facts: list[EvidenceFact],
) -> InterpretationBundle:
    """Fill deterministic UI fields that do not require editorial judgment."""
    normalized = bundle.model_copy(deep=True)
    valid_ids = {fact.id for fact in facts}
    overview_ids: list[str] = []
    for domain in normalized.domains:
        first_valid = next((fact_id for fact_id in domain.evidence_ids if fact_id in valid_ids), None)
        if first_valid and first_valid not in overview_ids:
            overview_ids.append(first_valid)
        if len(overview_ids) == 5:
            break
    if len(overview_ids) < 2:
        for domain in normalized.domains:
            for fact_id in domain.evidence_ids:
                if fact_id in valid_ids and fact_id not in overview_ids:
                    overview_ids.append(fact_id)
                if len(overview_ids) == 5:
                    break
            if len(overview_ids) == 5:
                break
    normalized.overview.evidence_ids = overview_ids
    normalized.global_limitations = list(GLOBAL_LIMITATIONS)
    return normalized


class CodexExecProvider(InterpretationProvider):
    """One-shot, schema-constrained process adapter for the isolated worker."""

    prompt_version = PROMPT_VERSION

    def __init__(self, settings: CodexExecSettings | None = None) -> None:
        self.settings = settings or CodexExecSettings.from_environment()

    def generate(
        self,
        snapshot_id: str,
        facts: list[EvidenceFact],
        packets: list[DomainEvidencePacket],
        paid: bool,
    ) -> InterpretationBundle:
        with tempfile.TemporaryDirectory(prefix="vedicway-agent-") as temporary:
            temp_path = Path(temporary)
            output_path = temp_path / "result.json"
            schema_path = temp_path / "interpretation-schema.json"
            schema_path.write_text(
                json.dumps(codex_output_schema(paid), ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            prompt = build_interpretation_prompt(snapshot_id, facts, packets, paid)
            for attempt in range(2):
                raw_output = self._run_once(prompt, schema_path, output_path, paid, attempt + 1)
                try:
                    return self._validate_raw(raw_output, snapshot_id, facts, packets, paid)
                except _BundleValidationFailure as exc:
                    LOGGER.warning(
                        "codex_output_validation_failed access=%s attempt=%s errors=%s",
                        "paid" if paid else "free",
                        attempt + 1,
                        " | ".join(exc.errors[:12]),
                    )
                    if attempt == 1:
                        raise DomainError(
                            "INTERPRETATION_INVALID",
                            "Структура объяснения не прошла проверку",
                            recoverable=True,
                        ) from exc
                    prompt = build_interpretation_prompt(
                        snapshot_id,
                        facts,
                        packets,
                        paid,
                        repair={
                            "instruction": "Исправь предыдущий объект по перечисленным ошибкам и верни его целиком.",
                            "validation_errors": exc.errors[:12],
                            "previous_output": exc.raw_output[:120_000],
                        },
                    )
        raise DomainError("INTERPRETATION_INVALID", "Не удалось проверить объяснение", recoverable=True)

    def _run_once(
        self,
        prompt: str,
        schema_path: Path,
        output_path: Path,
        paid: bool,
        attempt: int,
    ) -> str:
        if output_path.exists():
            output_path.unlink()
        model = self.settings.paid_model if paid else self.settings.free_model
        reasoning = self.settings.paid_reasoning if paid else self.settings.free_reasoning
        timeout = self.settings.paid_timeout_seconds if paid else self.settings.free_timeout_seconds
        command = [
            str(self.settings.executable),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "-C",
            str(self.settings.workdir),
            "-m",
            model,
            "-c",
            f'model_reasoning_effort="{reasoning}"',
            "-c",
            f'service_tier="{self.settings.service_tier}"',
            "-c",
            'web_search="disabled"',
            "-c",
            "features.apps=false",
            "-c",
            "features.multi_agent=false",
            "-c",
            "features.shell_tool=false",
        ]
        if self.settings.service_tier == "fast":
            command.extend(["-c", "features.fast_mode=true"])
        command.extend(
            [
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "--json",
                "-",
            ]
        )
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=timeout,
                shell=False,
                env=self._child_environment(),
                cwd=self.settings.workdir,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DomainError(
                "INTERPRETATION_UNAVAILABLE",
                "Подготовка объяснения заняла слишком много времени",
                recoverable=True,
                status_code=503,
            ) from exc
        except OSError as exc:
            raise DomainError(
                "INTERPRETATION_UNAVAILABLE",
                "Не удалось запустить контур объяснения",
                recoverable=True,
                status_code=503,
            ) from exc
        duration_ms = round((time.perf_counter() - started) * 1000)
        LOGGER.info(
            "codex_exec_finished model=%s access=%s attempt=%s returncode=%s duration_ms=%s events=%s config=%s",
            model,
            "paid" if paid else "free",
            attempt,
            completed.returncode,
            duration_ms,
            len(completed.stdout.splitlines()),
            MODEL_CONFIG_VERSION,
        )
        if completed.returncode != 0 or not output_path.is_file():
            raise DomainError(
                "INTERPRETATION_UNAVAILABLE",
                "Подготовка объяснения временно недоступна",
                recoverable=True,
                status_code=503,
            )
        if output_path.stat().st_size > 2_000_000:
            raise DomainError("INTERPRETATION_INVALID", "Ответ объяснения превышает допустимый размер", recoverable=True)
        try:
            return output_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DomainError("INTERPRETATION_INVALID", "Не удалось прочитать объяснение", recoverable=True) from exc

    def _child_environment(self) -> dict[str, str]:
        allowed_names = (
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
            "LOCALAPPDATA",
            "APPDATA",
            "USERPROFILE",
            "HOME",
            "HOMEDRIVE",
            "HOMEPATH",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
        )
        environment = {name: os.environ[name] for name in allowed_names if os.environ.get(name)}
        environment["CODEX_HOME"] = str(self.settings.codex_home)
        environment["NO_COLOR"] = "1"
        environment["CI"] = "1"
        if os.environ.get("OPENAI_API_KEY"):
            environment["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
        return environment

    @staticmethod
    def _validate_raw(
        raw_output: str,
        snapshot_id: str,
        facts: list[EvidenceFact],
        packets: list[DomainEvidencePacket],
        paid: bool,
    ) -> InterpretationBundle:
        try:
            value = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise _BundleValidationFailure([f"JSON parse error: {exc.msg}"], raw_output) from exc
        try:
            bundle = InterpretationBundle.model_validate(value)
        except ValidationError as exc:
            errors = [
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in exc.errors(include_url=False)
            ]
            raise _BundleValidationFailure(errors, raw_output) from exc
        bundle = _normalize_generated_contract(bundle, facts)
        try:
            return validate_bundle(bundle, snapshot_id, facts, packets, paid)
        except DomainError as exc:
            raise _BundleValidationFailure([f"{exc.code}: {exc.message}"], raw_output) from exc


def validate_bundle(
    bundle: InterpretationBundle,
    snapshot_id: str,
    facts: list[EvidenceFact],
    packets: list[DomainEvidencePacket],
    paid: bool,
) -> InterpretationBundle:
    """Apply evidence, editorial and access rules before persistence."""
    expected_schema = "interpretation.paid.v1" if paid else "interpretation.free.v1"
    if bundle.schema_version != expected_schema or bundle.snapshot_id != snapshot_id:
        raise DomainError("INTERPRETATION_INVALID", "Версия объяснения не соответствует расчёту", recoverable=True)
    if [packet.slug for packet in packets] != list(DOMAIN_ORDER):
        raise DomainError("INTERPRETATION_INVALID", "Набор оснований имеет неверный порядок", recoverable=True)

    expected_questions = 12 if paid else 6
    if len(bundle.questions) != expected_questions:
        raise DomainError("INTERPRETATION_INVALID", "Неверное число вопросов к себе", recoverable=True)
    if [question.id for question in bundle.questions] != [f"q_{index:02d}" for index in range(1, expected_questions + 1)]:
        raise DomainError("INTERPRETATION_INVALID", "Идентификаторы вопросов нарушают контракт", recoverable=True)
    if len({_normalized_text(question.text) for question in bundle.questions}) != expected_questions:
        raise DomainError("INTERPRETATION_INVALID", "Вопросы к себе повторяются", recoverable=True)
    if not paid and len({question.domain for question in bundle.questions}) != 6:
        raise DomainError("INTERPRETATION_INVALID", "Бесплатные вопросы не покрывают шесть разных тем", recoverable=True)
    if paid and set(question.domain for question in bundle.questions) != set(DOMAIN_ORDER):
        raise DomainError("INTERPRETATION_INVALID", "Платные вопросы не покрывают все темы", recoverable=True)

    by_id = _facts_by_id(facts)
    if len(by_id) != len(facts):
        raise DomainError("INTERPRETATION_INVALID", "В наборе оснований повторяются идентификаторы", recoverable=True)
    by_slug = _packet_by_slug(packets)
    if len(by_slug) != len(DOMAIN_ORDER):
        raise DomainError("INTERPRETATION_INVALID", "Набор оснований неполон", recoverable=True)
    if [domain.slug for domain in bundle.domains] != list(DOMAIN_ORDER):
        raise DomainError("INTERPRETATION_INVALID", "Нарушен порядок жизненных разделов", recoverable=True)

    if bundle.overview.slug != DomainSlug.CHARACTER or bundle.overview.section_label != "Главный рисунок":
        raise DomainError("INTERPRETATION_INVALID", "Главный рисунок нарушает контракт", recoverable=True)
    if bundle.overview.coverage != _overview_coverage(packets):
        raise DomainError("INTERPRETATION_INVALID", "Покрытие главного рисунка изменено вне расчёта", recoverable=True)
    if not set(bundle.overview.evidence_ids).issubset(by_id):
        raise DomainError("INTERPRETATION_INVALID", "Главный рисунок ссылается на неизвестный факт", recoverable=True)
    if bundle.overview.paragraphs or bundle.overview.manifestations or bundle.overview.reflection_prompts:
        raise DomainError("INTERPRETATION_INVALID", "Подробный синтез попал в краткий главный рисунок", recoverable=True)
    if not 220 <= len(bundle.overview.summary) <= 420:
        raise DomainError("INTERPRETATION_INVALID", "Главный рисунок имеет неверную длину", recoverable=True)

    texts: list[str] = [*bundle.global_limitations, *bundle.synthesis, bundle.overview.title, bundle.overview.summary]
    summaries: list[str] = []
    titles: list[str] = []
    for domain in bundle.domains:
        packet = by_slug.get(domain.slug)
        if packet is None:
            raise DomainError("INTERPRETATION_INVALID", "Раздел не связан с набором оснований", recoverable=True)
        if domain.section_label != DOMAIN_LABELS_RU[domain.slug]:
            raise DomainError("INTERPRETATION_INVALID", "Название жизненного раздела изменено", recoverable=True)
        if domain.coverage != packet.coverage:
            raise DomainError("INTERPRETATION_INVALID", "Уровень уверенности раздела изменён вне расчёта", recoverable=True)
        if _normalized_text(domain.title) == _normalized_text(domain.section_label) or len(domain.title) < 12:
            raise DomainError("INTERPRETATION_INVALID", "Заголовок раздела не содержит персонального наблюдения", recoverable=True)
        if not 220 <= len(domain.summary) <= 420:
            raise DomainError("INTERPRETATION_INVALID", "Бесплатная выжимка имеет неверную длину", recoverable=True)
        allowed = set(packet.primary_facts + packet.confirming_facts + packet.contradictions)
        evidence_set = set(domain.evidence_ids)
        if not evidence_set.issubset(allowed) or not evidence_set.issubset(by_id):
            raise DomainError("INTERPRETATION_INVALID", "Объяснение ссылается на неподтверждённый факт", recoverable=True)
        if packet.coverage == Coverage.MULTIPLE_FACTORS:
            if not evidence_set.intersection(packet.primary_facts) or not evidence_set.intersection(packet.confirming_facts):
                raise DomainError("INTERPRETATION_INVALID", "Связка раздела не использует подтверждающий фактор", recoverable=True)
        if packet.coverage == Coverage.INSUFFICIENT:
            if domain.title != "Для подробного вывода не хватает данных" or not domain.limitations:
                raise DomainError("INTERPRETATION_INVALID", "Ограниченный раздел скрывает нехватку данных", recoverable=True)
            if domain.paragraphs or domain.manifestations or domain.reflection_prompts:
                raise DomainError("INTERPRETATION_INVALID", "Ограниченный раздел заполнен общим подробным текстом", recoverable=True)
        required_chart = REQUIRED_DOMAIN_CHART.get(domain.slug)
        if required_chart and packet.coverage != Coverage.INSUFFICIENT:
            used_charts = {by_id[fact_id].chart.upper() for fact_id in evidence_set}
            if required_chart not in used_charts:
                raise DomainError("INTERPRETATION_INVALID", "Раздел не использует обязательную подтверждающую карту", recoverable=True)
        if not paid and (domain.paragraphs or domain.manifestations or domain.reflection_prompts):
            raise DomainError("INTERPRETATION_INVALID", "Подробный текст попал в бесплатный слой", recoverable=True)
        if paid and packet.coverage != Coverage.INSUFFICIENT:
            if not 4 <= len(domain.paragraphs) <= 7:
                raise DomainError("INTERPRETATION_INVALID", "Платный раздел имеет неверное число абзацев", recoverable=True)
            if not 2 <= len(domain.manifestations) <= 4 or not 1 <= len(domain.reflection_prompts) <= 2:
                raise DomainError("INTERPRETATION_INVALID", "Платный раздел неполон", recoverable=True)
            for index, paragraph in enumerate(domain.paragraphs):
                if _too_similar(paragraph, domain.summary, 0.84):
                    raise DomainError("INTERPRETATION_INVALID", "Подробный текст повторяет выжимку", recoverable=True)
                for other in domain.paragraphs[:index]:
                    if _too_similar(paragraph, other, 0.86):
                        raise DomainError("INTERPRETATION_INVALID", "Абзацы платного раздела повторяются", recoverable=True)
        summaries.append(domain.summary)
        titles.append(domain.title)
        texts.extend([domain.title, domain.summary, *domain.paragraphs, *domain.manifestations, *domain.reflection_prompts])

    if len({_normalized_text(title) for title in titles}) != len(titles):
        raise DomainError("INTERPRETATION_INVALID", "Заголовки жизненных разделов повторяются", recoverable=True)
    for index, summary in enumerate(summaries):
        for other in summaries[:index]:
            if _too_similar(summary, other, 0.82):
                raise DomainError("INTERPRETATION_INVALID", "Выжимки жизненных разделов слишком похожи", recoverable=True)

    for question in bundle.questions:
        packet = by_slug.get(question.domain)
        allowed = set(packet.primary_facts + packet.confirming_facts) if packet else set()
        if not packet or not set(question.evidence_ids).issubset(allowed) or not set(question.evidence_ids).issubset(by_id):
            raise DomainError("INTERPRETATION_INVALID", "Вопрос не связан с разрешённым фактом", recoverable=True)
        texts.extend([question.text, question.rationale])

    if tuple(bundle.global_limitations) != GLOBAL_LIMITATIONS:
        raise DomainError("INTERPRETATION_INVALID", "Границы метода сформулированы неверно", recoverable=True)
    if not paid and bundle.synthesis:
        raise DomainError("INTERPRETATION_INVALID", "Синтез доступен только в полном отчёте", recoverable=True)
    if paid and not 4 <= len(bundle.synthesis) <= 7:
        raise DomainError("INTERPRETATION_INVALID", "Общий синтез имеет неверную структуру", recoverable=True)

    joined = " ".join(texts).casefold()
    forbidden_public = next((term for term in FORBIDDEN_PUBLIC_TERMS if term in joined), None)
    if forbidden_public:
        raise DomainError(
            "INTERPRETATION_INVALID",
            f"В текст попало служебное обозначение: {forbidden_public}",
            recoverable=True,
        )
    forbidden_claim = next((term for term in FORBIDDEN_CLAIM_TERMS if term in joined), None)
    if forbidden_claim:
        raise DomainError(
            "INTERPRETATION_INVALID",
            f"Уберите опасное или фаталистическое выражение: {forbidden_claim}",
            recoverable=True,
        )
    if "<" in joined or ">" in joined or "http://" in joined or "https://" in joined:
        raise DomainError("INTERPRETATION_INVALID", "В текст попала неразрешённая разметка", recoverable=True)
    return bundle


def provider_from_environment() -> InterpretationProvider:
    provider = os.environ.get("VEDICWAY_INTERPRETATION_PROVIDER", "").strip().casefold()
    production = os.environ.get("VEDICWAY_ENV", "development").casefold() == "production"
    if provider == "codex":
        try:
            return CodexExecProvider()
        except DomainError as exc:
            LOGGER.error("codex_provider_configuration_failed code=%s", exc.code)
            if production:
                raise
            return UnavailableInterpretationProvider("Контур персонального объяснения не настроен")
    if provider == "stub":
        if production:
            raise DomainError(
                "INTERPRETATION_CONFIG_INVALID",
                "Тестовый провайдер объяснений запрещён в production",
                recoverable=False,
                status_code=503,
            )
        return DevelopmentInterpretationProvider()
    if production:
        raise DomainError(
            "INTERPRETATION_CONFIG_INVALID",
            "Production требует VEDICWAY_INTERPRETATION_PROVIDER=codex",
            recoverable=False,
            status_code=503,
        )
    return UnavailableInterpretationProvider(
        "Персональное объяснение отключено: укажите VEDICWAY_INTERPRETATION_PROVIDER=codex"
    )

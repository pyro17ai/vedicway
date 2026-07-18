from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .constants import DOMAIN_LABELS_RU, DOMAIN_ORDER, DomainSlug
from .errors import DomainError
from .schemas import (
    Coverage,
    DomainEvidencePacket,
    DomainInterpretation,
    EvidenceFact,
    InterpretationBundle,
    ReflectionQuestion,
)

FORBIDDEN_PUBLIC_TERMS = (
    "codex",
    "pyjhora",
    "mcp",
    "prompt",
    "промпт",
    "языковая модель",
    "модель сгенерировала",
    "внутренний агент",
)

SECTION_TITLES = {
    DomainSlug.CHARACTER: "Как проявляется ваш характер",
    DomainSlug.INNER_SUPPORT: "На что вы опираетесь внутри",
    DomainSlug.RELATIONSHIPS: "Как вы строите отношения",
    DomainSlug.FAMILY_HOME: "Дом, семья и чувство своего места",
    DomainSlug.WORK: "Рабочий стиль и реализация",
    DomainSlug.MONEY: "Денежные привычки и ресурсы",
    DomainSlug.LEARNING: "Как вы осваиваете новое",
    DomainSlug.CURRENT_PERIOD: "Темы текущего периода",
}

QUESTION_STEMS = {
    DomainSlug.CHARACTER: "В каких ситуациях мои сильные качества видны особенно ясно?",
    DomainSlug.INNER_SUPPORT: "Что возвращает мне чувство устойчивости, когда темп становится высоким?",
    DomainSlug.RELATIONSHIPS: "Какая форма близости помогает мне оставаться собой?",
    DomainSlug.FAMILY_HOME: "Какое пространство и какие правила дома дают мне чувство опоры?",
    DomainSlug.WORK: "В какой работе мой способ действовать получает достойное применение?",
    DomainSlug.MONEY: "Какие привычки помогают мне бережно обращаться с ресурсами?",
    DomainSlug.LEARNING: "Какой формат обучения помогает мне удерживать интерес и доводить знания до практики?",
    DomainSlug.CURRENT_PERIOD: "Какие темы текущего периода я хочу наблюдать без спешки и готовых выводов?",
}


def _checksum(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def _facts_by_id(facts: list[EvidenceFact]) -> dict[str, EvidenceFact]:
    return {fact.id: fact for fact in facts}


def _packet_by_slug(packets: list[DomainEvidencePacket]) -> dict[DomainSlug, DomainEvidencePacket]:
    return {packet.slug: packet for packet in packets}


def _summary(slug: DomainSlug, facts: list[EvidenceFact], coverage: Coverage) -> str:
    labels = "; ".join(fact.human_label_ru.lower() for fact in facts[:2])
    if coverage == Coverage.INSUFFICIENT:
        return "Для этого раздела пока недостаточно взаимно подтверждающих расчётных данных. Карта сохранена, а подробности появятся после завершения следующих разделов."
    if coverage == Coverage.SINGLE_FACTOR:
        return f"В теме «{DOMAIN_LABELS_RU[slug]}» виден один устойчивый ориентир: {labels}. Рассматривайте его как повод присмотреться к своим привычкам, не как готовый вывод о будущем."
    return f"В теме «{DOMAIN_LABELS_RU[slug]}» сочетаются два ориентира: {labels}. Их полезно читать вместе и соотносить с собственным опытом, без попытки предсказать точный исход событий."


class InterpretationProvider(ABC):
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
    """Deterministic provider for local development and contract tests.

    It is deliberately evidence-first: every paragraph has only facts approved for
    its domain, which also makes it a safe fallback when the isolated agent is down.
    """

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
            limitations = []
            if packet.coverage == Coverage.INSUFFICIENT:
                limitations.append("Раздел ждёт данных из следующего расчётного слоя.")
            elif packet.coverage == Coverage.SINGLE_FACTOR:
                limitations.append("Вывод опирается на один расчётный ориентир.")
            paragraphs: list[str] = []
            manifestations: list[str] = []
            reflection_prompts: list[str] = []
            if paid and evidence:
                evidence_names = ", ".join(fact.human_label_ru for fact in evidence)
                paragraphs = [
                    f"{evidence_names}. Эта связка описывает способ наблюдать за темой «{DOMAIN_LABELS_RU[packet.slug]}» в повседневных выборах и отношениях с собой.",
                    "Полезнее замечать повторяющиеся ситуации, чем искать в карте единый ответ. Так личный опыт остаётся главным критерием, а расчёт помогает сформулировать вопрос точнее.",
                    "Если факты откликаются неоднозначно, оставьте место для контекста: возраста, обстоятельств, среды и собственного решения. Карта не назначает роль и не отменяет свободу действия.",
                ]
                manifestations = [
                    "Наблюдайте за повторяющимся способом реагировать в знакомых обстоятельствах.",
                    "Отмечайте, что поддерживает ясность и что забирает силы в этой теме.",
                ]
                reflection_prompts = [QUESTION_STEMS[packet.slug]]
            domains.append(
                DomainInterpretation(
                    slug=packet.slug,
                    section_label=DOMAIN_LABELS_RU[packet.slug],
                    title=SECTION_TITLES[packet.slug],
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
            suffix = "" if index < len(selected_domains) else " Что я могу проверить в ближайший месяц своим опытом?"
            questions.append(
                ReflectionQuestion(
                    id=f"q_{slug.value}_{index + 1}",
                    domain=slug,
                    text=QUESTION_STEMS[slug] + suffix,
                    rationale="Вопрос привязан к указанным положениям карты и предлагает наблюдение, а не готовый прогноз.",
                    evidence_ids=evidence_ids or ["unavailable"],
                )
            )
        overview = domains[0].model_copy(
            update={
                "title": "Первое чтение карты",
                "summary": "Карта готова. Начните с восьми жизненных тем и сверяйте каждую формулировку с собственным опытом. Подробный отчёт добавляет развёрнутые объяснения и двенадцать вопросов к себе.",
            }
        )
        return InterpretationBundle(
            schema_version="interpretation.paid.v1" if paid else "interpretation.free.v1",
            snapshot_id=snapshot_id,
            overview=overview,
            domains=domains,
            questions=questions,
            global_limitations=[
                "Материал предназначен для самонаблюдения и знакомства с астрологической традицией.",
                "Он не заменяет медицинскую, юридическую, финансовую или психологическую помощь.",
            ],
            synthesis=(
                [
                    "Сводный текст соединяет темы карты в последовательность для наблюдения, а не в сценарий будущего.",
                    "Возвращайтесь к выбранным вопросам после реальных событий и уточняйте собственные выводы.",
                ]
                if paid
                else []
            ),
        )


class CodexExecProvider(InterpretationProvider):
    """One-shot, schema-constrained process adapter for the isolated production worker."""

    def __init__(self, fallback: InterpretationProvider | None = None) -> None:
        self.fallback = fallback

    def generate(
        self,
        snapshot_id: str,
        facts: list[EvidenceFact],
        packets: list[DomainEvidencePacket],
        paid: bool,
    ) -> InterpretationBundle:
        if os.environ.get("VEDICWAY_INTERPRETATION_PROVIDER") != "codex":
            if self.fallback:
                return self.fallback.generate(snapshot_id, facts, packets, paid)
            raise DomainError("INTERPRETATION_UNAVAILABLE", "Поставщик объяснения временно недоступен", recoverable=True, status_code=503)
        codex_home = os.environ.get("VEDICWAY_CODEX_HOME")
        sandbox_dir = os.environ.get("VEDICWAY_AGENT_WORKDIR")
        if not codex_home or not sandbox_dir:
            raise DomainError("INTERPRETATION_UNAVAILABLE", "Не настроен изолированный контур объяснения", recoverable=False, status_code=503)
        with tempfile.TemporaryDirectory(prefix="vedicway-agent-") as temporary:
            temp_path = Path(temporary)
            output_path = temp_path / "result.json"
            schema_path = temp_path / "interpretation-schema.json"
            schema_path.write_text(json.dumps(InterpretationBundle.model_json_schema(), ensure_ascii=False), encoding="utf-8")
            prompt = self._prompt(snapshot_id, facts, packets, paid)
            command = [
                "codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--strict-config",
                "--sandbox", "read-only", "--skip-git-repo-check", "-C", sandbox_dir,
                "-m", "gpt-5.6-terra" if paid else "gpt-5.6-luna",
                "-c", f'model_reasoning_effort="{"medium" if paid else "low"}"',
                "-c", 'features.apps=false', "-c", 'features.multi_agent=false', "-c", 'features.shell_tool=false',
                "--output-schema", str(schema_path), "--output-last-message", str(output_path), "--json", "-",
            ]
            environment = {"CODEX_HOME": codex_home, "PATH": os.environ.get("PATH", "")}
            try:
                completed = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    timeout=120 if paid else 35,
                    shell=False,
                    env=environment,
                    cwd=sandbox_dir,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise DomainError("INTERPRETATION_UNAVAILABLE", "Подготовка объяснения заняла слишком много времени", recoverable=True, status_code=503) from exc
            if completed.returncode != 0 or not output_path.exists():
                raise DomainError("INTERPRETATION_UNAVAILABLE", "Подготовка объяснения временно недоступна", recoverable=True, status_code=503)
            try:
                value = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise DomainError("INTERPRETATION_INVALID", "Не удалось проверить структуру объяснения", recoverable=True) from exc
        try:
            return InterpretationBundle.model_validate(value)
        except ValidationError as exc:
            raise DomainError("INTERPRETATION_INVALID", "Структура объяснения не прошла проверку", recoverable=True) from exc

    @staticmethod
    def _prompt(snapshot_id: str, facts: list[EvidenceFact], packets: list[DomainEvidencePacket], paid: bool) -> str:
        return _json_dump(
            {
                "task": "Сформируй только JSON по приложенной схеме для русскоязычного материала о самонаблюдении.",
                "rules": [
                    "Работай только с фактами из evidence.",
                    "Не называй внутренние технологии, инструменты, модели или источники кода.",
                    "Не обещай точные события, даты, диагнозы, финансовые результаты или решения за человека.",
                    "Не используй HTML, Markdown и ссылки.",
                    "Порядок восьми domains должен совпадать с packets.",
                    "Бесплатный вариант содержит шесть вопросов и не содержит подробных paragraphs.",
                ],
                "access": "paid_full" if paid else "free_summary",
                "snapshot_id": snapshot_id,
                "evidence": [fact.model_dump(mode="json") for fact in facts],
                "packets": [packet.model_dump(mode="json") for packet in packets],
            }
        )


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_bundle(
    bundle: InterpretationBundle,
    snapshot_id: str,
    facts: list[EvidenceFact],
    packets: list[DomainEvidencePacket],
    paid: bool,
) -> InterpretationBundle:
    """Apply schema, evidence, editorial and commercial access rules before persistence."""
    expected_schema = "interpretation.paid.v1" if paid else "interpretation.free.v1"
    if bundle.schema_version != expected_schema or bundle.snapshot_id != snapshot_id:
        raise DomainError("INTERPRETATION_INVALID", "Версия объяснения не соответствует расчёту", recoverable=True)
    expected_questions = 12 if paid else 6
    if len(bundle.questions) != expected_questions:
        raise DomainError("INTERPRETATION_INVALID", "Неверное число вопросов к себе", recoverable=True)
    if len({question.id for question in bundle.questions}) != expected_questions:
        raise DomainError("INTERPRETATION_INVALID", "Повторяются идентификаторы вопросов", recoverable=True)
    by_id = _facts_by_id(facts)
    by_slug = _packet_by_slug(packets)
    if [domain.slug for domain in bundle.domains] != list(DOMAIN_ORDER):
        raise DomainError("INTERPRETATION_INVALID", "Нарушен порядок жизненных разделов", recoverable=True)
    texts: list[str] = [*bundle.global_limitations, *bundle.synthesis, bundle.overview.title, bundle.overview.summary]
    for domain in bundle.domains:
        packet = by_slug.get(domain.slug)
        if packet is None:
            raise DomainError("INTERPRETATION_INVALID", "Раздел не связан с набором доказательств", recoverable=True)
        if domain.coverage != packet.coverage:
            raise DomainError("INTERPRETATION_INVALID", "Уровень уверенности раздела изменён вне расчёта", recoverable=True)
        allowed = set(packet.primary_facts + packet.confirming_facts + packet.contradictions)
        if not set(domain.evidence_ids).issubset(allowed) or not set(domain.evidence_ids).issubset(by_id):
            raise DomainError("INTERPRETATION_INVALID", "Объяснение ссылается на неподтверждённый факт", recoverable=True)
        if not paid and (domain.paragraphs or domain.manifestations or domain.reflection_prompts):
            raise DomainError("INTERPRETATION_INVALID", "Подробный текст попал в бесплатный слой", recoverable=True)
        texts.extend([domain.title, domain.summary, *domain.paragraphs, *domain.manifestations, *domain.reflection_prompts])
    for question in bundle.questions:
        packet = by_slug.get(question.domain)
        if packet is None or not set(question.evidence_ids).issubset(set(packet.primary_facts + packet.confirming_facts)):
            raise DomainError("INTERPRETATION_INVALID", "Вопрос не связан с разрешённым фактом", recoverable=True)
        texts.extend([question.text, question.rationale])
    if not paid and bundle.synthesis:
        raise DomainError("INTERPRETATION_INVALID", "Синтез доступен только в полном отчёте", recoverable=True)
    joined = " ".join(texts).casefold()
    if any(term in joined for term in FORBIDDEN_PUBLIC_TERMS):
        raise DomainError("INTERPRETATION_INVALID", "В текст попало служебное обозначение", recoverable=True)
    if "<" in joined or ">" in joined or "http://" in joined or "https://" in joined:
        raise DomainError("INTERPRETATION_INVALID", "В текст попала неразрешённая разметка", recoverable=True)
    return bundle


def provider_from_environment() -> InterpretationProvider:
    fallback = DevelopmentInterpretationProvider()
    return CodexExecProvider(fallback=fallback)

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .constants import DOMAIN_LABELS_RU, DOMAIN_ORDER, DomainSlug
from .schemas import Coverage, DomainEvidencePacket, EvidenceFact, InterpretationBundle

PROMPT_VERSION = "interpretation-editor-ru.v2"
MODEL_CONFIG_VERSION = "codex-exec-isolated.v2"
GLOBAL_LIMITATIONS = (
    "Материал предназначен для самонаблюдения и знакомства с астрологической традицией.",
    "Он не заменяет медицинскую, юридическую, финансовую или психологическую помощь.",
)

DOMAIN_GUIDANCE: dict[DomainSlug, str] = {
    DomainSlug.CHARACTER: (
        "Опиши способ начинать дела, проявлять волю и обозначать границы. "
        "D1 служит основой; не превращай знак или одну планету в ярлык личности."
    ),
    DomainSlug.INNER_SUPPORT: (
        "Опиши эмоциональную устойчивость, восстановление и внутренние опоры. "
        "Различай переживание и внешнее поведение; не используй психологические диагнозы."
    ),
    DomainSlug.RELATIONSHIPS: (
        "Опиши способ сближаться, сохранять себя в союзе и проживать повторяющееся напряжение. "
        "D9 подтверждает тему отношений, но не предсказывает конкретного партнёра или исход союза."
    ),
    DomainSlug.FAMILY_HOME: (
        "Опиши потребности в доме, близости, корнях и чувстве своего места. "
        "D4 подтверждает тему; не приписывай факты биографии и поступки родственников."
    ),
    DomainSlug.WORK: (
        "Опиши рабочий ритм, способ брать ответственность и подходящие условия реализации. "
        "D10 подтверждает тему; не называй гарантированную профессию, должность или срок карьерного события."
    ),
    DomainSlug.MONEY: (
        "Опиши отношение к накоплению, риску и материальной опоре. D2 подтверждает тему; "
        "не давай инвестиционных рекомендаций и не обещай доход."
    ),
    DomainSlug.LEARNING: (
        "Опиши способ удерживать интерес, усваивать знание и переводить его в мастерство. "
        "D24 подтверждает тему; не утверждай уровень интеллекта или неизбежный результат обучения."
    ),
    DomainSlug.CURRENT_PERIOD: (
        "Опиши активные махадашу и антардашу как фон внимания и вероятностей. "
        "Транзитов во входе нет: не называй точное будущее событие и дату его наступления."
    ),
}

_STABLE_PREFIX = """Ты пишешь персональное чтение ведической натальной карты для сервиса VedicWay.

РОЛЬ И ГРАНИЦА
Ты редактор, который переводит уже рассчитанные факты карты в ясные наблюдения для взрослого человека. Ты не рассчитываешь карту, не исправляешь входные положения и не добавляешь астрологические данные из памяти. Единственный источник персональных утверждений — блок EVIDENCE_PAYLOAD в конце задания.

ДИСЦИПЛИНА ДОКАЗАТЕЛЬСТВ
1. Каждое персональное утверждение опирается на один или несколько evidence_ids из соответствующего domain packet. Нельзя использовать идентификатор, которого нет во входе, или переносить факт между доменами без разрешения packet.
2. При multiple_factors свяжи основной и подтверждающий факты, покажи их совместный рисунок или напряжение. При single_factor прямо обозначь, что виден один ориентир. При insufficient используй заголовок «Для подробного вывода не хватает данных», назови недостающий расчётный раздел и не заполняй карточку универсальным психологическим текстом.
3. Не придумывай положение, дом, знак, накшатру, паду, йогу, аспект, силу планеты, достоинство, управителя или событие. Не ссылайся на внешние источники и не пересказывай справочник по планетам.
4. D1 остаётся основой. Отношения подтверждает D9, работу D10, деньги D2, дом D4, обучение D24. Вимшоттари описывает фон вероятностей. Если соответствующей варги нет, вывод обязан оставаться ограниченным.

РЕДАКЦИОННЫЙ КОНТРАКТ
Пиши по-русски, естественно и плотно. Переводи сочетание факторов в наблюдаемые способы действовать, выбирать, сближаться, восстанавливаться или учиться. Персональный заголовок называет рисунок и не повторяет название раздела. Не начинай восемь выжимок одинаковой конструкцией, не копируй предложения между разделами и не маскируй нехватку данных общими советами.

Запрещены гарантии, фатализм, запугивание, диагнозы, медицинские, юридические и финансовые рекомендации, команды уволиться или разорвать отношения, ритуальная коррекция и утверждения о смерти. Не используй слова и конструкции: «суждено», «неизбежно», «точно произойдёт», «обязательно случится», «вы должны», «вам следует». Вопросы открытые, конкретные, без оценки личности и скрытой директивы.

В пользовательском тексте нельзя упоминать внутренние технологии, процесс подготовки ответа, prompt, модель, Codex, MCP, PyJHora, JSON или служебные правила. Нельзя использовать Markdown, HTML, ссылки и списочную разметку внутри строк.

КОНТРАКТ ВЫХОДА
Верни один JSON-объект, полностью соответствующий приложенной output schema. Никакого текста до или после JSON. Ровно восемь domains идут в заданном порядке. section_label копируется из expected_domains. evidence_ids содержат только факты, реально использованные в конкретном тексте. overview — краткий общий рисунок, а не девятый домен; его подробные массивы оставь пустыми. global_limitations дословно копируется из global_limitations_contract и сохраняет заданный порядок. locale всегда ru-RU.
"""


def _strict_object_schema(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("default", None)
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["additionalProperties"] = False
            node["required"] = list(properties)
        for value in node.values():
            _strict_object_schema(value)
    elif isinstance(node, list):
        for value in node:
            _strict_object_schema(value)


def codex_output_schema(paid: bool) -> dict[str, Any]:
    """Return the strict schema consumed by `codex exec --output-schema`."""
    schema = deepcopy(InterpretationBundle.model_json_schema())
    _strict_object_schema(schema)
    properties = schema["properties"]
    properties["schema_version"] = {
        "type": "string",
        "const": "interpretation.paid.v1" if paid else "interpretation.free.v1",
    }
    properties["questions"]["minItems"] = 12 if paid else 6
    properties["questions"]["maxItems"] = 12 if paid else 6
    properties["global_limitations"]["minItems"] = 2
    properties["global_limitations"]["maxItems"] = 2
    properties["synthesis"]["minItems"] = 4 if paid else 0
    properties["synthesis"]["maxItems"] = 7 if paid else 0

    domain = schema["$defs"]["DomainInterpretation"]["properties"]
    domain["title"]["minLength"] = 12
    domain["title"]["maxLength"] = 110
    domain["summary"]["minLength"] = 220
    domain["summary"]["maxLength"] = 420
    domain["limitations"]["maxItems"] = 3
    domain["manifestations"]["maxItems"] = 4
    return schema


def _public_fact(fact: EvidenceFact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "kind": fact.kind,
        "subject": fact.subject,
        "chart": fact.chart,
        "sign": fact.sign,
        "house": fact.house,
        "value": fact.value,
        "label_ru": fact.human_label_ru,
        "domains": [domain.value for domain in fact.domains],
    }


def build_interpretation_prompt(
    snapshot_id: str,
    facts: list[EvidenceFact],
    packets: list[DomainEvidencePacket],
    paid: bool,
    repair: dict[str, Any] | None = None,
) -> str:
    if paid:
        length_contract = (
            "Для каждого готового домена: summary 220–420 знаков и 4–7 самостоятельных paragraphs "
            "общим объёмом 350–550 слов. Первый абзац называет центральный рисунок, второй связывает "
            "его с evidence, третий раскрывает сочетание или противоречие, четвёртый переводит его в "
            "наблюдаемые ситуации, последний даёт способ осмысления без директивы. Добавь 2–4 "
            "manifestations и 1–2 reflection_prompts. synthesis содержит 4–7 плотных абзацев общим "
            "объёмом 450–700 слов без последовательного пересказа восьми карточек."
        )
    else:
        length_contract = (
            "Для каждого домена дай законченную summary длиной 220–420 знаков, обычно 2–4 предложения. "
            "paragraphs, manifestations и reflection_prompts во всех domains и overview оставь пустыми. "
            "synthesis оставь пустым."
        )
    question_count = 12 if paid else 6
    dynamic_contract = (
        f"\n\nРЕЖИМ ЗАДАНИЯ\naccess={'paid_full' if paid else 'free_summary'}; "
        f"schema_version={'interpretation.paid.v1' if paid else 'interpretation.free.v1'}; "
        f"questions={question_count}.\n{length_contract}\n"
        f"Создай ровно {question_count} уникальных вопросов. В бесплатном наборе используй шесть разных "
        "доменов. В платном наборе покрой все восемь доменов, а четыре дополнительных вопроса раскрой "
        "через другие наблюдаемые ситуации. rationale объясняет связь вопроса с 1–2 указанными фактами. "
        "Идентификаторы вопросов: q_01, q_02 и далее по порядку."
    )
    usable_fact_ids = {
        fact_id
        for packet in packets
        for fact_id in packet.primary_facts + packet.confirming_facts
    }
    if len(usable_fact_ids) >= 2:
        overview_coverage = Coverage.MULTIPLE_FACTORS
    elif usable_fact_ids:
        overview_coverage = Coverage.SINGLE_FACTOR
    else:
        overview_coverage = Coverage.INSUFFICIENT
    payload: dict[str, Any] = {
        "prompt_version": PROMPT_VERSION,
        "snapshot_id": snapshot_id,
        "locale": "ru-RU",
        "overview_contract": {
            "slug": DomainSlug.CHARACTER.value,
            "section_label": "Главный рисунок",
            "coverage": overview_coverage.value,
            "evidence_ids": "выбери 2–5 действительно использованных ID из разных готовых доменов",
        },
        "global_limitations_contract": list(GLOBAL_LIMITATIONS),
        "expected_domains": [
            {
                "slug": slug.value,
                "section_label": DOMAIN_LABELS_RU[slug],
                "guidance": DOMAIN_GUIDANCE[slug],
            }
            for slug in DOMAIN_ORDER
        ],
        "evidence": [_public_fact(fact) for fact in facts],
        "packets": [packet.model_dump(mode="json") for packet in packets],
    }
    if repair:
        payload["repair"] = repair
    return (
        _STABLE_PREFIX
        + dynamic_contract
        + "\n\nEVIDENCE_PAYLOAD\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )

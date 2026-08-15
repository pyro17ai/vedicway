from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from vedicway_backend.constants import DOMAIN_LABELS_RU, DOMAIN_ORDER, DomainSlug
from vedicway_backend.errors import DomainError
from vedicway_backend.interpretation import (
    CodexExecProvider,
    CodexExecSettings,
    DevelopmentInterpretationProvider,
    UnavailableInterpretationProvider,
    free_projection,
    provider_from_environment,
    validate_bundle,
)
from vedicway_backend.interpretation_prompt import (
    GLOBAL_LIMITATIONS,
    PROMPT_VERSION,
    build_interpretation_prompt,
    codex_output_schema,
)
from vedicway_backend.schemas import Coverage, DomainEvidencePacket, EvidenceFact

CHART_BY_DOMAIN = {
    DomainSlug.CHARACTER: "D1",
    DomainSlug.INNER_SUPPORT: "D1",
    DomainSlug.RELATIONSHIPS: "D9",
    DomainSlug.FAMILY_HOME: "D4",
    DomainSlug.WORK: "D10",
    DomainSlug.MONEY: "D2",
    DomainSlug.LEARNING: "D24",
    DomainSlug.CURRENT_PERIOD: "D1",
}


def _evidence() -> tuple[list[EvidenceFact], list[DomainEvidencePacket]]:
    facts: list[EvidenceFact] = []
    packets: list[DomainEvidencePacket] = []
    for index, slug in enumerate(DOMAIN_ORDER, start=1):
        chart = CHART_BY_DOMAIN[slug]
        primary_id = f"ev_{slug.value}_primary"
        confirming_id = f"ev_{slug.value}_confirming"
        facts.extend(
            [
                EvidenceFact(
                    id=primary_id,
                    kind="planet_position",
                    subject=f"Основа {index}",
                    chart=chart,
                    sign="Рак",
                    house=index,
                    human_label_ru=f"{chart}: основной фактор темы {DOMAIN_LABELS_RU[slug]}",
                    domains=[slug],
                    source_paths=[f"sections.{chart}.{index}.primary"],
                ),
                EvidenceFact(
                    id=confirming_id,
                    kind="planet_position",
                    subject=f"Подтверждение {index}",
                    chart=chart,
                    sign="Дева",
                    house=(index % 12) + 1,
                    human_label_ru=f"{chart}: подтверждающий фактор темы {DOMAIN_LABELS_RU[slug]}",
                    domains=[slug],
                    source_paths=[f"sections.{chart}.{index}.confirming"],
                ),
            ]
        )
        packets.append(
            DomainEvidencePacket(
                slug=slug,
                primary_facts=[primary_id],
                confirming_facts=[confirming_id],
                coverage=Coverage.MULTIPLE_FACTORS,
                allowed_claim_scope="Наблюдаемая склонность без прогноза точного события.",
            )
        )
    return facts, packets


def test_prompt_and_schema_keep_personal_data_out_of_runner_contract() -> None:
    facts, packets = _evidence()
    prompt = build_interpretation_prompt(facts, packets, paid=False)
    schema = codex_output_schema(paid=False)
    payload_text = prompt.split("\n\nEVIDENCE_PAYLOAD\n", 1)[1]
    payload = json.loads(payload_text.split("\n\n<!-- answering format -->", 1)[0])
    assert PROMPT_VERSION in prompt
    assert "snapshot_public" not in prompt
    assert "snapshot_id" not in payload
    assert "D10" in prompt and "D9" in prompt
    assert all(limitation in prompt for limitation in GLOBAL_LIMITATIONS)
    assert "Григорий" not in prompt and "grisha@example.com" not in prompt and "Москва, Россия" not in prompt
    assert schema["properties"]["questions"]["minItems"] == 6
    assert schema["properties"]["questions"]["maxItems"] == 6
    assert schema["properties"]["synthesis"]["maxItems"] == 0
    assert "snapshot_id" not in schema["properties"]
    assert "snapshot_id" not in schema["required"]
    required = schema["$defs"]["DomainInterpretation"]["required"]
    assert "paragraphs" in required and "manifestations" in required and "reflection_prompts" in required

    paid_schema = codex_output_schema(paid=True)
    paid_domain = paid_schema["$defs"]["DomainInterpretation"]["properties"]
    assert paid_domain["evidence_ids"]["maxItems"] == 6
    assert paid_domain["paragraphs"]["items"]["minLength"] == 240
    assert paid_schema["properties"]["synthesis"]["items"]["minLength"] == 300
    assert "управителя 10-го дома" in build_interpretation_prompt(facts, packets, paid=True)
    assert "управителей 2-го и 11-го домов" in build_interpretation_prompt(facts, packets, paid=True)
    assert "dasha_timeline" in build_interpretation_prompt(facts, packets, paid=True)


@pytest.mark.parametrize("paid", [False, True])
def test_prompt_ends_with_requested_russian_answering_format(paid: bool) -> None:
    facts, packets = _evidence()
    prompt = build_interpretation_prompt(facts, packets, paid=paid)

    assert PROMPT_VERSION == "interpretation-editor-ru.v4"
    assert "\n\n<!-- answering format -->\n" in prompt
    assert "Отвечай мне всегда естественным публицистическим русским языком" in prompt
    assert "Не пиши заключительный абзац" in prompt
    assert "Каждое предложение должно сообщать факт" in prompt
    assert prompt.endswith("<!-- answering format -->")


def test_explicit_contract_stub_is_valid_but_never_selected_implicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    facts, packets = _evidence()
    bundle = DevelopmentInterpretationProvider().generate("snapshot_stub", facts, packets, paid=False)
    assert tuple(bundle.global_limitations) == GLOBAL_LIMITATIONS
    validate_bundle(bundle, "snapshot_stub", facts, packets, paid=False)
    monkeypatch.delenv("VEDICWAY_INTERPRETATION_PROVIDER", raising=False)
    provider = provider_from_environment()
    assert isinstance(provider, UnavailableInterpretationProvider)
    with pytest.raises(DomainError, match="Персональное объяснение отключено"):
        provider.generate("snapshot_stub", facts, packets, paid=False)


def test_full_bundle_yields_valid_preview_without_second_generation() -> None:
    facts, packets = _evidence()
    full = DevelopmentInterpretationProvider().generate("snapshot_stub", facts, packets, paid=True)

    preview = free_projection(full)

    validate_bundle(full, "snapshot_stub", facts, packets, paid=True)
    validate_bundle(preview, "snapshot_stub", facts, packets, paid=False)
    assert len(full.questions) == 12
    assert len(preview.questions) == 6
    assert preview.overview.summary == full.overview.summary
    assert all(not domain.paragraphs for domain in preview.domains)


def test_paid_validator_rejects_thin_domain_and_synthesis() -> None:
    facts, packets = _evidence()
    full = DevelopmentInterpretationProvider().generate("snapshot_thin", facts, packets, paid=True)

    thin_domain = full.model_copy(deep=True)
    thin_domain.domains[0].paragraphs = ["Короткое повторение без подробного разбора."] * 4
    with pytest.raises(DomainError, match="Платный раздел раскрыт слишком кратко"):
        validate_bundle(thin_domain, "snapshot_thin", facts, packets, paid=True)

    thin_synthesis = full.model_copy(deep=True)
    thin_synthesis.synthesis = ["Короткий общий вывод без подробного синтеза."] * 4
    with pytest.raises(DomainError, match="Общий синтез раскрыт слишком кратко"):
        validate_bundle(thin_synthesis, "snapshot_thin", facts, packets, paid=True)


def test_paid_validator_requires_available_future_period_timeline() -> None:
    facts, packets = _evidence()
    timeline_id = "ev_shared_dasha_timeline"
    facts.append(
        EvidenceFact(
            id=timeline_id,
            kind="dasha_timeline",
            subject="Шкала периодов Вимшоттари",
            chart="D1",
            value={"mahadashas": []},
            human_label_ru="Текущий и ближайшие будущие периоды Вимшоттари",
            domains=[DomainSlug.CURRENT_PERIOD, DomainSlug.WORK, DomainSlug.MONEY],
            source_paths=["sections.dashas.data.maha_dashas"],
        )
    )
    for packet in packets:
        if packet.slug in {DomainSlug.CURRENT_PERIOD, DomainSlug.WORK, DomainSlug.MONEY}:
            packet.confirming_facts.append(timeline_id)

    full = DevelopmentInterpretationProvider().generate(
        "snapshot_timeline", facts, packets, paid=True
    )
    validate_bundle(full, "snapshot_timeline", facts, packets, paid=True)

    without_timeline = full.model_copy(deep=True)
    work = next(domain for domain in without_timeline.domains if domain.slug == DomainSlug.WORK)
    work.evidence_ids.remove(timeline_id)
    with pytest.raises(DomainError, match="не использует шкалу текущих и будущих периодов"):
        validate_bundle(without_timeline, "snapshot_timeline", facts, packets, paid=True)


def test_production_provider_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.setenv("VEDICWAY_INTERPRETATION_PROVIDER", "stub")
    with pytest.raises(DomainError, match="запрещён в production"):
        provider_from_environment()

    monkeypatch.setenv("VEDICWAY_INTERPRETATION_PROVIDER", "codex")
    monkeypatch.setenv("VEDICWAY_CODEX_HOME", str(tmp_path / "missing-codex-home"))
    monkeypatch.setenv("VEDICWAY_AGENT_WORKDIR", str(tmp_path / "missing-workdir"))
    with pytest.raises(DomainError, match="Каталоги контура объяснения не готовы"):
        provider_from_environment()


def test_codex_settings_use_standard_openai_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    workdir = tmp_path / "empty-workdir"
    codex_home.mkdir()
    workdir.mkdir()
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"test")
    monkeypatch.setenv("VEDICWAY_CODEX_HOME", str(codex_home))
    monkeypatch.setenv("VEDICWAY_AGENT_WORKDIR", str(workdir))
    monkeypatch.setenv("VEDICWAY_CODEX_EXECUTABLE", str(executable))
    monkeypatch.setenv("CODEX_API_KEY", "legacy-key-must-not-work")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(DomainError, match="нет авторизации"):
        CodexExecSettings.from_environment()

    monkeypatch.setenv("OPENAI_API_KEY", "standard-cli-key")
    settings = CodexExecSettings.from_environment()
    environment = CodexExecProvider(settings)._child_environment()
    assert environment["OPENAI_API_KEY"] == "standard-cli-key"
    assert "CODEX_API_KEY" not in environment


def test_editorial_validator_rejects_copied_domain_summary() -> None:
    facts, packets = _evidence()
    bundle = DevelopmentInterpretationProvider().generate("snapshot_repeat", facts, packets, paid=False)
    copied = bundle.model_copy(deep=True)
    copied.domains[1].summary = copied.domains[0].summary
    with pytest.raises(DomainError, match="слишком похожи"):
        validate_bundle(copied, "snapshot_repeat", facts, packets, paid=False)


def test_editorial_validator_accepts_non_fatalistic_boundary_wording() -> None:
    facts, packets = _evidence()
    bundle = DevelopmentInterpretationProvider().generate("snapshot_boundary", facts, packets, paid=False)
    bundle.domains[0].summary = (
        "Этот рисунок не означает, что вам что-либо суждено или что выбор сделан заранее. "
        "Рассчитанные положения описывают склонность входить в новое дело собранно, замечать контекст и яснее "
        "обозначать свою зону решения. Наблюдение полезно сверять с реальными ситуациями, где инициатива и "
        "чувствительность к обстоятельствам проявляются одновременно."
    )
    validate_bundle(bundle, "snapshot_boundary", facts, packets, paid=False)


def test_codex_provider_uses_native_executable_and_repairs_invalid_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facts, packets = _evidence()
    valid = DevelopmentInterpretationProvider().generate("snapshot_live", facts, packets, paid=False)
    codex_home = tmp_path / "codex-home"
    workdir = tmp_path / "empty-workdir"
    codex_home.mkdir()
    workdir.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"test")
    settings = CodexExecSettings(codex_home=codex_home, workdir=workdir, executable=executable)
    monkeypatch.setenv("OPENAI_API_KEY", "standard-cli-key")
    calls: list[dict[str, object]] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        output_path = Path(command[command.index("--output-last-message") + 1])
        value = {"invalid": True} if len(calls) == 1 else valid.model_dump(mode="json")
        value.pop("snapshot_id", None)
        output_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout='{"type":"thread.completed"}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CodexExecProvider(settings).generate("snapshot_live", facts, packets, paid=False)
    assert result.schema_version == "interpretation.free.v1"
    assert result.snapshot_id == "snapshot_live"
    assert "snapshot_live" not in str(calls[0]["input"])
    assert "snapshot_live" not in str(calls[1]["input"])
    assert len(calls) == 2
    first_command = calls[0]["command"]
    assert first_command[0] == str(executable)
    assert calls[0]["shell"] is False
    assert "timeout" not in calls[0]
    assert calls[0]["env"]["CODEX_HOME"] == str(codex_home)
    assert calls[0]["env"]["OPENAI_API_KEY"] == "standard-cli-key"
    assert "CODEX_API_KEY" not in calls[0]["env"]
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--strict-config"):
        assert flag in first_command
    assert first_command[first_command.index("--sandbox") + 1] == "read-only"
    assert 'web_search="disabled"' in first_command
    assert "features.apps=false" in first_command
    assert "features.multi_agent=false" in first_command
    assert "features.shell_tool=false" in first_command
    assert '"repair"' in calls[1]["input"]


def test_codex_provider_derives_overview_citations_and_fixed_limitations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facts, packets = _evidence()
    generated = DevelopmentInterpretationProvider().generate("snapshot_normalized", facts, packets, paid=False)
    generated.overview.evidence_ids = ["invented_overview_fact"]
    generated.domains[0].evidence_ids = ["invented_domain_fact"]
    generated.questions[0].evidence_ids = ["invented_question_fact"]
    generated.global_limitations = ["Свободная формулировка 1", "Свободная формулировка 2"]
    codex_home = tmp_path / "codex-home"
    workdir = tmp_path / "empty-workdir"
    codex_home.mkdir()
    workdir.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"test")
    settings = CodexExecSettings(codex_home=codex_home, workdir=workdir, executable=executable)
    calls = 0

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        output_path = Path(command[command.index("--output-last-message") + 1])
        value = generated.model_dump(mode="json")
        value.pop("snapshot_id", None)
        output_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout='{"type":"thread.completed"}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CodexExecProvider(settings).generate("snapshot_normalized", facts, packets, paid=False)
    assert calls == 1
    assert result.overview.evidence_ids
    assert "invented_overview_fact" not in result.overview.evidence_ids
    assert result.domains[0].evidence_ids
    assert "invented_domain_fact" not in result.domains[0].evidence_ids
    assert result.questions[0].evidence_ids
    assert "invented_question_fact" not in result.questions[0].evidence_ids
    assert tuple(result.global_limitations) == GLOBAL_LIMITATIONS

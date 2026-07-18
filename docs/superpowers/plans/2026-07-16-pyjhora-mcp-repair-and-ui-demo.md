# PyJHora MCP Repair and UI Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Устранить расхождение D1, стабилизировать путь Swiss Ephemeris, ввести единый структурированный формат ошибок и output-схемы всех 22 tools, затем объединить backend-контракт и детальные требования демонстрационного UI в одном Markdown-документе.

**Architecture:** Каноническим источником D1 остаётся PyJHora charts.rasi_chart. Все расчёты проходят через единый подготовительный слой, который проверяет эфемериды и возвращает структурированные ошибки. Зарегистрированные FastMCP tools сохраняют совместимый dict-результат, но получают TypedDict output annotations для подробного outputSchema. Веб-сервис остаётся frontend-demo: кнопки, состояния, раскрытия и placeholder-ответы проектируются независимо от настоящего orchestration backend.

**Tech Stack:** Python 3.11.15, PyJHora 4.7.0, pyswisseph 2.10.3.2, FastMCP 3.4.3, Pydantic 2, pytest, ruff, React, TypeScript, Vite.

## Global Constraints

- Не менять пользовательские незакоммиченные изменения в MCP и VedicWay за пределами файлов, перечисленных в задачах.
- Не использовать другие GitHub-репозитории как источник реализации; для PyJHora MCP использовать только активный checkout и его origin.
- Сохранять южноиндийскую South Indian grid и текущую структуру трёх вкладок.
- Не менять публичный UI на упоминание Hermes, MCP или внутренней реализации.
- Не использовать mocks в интеграционных тестах MCP.
- После каждого исправления выполнять целевой тест, затем полный pytest и статические проверки.

---

### Task 1: Add failing regression tests for the four reported defects

**Files:**
- Modify: C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\tests\conftest.py
- Create: C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\tests\test_regressions.py

**Interfaces:**
- Consumes: Existing sample birth fixtures and direct tool functions.
- Produces: Failing tests for D1 consistency, ephemeris preparation, error shape and FastMCP output schemas.

- [ ] **Step 1: Write the failing regression tests**

    from pathlib import Path

    import pytest

    from pyjhora_mcp.tools.horoscope import get_rasi_chart
    from pyjhora_mcp.tools.panchanga import get_panchanga, get_planet_positions
    from pyjhora_mcp.utils.converters import ensure_ephemeris_path

    def test_planet_positions_matches_canonical_rasi_chart(sample_birth_data):
        chart = get_rasi_chart(sample_birth_data)
        positions = get_planet_positions(sample_birth_data)
        chart_by_name = {
            item["planet"]: item
            for item in chart["planets"]
            if item["planet"] in positions["planets"]
        }
        for name, position in positions["planets"].items():
            assert position["rasi"] == chart_by_name[name]["rasi"]
            assert position["total_longitude"] == pytest.approx(
                chart_by_name[name]["total_longitude"], abs=0.0001
            )

    def test_ephemeris_path_is_explicit_and_contains_required_file():
        path = Path(ensure_ephemeris_path())
        assert path.is_dir()
        assert (path / "seplm48.se1").is_file()

    def test_panchanga_errors_are_structured(sample_birth_data):
        result = get_panchanga(sample_birth_data)
        for value in result.values():
            if isinstance(value, dict) and "error" in value:
                assert isinstance(value["error"], dict)
                assert {"code", "message", "type"} <= value["error"].keys()

    @pytest.mark.asyncio
    async def test_registered_tools_expose_detailed_output_schemas():
        from pyjhora_mcp.server import mcp

        tools = await mcp.list_tools()
        assert len(tools) == 22
        assert all(tool.output_schema.get("properties") for tool in tools)

- [ ] **Step 2: Run the regression tests and confirm the expected failures**

    .venv311\Scripts\python.exe -m pytest tests/test_regressions.py -q

Expected: D1 consistency fails because get_planet_positions uses drik.sidereal_longitude with local JD; ephemeris preparation fails because ensure_ephemeris_path does not exist; structured errors fail because existing fields contain strings; output schema fails because tools currently annotate dict[str, Any].

### Task 2: Centralize ephemeris setup and structured errors

**Files:**
- Modify: C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\src\pyjhora_mcp\utils\converters.py
- Modify: all seven files under C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\src\pyjhora_mcp\tools

**Interfaces:**
- Consumes: PyJHora const._EPHIMERIDE_DATA_PATH and existing exception handling.
- Produces: ensure_ephemeris_path() -> str and error_payload(exc, code, recoverable) -> dict[str, object].

- [ ] **Step 1: Implement the preparation helpers**

    def ensure_ephemeris_path() -> str:
        from pathlib import Path
        import swisseph as swe
        from jhora import const

        candidates = (
            Path(const._EPHIMERIDE_DATA_PATH).resolve(),
            Path(const._ephe_path).resolve(),
        )
        path = next((candidate for candidate in candidates if candidate.is_dir()), None)
        if path is None:
            raise RuntimeError("Swiss Ephemeris directory is not available")
        required = path / "seplm48.se1"
        if not required.is_file():
            raise RuntimeError(f"Required Swiss Ephemeris file is missing: {required.name}")
        swe.set_ephe_path(path.as_posix())
        return str(path)

    def error_payload(exc: Exception, code: str = "CALCULATION_ERROR", recoverable: bool = True) -> dict:
        return {
            "code": code,
            "type": type(exc).__name__,
            "message": str(exc),
            "recoverable": recoverable,
        }

Call ensure_ephemeris_path() from to_julian_day() and to_place() so both date/place-only and birth-data tools prepare the same runtime. Replace every internal string error with error_payload(exc), while preserving the existing field name.

- [ ] **Step 2: Run the focused tests**

    .venv311\Scripts\python.exe -m pytest tests/test_regressions.py::test_ephemeris_path_is_explicit_and_contains_required_file tests/test_regressions.py::test_panchanga_errors_are_structured -q

Expected: both tests pass.

### Task 3: Make get_planet_positions use the canonical D1 source

**Files:**
- Modify: C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\src\pyjhora_mcp\tools\panchanga.py
- Modify: C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\tests\test_regressions.py

**Interfaces:**
- Consumes: get_rasi_chart-compatible charts.rasi_chart output.
- Produces: get_planet_positions() with nine classical planet entries matching get_rasi_chart total_longitude, rasi, nakshatra and pada.

- [ ] **Step 1: Replace the incorrect sidereal_longitude loop**

Use charts.rasi_chart(jd, place) and filter by classical planet IDs 0 through 8. Convert every entry with the same converter helper and return the existing dictionary shape. Keep ascendant from drik.ascendant so the output remains backward compatible, but add nakshatra and pada using the same longitude helper used by D1.

- [ ] **Step 2: Run the D1 regression test**

    .venv311\Scripts\python.exe -m pytest tests/test_regressions.py::test_planet_positions_matches_canonical_rasi_chart -q

Expected: PASS, with no planet mismatch.

### Task 4: Add strict output models without changing direct dict callers

**Files:**
- Modify: C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\src\pyjhora_mcp\models\schemas.py
- Modify: all seven files under C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\src\pyjhora_mcp\tools
- Modify: C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\tests\test_regressions.py

**Interfaces:**
- Consumes: Current dict-shaped tool results.
- Produces: typing_extensions.TypedDict annotations with explicit top-level properties for all 22 tools and nested typed fields for chart, panchanga, dasha, yoga, compatibility and strength data.

- [ ] **Step 1: Define reusable typed output fields**

Define ErrorValue, PositionOutput, AscendantOutput, PeriodOutput, PanchangaOutput, RasiChartOutput, DivisionalChartOutput, DashaOutput, YogaOutput, DoshaOutput, StrengthOutput and tool-specific top-level TypedDicts in schemas.py. Use NotRequired for partial fields and dict[str, Any] only for raw third-party records whose keys are not controlled by PyJHora.

- [ ] **Step 2: Change every tool annotation to its named output type**

Keep the function bodies returning dicts. Annotate each of the 22 tools with its corresponding TypedDict so FastMCP generates a detailed output schema while direct Python tests retain result["field"] behavior.

- [ ] **Step 3: Verify tool registration**

    .venv311\Scripts\python.exe -m pytest tests/test_regressions.py::test_registered_tools_expose_detailed_output_schemas -q

Expected: PASS, 22 tools with non-empty output schema properties.

### Task 5: Expand regression coverage and update the single UI specification

**Files:**
- Modify: D:\CODEX_WORK\VedicWay\docs\PYJHORA_MCP_NATAL_CHART_UI_REQUIREMENTS_RU.md
- Modify: C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\tests\test_regressions.py

**Interfaces:**
- Consumes: Fixed MCP contract and current VedicWay ResultsShowcase component.
- Produces: One document containing the repaired backend contract and exact landing-page demo UI behavior.

- [ ] **Step 1: Update the contract section**

Remove the old P0 status wording. Document get_rasi_chart and get_planet_positions as one canonical D1 source, the explicit ephemeris preparation, structured errors, named output schemas and the current verified behavior.

- [ ] **Step 2: Add the second landing-page block UI specification**

Document the visual frame, sidebar, tab states, click targets, keyboard behavior, responsive behavior and placeholder strategy. The sidebar has three buttons: Натальная карта, Объяснение, Вопросы к себе. The chart view has a South Indian grid, planet table, D1–D60 selector and expandable data sections. The explanation view has summary cards, filters, expandable evidence drawers and a fixed action for returning to the chart. The questions view has prompt cards, a question composer, chips for themes, answer loading skeletons, empty state and source drawer. All data may be demo fixtures or placeholders in the landing-page version.

- [ ] **Step 3: Add implementation-ready interaction requirements**

Specify exact button labels, active, hover, focus, disabled, loading and error states, aria roles, tab navigation, chart zoom/reset controls, disclosure behavior, responsive breakpoints and visual acceptance criteria. Explicitly separate the demo interaction contract from future backend orchestration.

### Task 6: Verify the complete repair and UI contract

**Files:**
- No new files.

- [ ] **Step 1: Run MCP tests and static checks**

    Set-Location C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp
    .venv311\Scripts\python.exe -m pytest tests -q
    ruff check --no-cache src tests
    .venv311\Scripts\python.exe -m compileall -q src

Expected: pytest has zero failures, ruff reports All checks passed, compileall exits 0.

- [ ] **Step 2: Run the VedicWay frontend tests and build**

    Set-Location D:\CODEX_WORK\VedicWay
    npm test -- --run
    npm run build

Expected: all Vitest tests pass and Vite production build exits 0.

- [ ] **Step 3: Inspect the final diff**

    git -C C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp diff --check
    git -C D:\CODEX_WORK\VedicWay diff --check

Expected: no whitespace errors. Existing unrelated user changes remain untouched.

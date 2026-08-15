from __future__ import annotations

import hashlib
import html
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .errors import DomainError
from .schemas import (
    BirthInput,
    ChartSnapshot,
    InterpretationBundle,
    PdfRenderPreferences,
    RectificationResult,
)

SOUTH_INDIAN_POSITIONS = {
    0: (0, 0), 1: (1, 0), 2: (2, 0), 3: (3, 0),
    4: (3, 1), 5: (3, 2), 6: (3, 3), 7: (2, 3),
    8: (1, 3), 9: (0, 3), 10: (0, 2), 11: (0, 1),
}


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _degree(value: object) -> str:
    try:
        total_minutes = min(29 * 60 + 59, max(0, int(float(value) * 60)))
    except (TypeError, ValueError):
        return ""
    return f"{total_minutes // 60}°{total_minutes % 60:02d}′"


def south_indian_svg(
    cells: list[dict[str, Any]],
    preferences: PdfRenderPreferences | None = None,
    width: int = 720,
) -> str:
    """Print-friendly South Indian chart based on the same normalised cells as the UI."""
    preferences = preferences or PdfRenderPreferences()
    cell = width / 4
    cells_by_index = {int(item["sign_index"]): item for item in cells}
    fragments = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {width}" role="img" aria-label="Южноиндийская {_escape(preferences.varga)}-карта">',
        '<rect width="100%" height="100%" fill="#fffdf9"/>',
        '<g fill="none" stroke="#5d3421" stroke-width="2">',
    ]
    for line in range(5):
        point = line * cell
        fragments.append(f'<path d="M {point} 0 V {width} M 0 {point} H {width}"/>')
    fragments.append('</g>')
    for sign_index, (column, row) in SOUTH_INDIAN_POSITIONS.items():
        chart_cell = cells_by_index.get(sign_index, {})
        x = column * cell
        y = row * cell
        sign = _escape(chart_cell.get("sign_label", ""))
        lagna = ' Лагна' if chart_cell.get("is_lagna") else ''
        planet_labels = []
        for item in chart_cell.get("planets", []):
            label = item.get("short_label", "") if preferences.mode == "plain" else item.get("label", "")
            if preferences.mode == "expert":
                label = f"{label} {_degree(item.get('longitude_in_sign'))}".strip()
            if item.get("retrograde"):
                label = f"{label} R"
            planet_labels.append(_escape(label))
        planets = " · ".join(planet_labels)
        fragments.extend(
            [
                f'<text x="{x + 18}" y="{y + 31}" font-family="Arial, sans-serif" font-size="18" fill="#7d472b">{sign}{lagna}</text>',
                f'<text x="{x + 18}" y="{y + 63}" font-family="Arial, sans-serif" font-size="{15 if preferences.mode == "expert" else 25}" font-weight="600" fill="#2d1a13">{planets}</text>',
            ]
        )
    fragments.extend(
        [
            f'<rect x="{cell}" y="{cell}" width="{cell * 2}" height="{cell * 2}" fill="#fffaf4" stroke="#5d3421" stroke-width="2"/>',
            f'<text x="{width / 2}" y="{width / 2 - 12}" text-anchor="middle" font-family="Georgia, serif" font-size="27" fill="#2d1a13">{_escape(preferences.varga)} · Раши</text>',
            f'<text x="{width / 2}" y="{width / 2 + 24}" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" fill="#6c5a50">Южноиндийская фиксированная сетка знаков</text>',
            '</svg>',
        ]
    )
    return "".join(fragments)


def _selected_chart_cells(snapshot: ChartSnapshot, preferences: PdfRenderPreferences) -> list[dict[str, Any]]:
    if preferences.varga == "D1":
        return [cell.model_dump(mode="json") for cell in snapshot.cells]
    section = snapshot.sections.get(preferences.varga)
    data = section.get("data") if isinstance(section, dict) else None
    cells = data.get("cells") if isinstance(data, dict) else None
    if not isinstance(cells, list) or not cells:
        raise DomainError("PDF_VARGA_UNAVAILABLE", f"Карта {preferences.varga} ещё не готова", recoverable=True)
    return cells


def report_html(
    snapshot: ChartSnapshot,
    bundle: InterpretationBundle,
    preferences: PdfRenderPreferences | None = None,
) -> str:
    preferences = preferences or PdfRenderPreferences()
    cells = _selected_chart_cells(snapshot, preferences)
    chart_svg = south_indian_svg(cells, preferences)
    birth = snapshot.birth
    sections = []
    for domain in bundle.domains:
        paragraphs = "".join(f"<p>{_escape(paragraph)}</p>" for paragraph in domain.paragraphs)
        manifestations = "".join(f"<li>{_escape(item)}</li>" for item in domain.manifestations)
        sections.append(
            "<section class=\"domain\">"
            f"<h2>{_escape(domain.section_label)}</h2>"
            f"<h3>{_escape(domain.title)}</h3>"
            f"<p class=\"summary\">{_escape(domain.summary)}</p>"
            f"{paragraphs}"
            f"<ul>{manifestations}</ul>"
            "</section>"
        )
    questions = "".join(f"<li>{_escape(question.text)}</li>" for question in bundle.questions)
    limitations = "".join(f"<li>{_escape(item)}</li>" for item in bundle.global_limitations)
    synthesis_paragraphs = "".join(f"<p>{_escape(paragraph)}</p>" for paragraph in bundle.synthesis)
    synthesis_section = (
        f'<section class="synthesis"><h2>Общий синтез</h2>{synthesis_paragraphs}</section>'
        if synthesis_paragraphs
        else ""
    )
    mode_label = "Понятный" if preferences.mode == "plain" else "Профессиональный"
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    @page {{ size: A4; margin: 14mm; }}
    * {{ box-sizing: border-box; }}
    body {{ color: #2d1a13; font: 11pt/1.55 Arial, sans-serif; margin: 0; }}
    h1, h2, h3 {{ font-family: Georgia, serif; color: #3b2116; }}
    h1 {{ font-size: 27pt; margin: 0 0 8mm; }}
    h2 {{ border-top: 1px solid #c59a75; padding-top: 7mm; font-size: 20pt; margin: 12mm 0 2mm; }}
    h3 {{ font-size: 14pt; margin: 0 0 3mm; }}
    .meta {{ color: #6c5a50; margin-bottom: 8mm; }}
    .render-settings {{ display: flex; gap: 5mm; margin: -4mm 0 7mm; padding: 3mm 4mm; border: 1px solid #dec7b3; background: #fffaf4; color: #6c5a50; font-size: 9pt; }}
    .chart {{ max-width: 150mm; margin: 0 auto 8mm; }}
    .summary {{ font-size: 12pt; }}
    .domain {{ break-inside: avoid; }}
    .notice {{ background: #fbf4eb; border-left: 3px solid #bb6734; padding: 4mm 5mm; margin-top: 10mm; }}
    li {{ margin-bottom: 2mm; }}
  </style>
</head>
<body>
  <h1>Натальная карта · {_escape(preferences.varga)}</h1>
  <p class="meta">{_escape(birth.get('local_date'))}, {_escape(birth.get('local_time'))} · {_escape(birth.get('place'))} · Лахири</p>
  <div class="render-settings"><span><strong>Карта:</strong> {_escape(preferences.varga)}</span><span><strong>Режим:</strong> {_escape(mode_label)}</span><span><strong>Стиль:</strong> Южноиндийский</span></div>
  <div class="chart">{chart_svg}</div>
  <h2>Первое чтение</h2>
  <p class="summary">{_escape(bundle.overview.summary)}</p>
  {synthesis_section}
  {''.join(sections)}
  <section><h2>Вопросы к себе</h2><ol>{questions}</ol></section>
  <section class="notice"><strong>Границы материала</strong><ul>{limitations}</ul></section>
</body>
</html>"""


def rectification_report_html(birth: BirthInput, result: RectificationResult) -> str:
    confidence_labels = {"low": "предварительная", "medium": "средняя", "high": "высокая"}
    alternatives = "".join(
        "<li>"
        f"<strong>{_escape(item.get('time', ''))}</strong> · "
        f"лагна {_escape(item.get('lagna', ''))} · "
        f"совпадение {_escape(item.get('score_percent', ''))}%"
        "</li>"
        for item in result.alternatives
    )
    alternatives_section = (
        f"<section><h2>Ближайшие альтернативы</h2><ol>{alternatives}</ol></section>"
        if alternatives
        else ""
    )
    birth_date = birth.local_datetime.strftime("%d.%m.%Y")
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: A4; margin: 16mm; }}
    * {{ box-sizing: border-box; }}
    body {{ color: #2d1a13; font: 11pt/1.55 Arial, sans-serif; margin: 0; }}
    h1, h2 {{ font-family: Georgia, serif; color: #3b2116; }}
    h1 {{ font-size: 25pt; margin: 0 0 4mm; }}
    h2 {{ border-top: 1px solid #c59a75; padding-top: 6mm; font-size: 17pt; margin: 10mm 0 3mm; }}
    .brand {{ color: #b05d32; font-size: 10pt; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
    .meta {{ color: #6c5a50; margin: 0 0 10mm; }}
    .result {{ background: #fbf4eb; border: 1px solid #dec7b3; padding: 8mm; text-align: center; }}
    .time {{ color: #b05d32; font: 700 42pt/1 Georgia, serif; margin: 3mm 0; }}
    .metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 4mm; margin-top: 7mm; }}
    .metric {{ border: 1px solid #dec7b3; padding: 4mm; }}
    .metric strong {{ display: block; font-size: 17pt; }}
    .metric span {{ color: #6c5a50; font-size: 9pt; }}
    .notice {{ background: #fbf4eb; border-left: 3px solid #bb6734; padding: 4mm 5mm; margin-top: 10mm; }}
    li {{ margin-bottom: 2mm; }}
  </style>
</head>
<body>
  <p class="brand">VedicWay</p>
  <h1>Отчёт по времени рождения</h1>
  <p class="meta">{_escape(birth_date)} · {_escape(birth.place.display_name)}</p>
  <section class="result">
    <span>Наиболее согласованное время</span>
    <div class="time">{_escape(result.selected_time)}</div>
    <p>Диапазон уверенности ±{_escape(result.uncertainty_minutes)} минут · лагна {_escape(result.lagna)}</p>
  </section>
  <div class="metrics">
    <div class="metric"><strong>{_escape(result.score_percent)}%</strong><span>совпадение правил</span></div>
    <div class="metric"><strong>{_escape(result.candidate_count_scored)}</strong><span>вариантов проверено</span></div>
    <div class="metric"><strong>{_escape(confidence_labels[result.confidence])}</strong><span>оценка уверенности</span></div>
  </div>
  {alternatives_section}
  <section class="notice"><strong>Границы результата</strong><p>{_escape(result.disclaimer)}</p></section>
</body>
</html>"""


def _render_html_pdf(source: str, output: Path) -> bytes:
    script = Path(__file__).resolve().parents[2] / "scripts" / "render_pdf.mjs"
    if not script.exists():
        raise DomainError("PDF_RENDER_FAILED", "Не найден безопасный рендерер PDF", recoverable=False)
    with tempfile.TemporaryDirectory(prefix="vedicway-pdf-") as temporary:
        html_path = Path(temporary) / "report.html"
        html_path.write_text(source, encoding="utf-8")
        completed = subprocess.run(
            ["node", str(script), str(html_path), str(output)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            shell=False,
            cwd=script.parents[2],
            env=os.environ.copy(),
            check=False,
        )
    if completed.returncode != 0 or not output.exists():
        raise DomainError("PDF_RENDER_FAILED", "Не удалось собрать PDF", recoverable=True)
    return output.read_bytes()


def rectification_report_pdf(birth: BirthInput, result: RectificationResult) -> bytes:
    with tempfile.TemporaryDirectory(prefix="vedicway-rectification-pdf-") as temporary:
        output = Path(temporary) / "vedicway-birth-time-report.pdf"
        return _render_html_pdf(rectification_report_html(birth, result), output)


class PdfRenderer:
    def __init__(self, reports_dir: str | Path) -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def render(
        self,
        chart_id: str,
        snapshot: ChartSnapshot,
        bundle: InterpretationBundle,
        preferences: PdfRenderPreferences,
        render_request_id: str,
    ) -> dict[str, Any]:
        output = self.reports_dir / f"{chart_id}_{render_request_id}_{secrets.token_urlsafe(8)}.pdf"
        payload = _render_html_pdf(report_html(snapshot, bundle, preferences), output)
        return {
            "path": str(output),
            "checksum": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            "size_bytes": len(payload),
            "pages": max(1, payload.count(b"/Type /Page")),
        }

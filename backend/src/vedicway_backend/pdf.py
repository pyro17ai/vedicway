from __future__ import annotations

import hashlib
import html
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .errors import DomainError
from .schemas import ChartSnapshot, InterpretationBundle

SOUTH_INDIAN_POSITIONS = {
    0: (0, 0), 1: (1, 0), 2: (2, 0), 3: (3, 0),
    4: (3, 1), 5: (3, 2), 6: (3, 3), 7: (2, 3),
    8: (1, 3), 9: (0, 3), 10: (0, 2), 11: (0, 1),
}


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def south_indian_svg(cells: list[dict[str, Any]], width: int = 720) -> str:
    """Print-friendly South Indian chart based on the same normalised cells as the UI."""
    cell = width / 4
    cells_by_index = {int(item["sign_index"]): item for item in cells}
    fragments = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {width}" role="img" aria-label="Южноиндийская D1-карта">',
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
        planets = " · ".join(_escape(item.get("short_label", "")) for item in chart_cell.get("planets", []))
        fragments.extend(
            [
                f'<text x="{x + 18}" y="{y + 31}" font-family="Arial, sans-serif" font-size="18" fill="#7d472b">{sign}{lagna}</text>',
                f'<text x="{x + 18}" y="{y + 63}" font-family="Arial, sans-serif" font-size="25" font-weight="600" fill="#2d1a13">{planets}</text>',
            ]
        )
    fragments.extend(
        [
            f'<rect x="{cell}" y="{cell}" width="{cell * 2}" height="{cell * 2}" fill="#fffaf4" stroke="#5d3421" stroke-width="2"/>',
            f'<text x="{width / 2}" y="{width / 2 - 12}" text-anchor="middle" font-family="Georgia, serif" font-size="27" fill="#2d1a13">D1 · Раши</text>',
            f'<text x="{width / 2}" y="{width / 2 + 24}" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" fill="#6c5a50">Южноиндийская фиксированная сетка знаков</text>',
            '</svg>',
        ]
    )
    return "".join(fragments)


def report_html(snapshot: ChartSnapshot, bundle: InterpretationBundle) -> str:
    cells = [cell.model_dump(mode="json") for cell in snapshot.cells]
    chart_svg = south_indian_svg(cells)
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
    .chart {{ max-width: 150mm; margin: 0 auto 8mm; }}
    .summary {{ font-size: 12pt; }}
    .domain {{ break-inside: avoid; }}
    .notice {{ background: #fbf4eb; border-left: 3px solid #bb6734; padding: 4mm 5mm; margin-top: 10mm; }}
    li {{ margin-bottom: 2mm; }}
  </style>
</head>
<body>
  <h1>Натальная карта</h1>
  <p class="meta">{_escape(birth.get('local_date'))}, {_escape(birth.get('local_time'))} · {_escape(birth.get('place'))} · Лахири</p>
  <div class="chart">{chart_svg}</div>
  <h2>Первое чтение</h2>
  <p class="summary">{_escape(bundle.overview.summary)}</p>
  {''.join(sections)}
  <section><h2>Вопросы к себе</h2><ol>{questions}</ol></section>
  <section class="notice"><strong>Границы материала</strong><ul>{limitations}</ul></section>
</body>
</html>"""


class PdfRenderer:
    def __init__(self, reports_dir: str | Path) -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.script = Path(__file__).resolve().parents[2] / "scripts" / "render_pdf.mjs"

    def render(self, chart_id: str, snapshot: ChartSnapshot, bundle: InterpretationBundle) -> dict[str, Any]:
        if not self.script.exists():
            raise DomainError("PDF_RENDER_FAILED", "Не найден безопасный рендерер PDF", recoverable=False)
        output = self.reports_dir / f"{chart_id}_{secrets.token_urlsafe(12)}.pdf"
        with tempfile.TemporaryDirectory(prefix="vedicway-pdf-") as temporary:
            html_path = Path(temporary) / "report.html"
            html_path.write_text(report_html(snapshot, bundle), encoding="utf-8")
            completed = subprocess.run(
                ["node", str(self.script), str(html_path), str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
                shell=False,
                cwd=self.script.parents[2],
                env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")},
                check=False,
            )
        if completed.returncode != 0 or not output.exists():
            raise DomainError("PDF_RENDER_FAILED", "Не удалось собрать PDF", recoverable=True)
        payload = output.read_bytes()
        return {
            "path": str(output),
            "checksum": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            "size_bytes": len(payload),
            "pages": max(1, payload.count(b"/Type /Page")),
        }

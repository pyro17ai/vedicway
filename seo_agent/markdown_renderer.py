from __future__ import annotations

import html
import re
from urllib.parse import urlsplit

LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
MEDIA_MARKER = re.compile(r"\{\{media:body-[1-9][0-9]*\}\}")


def _safe_href(value: str) -> bool:
    if value.startswith("/") and not value.startswith("//"):
        return True
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _inline(value: str) -> str:
    rendered: list[str] = []
    offset = 0
    for match in LINK_PATTERN.finditer(value):
        rendered.append(html.escape(value[offset : match.start()]))
        label, href = match.groups()
        escaped_label = html.escape(label)
        if _safe_href(href):
            rendered.append(
                f'<a href="{html.escape(href, quote=True)}">{escaped_label}</a>'
            )
        else:
            rendered.append(escaped_label)
        offset = match.end()
    rendered.append(html.escape(value[offset:]))
    return "".join(rendered)


def render_markdown(value: str) -> str:
    lines = str(value).strip().splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            output.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
            list_items.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue
        if MEDIA_MARKER.fullmatch(line):
            flush_paragraph()
            flush_list()
            output.append(line)
            continue
        heading = re.fullmatch(r"(##|###)\s+(.+)", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = 2 if heading.group(1) == "##" else 3
            output.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue
        if line.startswith("- "):
            flush_paragraph()
            list_items.append(_inline(line[2:].strip()))
            continue
        flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    return "".join(output)

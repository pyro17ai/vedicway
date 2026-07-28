from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .db import AgentLedger, LedgerError


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def generate_cover(title: str, category: str, output: Path) -> dict[str, object]:
    ledger = AgentLedger()
    target = output.expanduser().resolve()
    try:
        target.relative_to(ledger.data_dir)
    except ValueError as exc:
        raise LedgerError("Generated media must stay inside VEDICWAY_SEO_DATA_DIR") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1200, 630), (245, 238, 225))
    draw = ImageDraw.Draw(image)
    draw.ellipse((760, -180, 1260, 320), outline=(112, 70, 46), width=3)
    draw.ellipse((840, -100, 1180, 240), outline=(178, 133, 88), width=2)
    draw.line((72, 86, 1128, 86), fill=(178, 133, 88), width=2)
    draw.text((72, 118), category.upper(), font=_font(25, bold=True), fill=(112, 70, 46))
    lines = textwrap.wrap(title, width=31)[:4]
    y = 190
    for line in lines:
        draw.text((72, y), line, font=_font(52, bold=True), fill=(45, 31, 23))
        y += 66
    draw.text((72, 550), "VEDICWAY  •  ГИД ПО АСТРОЛОГИИ", font=_font(23, bold=True), fill=(112, 70, 46))
    image.save(target, "WEBP", quality=91, method=6)
    return {
        "path": str(target),
        "width": image.width,
        "height": image.height,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "source_kind": "generated",
        "license_note": "Generated locally by the VedicWay article-media skill",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a deterministic VedicWay article cover")
    parser.add_argument("--title", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(generate_cover(args.title, args.category, args.output), ensure_ascii=False, sort_keys=True))
        return 0
    except (LedgerError, OSError, ValueError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

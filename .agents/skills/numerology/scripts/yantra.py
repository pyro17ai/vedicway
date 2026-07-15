#!/usr/bin/env python3
"""
yantra.py — Generate a numeric (magic-square) yantra and an optional SVG image.

Pure Python standard library only — no ephemeris, no network, no dependencies.

Three kinds of yantra, all built on the same magic-square engine (every row,
column and main diagonal adds up to the same total — the "magic sum"):

  1. Personalised birth yantra (4x4)  — from a date of birth. The top row holds
     DD, MM, the century-part and the year-part of the birth year, and the whole
     square is magic for the total DD+MM+CC+YY. This is the classic "date of
     birth" yantra (the same construction as Ramanujan's birthday square).
  2. Navagraha planetary yantras (3x3) — one per graha, generated from the
     classical Lo Shu square by the constant-offset method (Surya = the Lo Shu
     square itself, magic sum 15; each later graha shifts the centre up by one).
  3. Custom target yantra (3x3)        — a 3x3 magic square for any chosen total
     (e.g. a lucky number). A 3x3 magic sum is always 3x its centre, so the
     target must be a multiple of 3.

Usage:
    python yantra.py --date 1990-08-15 [--svg out.svg] [--json]
    python yantra.py --planet surya   [--svg out.svg] [--json]
    python yantra.py --planet all     [--svg out_dir_prefix] [--json]
    python yantra.py --target 24      [--svg out.svg] [--json]

For cultural/educational/devotional use only. Not predictive, not a substitute
for medical, financial, legal, or other professional advice.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import sys

DISCLAIMER = ("For cultural/educational/devotional use only. Not predictive, and "
              "not a substitute for medical, financial, or legal advice.")

# Classical Lo Shu / base 3x3 magic square (magic sum 15, centre 5).
BASE_3X3 = [[4, 9, 2], [3, 5, 7], [8, 1, 6]]

# Navagraha (nine grahas). magic_sum anchors Surya at the Lo Shu 15; each later
# graha lifts the centre by one (offset construction). day = ruling weekday;
# bija = traditional seed (beej) mantra; helps = what the graha governs.
PLANETS = {
    "surya":   {"en": "Sun",     "magic_sum": 15, "day": "Sunday",
                "bija": "Om Hraam Hreem Hraum Sah Suryaya Namah",
                "helps": "vitality, confidence, authority, health, the father, government favour"},
    "chandra": {"en": "Moon",    "magic_sum": 18, "day": "Monday",
                "bija": "Om Shraam Shreem Shraum Sah Chandraya Namah",
                "helps": "peace of mind, emotions, the mother, sleep, public goodwill"},
    "mangal":  {"en": "Mars",    "magic_sum": 21, "day": "Tuesday",
                "bija": "Om Kraam Kreem Kraum Sah Bhaumaya Namah",
                "helps": "courage, energy, land/property, drive, protection from disputes"},
    "budh":    {"en": "Mercury", "magic_sum": 24, "day": "Wednesday",
                "bija": "Om Braam Breem Braum Sah Budhaya Namah",
                "helps": "intellect, speech, study, trade, communication, nerves"},
    "guru":    {"en": "Jupiter", "magic_sum": 27, "day": "Thursday",
                "bija": "Om Graam Greem Graum Sah Gurave Namah",
                "helps": "wisdom, wealth, children, teachers, dharma, marriage (for women)"},
    "shukra":  {"en": "Venus",   "magic_sum": 30, "day": "Friday",
                "bija": "Om Draam Dreem Draum Sah Shukraya Namah",
                "helps": "love, marriage, comforts, art, vehicles, prosperity"},
    "shani":   {"en": "Saturn",  "magic_sum": 33, "day": "Saturday",
                "bija": "Om Praam Preem Praum Sah Shanaischaraya Namah",
                "helps": "discipline, longevity, relief from delays/obstacles, labour, justice"},
    "rahu":    {"en": "Rahu",    "magic_sum": 36, "day": "Saturday",
                "bija": "Om Bhraam Bhreem Bhraum Sah Rahave Namah",
                "helps": "sudden gains, foreign matters, calming anxiety and confusion"},
    "ketu":    {"en": "Ketu",    "magic_sum": 39, "day": "Tuesday",
                "bija": "Om Sraam Sreem Sraum Sah Ketave Namah",
                "helps": "detachment, spirituality, moksha, relief from hidden troubles"},
}


# --- Magic-square engine ---------------------------------------------------

def make_3x3(magic_sum: int):
    """3x3 magic square for the given magic sum (must be a multiple of 3)."""
    if magic_sum % 3 != 0:
        raise ValueError(f"a 3x3 magic sum must be a multiple of 3 (got {magic_sum}); "
                         "its centre is always magic_sum / 3")
    k = (magic_sum - 15) // 3
    return [[BASE_3X3[r][c] + k for c in range(3)] for r in range(3)]


def make_birthday_4x4(year: int, month: int, day: int):
    """4x4 'date of birth' magic square. Top row = day, month, century-part,
    year-part. Every row, column and main diagonal sums to DD+MM+CC+YY.

    Construction is the classic parametric template (the same family as
    Ramanujan's birthday square); cells may occasionally be <= 0 for very small
    months, which is mathematically fine — the square stays magic.
    """
    a, b = day, month
    c, d = year // 100, year % 100   # century-part, year-part
    return [
        [a,     b,     c,     d],
        [d + 1, c - 1, b - 3, a + 3],
        [b - 2, a + 2, d + 2, c - 2],
        [c + 1, d - 1, a + 1, b - 1],
    ]


def line_sums(square):
    """All row, column and diagonal sums of a square matrix."""
    n = len(square)
    rows = [sum(square[r]) for r in range(n)]
    cols = [sum(square[r][c] for r in range(n)) for c in range(n)]
    diag = [sum(square[i][i] for i in range(n)),
            sum(square[i][n - 1 - i] for i in range(n))]
    return rows + cols + diag


def is_magic(square) -> bool:
    sums = line_sums(square)
    return len(set(sums)) == 1


# --- Numerology helpers (self-contained) -----------------------------------

def reduce_to_single(n: int) -> int:
    n = abs(int(n))
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n


def core_numbers(year: int, month: int, day: int) -> dict:
    moolank = reduce_to_single(day)
    bhagyank = reduce_to_single(sum(int(c) for c in f"{year:04d}{month:02d}{day:02d}"))
    return {"moolank": moolank, "bhagyank": bhagyank}


# --- SVG rendering ----------------------------------------------------------

def render_svg(square, title: str, subtitle: str = "", footer: str = "") -> str:
    """A decorative yantra SVG: bhupura (gated outer square), a lotus-petal ring,
    and the magic-square grid of numbers at the centre. Saffron/maroon palette."""
    W, H = 640, 760
    cx, cy = W / 2, 360.0            # centre of the mandala
    R_out = 250.0                    # outer circle radius
    R_pet = 200.0                    # petal base ring
    grid = 240.0                     # side of the number grid
    n = len(square)
    cell = grid / n

    cream, maroon, saffron, gold, ink = (
        "#fff8e7", "#7a1f1f", "#e07b00", "#caa12f", "#3a2410")

    out = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
               f'viewBox="0 0 {W} {H}">')
    out.append(f'<rect width="{W}" height="{H}" fill="{cream}"/>')

    # Title.
    out.append(f'<text x="{cx}" y="58" text-anchor="middle" font-family="Georgia,serif" '
               f'font-size="30" font-weight="bold" fill="{maroon}">{_esc(title)}</text>')
    if subtitle:
        out.append(f'<text x="{cx}" y="88" text-anchor="middle" font-family="Georgia,serif" '
                   f'font-size="16" fill="{saffron}">{_esc(subtitle)}</text>')

    # Bhupura — gated outer square (the earth-square enclosure).
    s = R_out + 28
    g = 26  # gate depth
    x0, y0, x1, y1 = cx - s, cy - s, cx + s, cy + s
    mx, my = cx, cy
    path = (f'M {x0} {y0} L {x1} {y0} L {x1} {y1} L {x0} {y1} Z')
    out.append(f'<path d="{path}" fill="none" stroke="{maroon}" stroke-width="6"/>')
    inset = 14
    out.append(f'<rect x="{x0 + inset}" y="{y0 + inset}" width="{2 * s - 2 * inset}" '
               f'height="{2 * s - 2 * inset}" fill="none" stroke="{gold}" stroke-width="2"/>')
    # Four T-gates.
    for (gx, gy, w, h) in [
        (mx - g, y0 - g, 2 * g, g),       # top
        (mx - g, y1, 2 * g, g),           # bottom
        (x0 - g, my - g, g, 2 * g),       # left
        (x1, my - g, g, 2 * g),           # right
    ]:
        out.append(f'<rect x="{gx}" y="{gy}" width="{w}" height="{h}" '
                   f'fill="none" stroke="{maroon}" stroke-width="6"/>')

    # Outer circles.
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{R_out}" fill="none" stroke="{maroon}" stroke-width="4"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{R_pet}" fill="none" stroke="{gold}" stroke-width="2"/>')

    # Lotus-petal ring (16 petals as smooth quadratic curves).
    petals = 16
    r_in, r_tip = R_pet, R_out - 6
    for i in range(petals):
        a0 = 2 * math.pi * i / petals
        a1 = 2 * math.pi * (i + 1) / petals
        am = (a0 + a1) / 2
        x_a = cx + r_in * math.cos(a0)
        y_a = cy + r_in * math.sin(a0)
        x_b = cx + r_in * math.cos(a1)
        y_b = cy + r_in * math.sin(a1)
        x_t = cx + r_tip * math.cos(am)
        y_t = cy + r_tip * math.sin(am)
        out.append(f'<path d="M {x_a:.1f} {y_a:.1f} Q {x_t:.1f} {y_t:.1f} {x_b:.1f} {y_b:.1f}" '
                   f'fill="none" stroke="{saffron}" stroke-width="2"/>')

    # Inner circle behind the grid.
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{grid / 2 + 18}" fill="{cream}" '
               f'stroke="{maroon}" stroke-width="3"/>')

    # The number grid.
    gx0, gy0 = cx - grid / 2, cy - grid / 2
    out.append(f'<rect x="{gx0}" y="{gy0}" width="{grid}" height="{grid}" '
               f'fill="none" stroke="{maroon}" stroke-width="3"/>')
    for i in range(1, n):
        out.append(f'<line x1="{gx0 + i * cell}" y1="{gy0}" x2="{gx0 + i * cell}" '
                   f'y2="{gy0 + grid}" stroke="{gold}" stroke-width="1.5"/>')
        out.append(f'<line x1="{gx0}" y1="{gy0 + i * cell}" x2="{gx0 + grid}" '
                   f'y2="{gy0 + i * cell}" stroke="{gold}" stroke-width="1.5"/>')
    fsize = 34 if n == 3 else 26
    for r in range(n):
        for c in range(n):
            tx = gx0 + c * cell + cell / 2
            ty = gy0 + r * cell + cell / 2 + fsize / 3
            out.append(f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" '
                       f'font-family="Georgia,serif" font-size="{fsize}" '
                       f'font-weight="bold" fill="{ink}">{square[r][c]}</text>')

    # Footer (mantra / magic sum).
    if footer:
        out.append(f'<text x="{cx}" y="{H - 36}" text-anchor="middle" '
                   f'font-family="Georgia,serif" font-size="17" fill="{maroon}">{_esc(footer)}</text>')
    out.append(f'<text x="{cx}" y="{H - 14}" text-anchor="middle" '
               f'font-family="Georgia,serif" font-size="11" fill="{saffron}">'
               f'For devotional / cultural use • not predictive</text>')
    out.append('</svg>')
    return "\n".join(out)


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# --- Text rendering ---------------------------------------------------------

def render_text(square, title: str, subtitle: str, footer: str) -> str:
    n = len(square)
    width = max(len(str(v)) for row in square for v in row) + 1
    sep = "  +" + "+".join("-" * (width + 1) for _ in range(n)) + "+"
    lines = ["=" * 50, f"  {title}"]
    if subtitle:
        lines.append(f"  {subtitle}")
    lines.append("=" * 50)
    lines.append(sep)
    for row in square:
        lines.append("  |" + "|".join(f" {v:>{width}}" for v in row) + "|")
        lines.append(sep)
    lines.append(f"  Magic sum (every row/column/diagonal): {sum(square[0])}")
    if footer:
        lines.append(f"  {footer}")
    lines.append("-" * 50)
    lines.append(f"  {DISCLAIMER}")
    lines.append("=" * 50)
    return "\n".join(lines)


# --- Builders ---------------------------------------------------------------

def build_birthday(date_str: str) -> dict:
    y, m, d = (int(x) for x in date_str.split("-"))
    _dt.date(y, m, d)  # rejects impossible dates
    square = make_birthday_4x4(y, m, d)
    core = core_numbers(y, m, d)
    has_neg = any(v <= 0 for row in square for v in row)
    return {
        "kind": "birthday",
        "date": date_str,
        "square": square,
        "magic_sum": sum(square[0]),
        "moolank": core["moolank"],
        "bhagyank": core["bhagyank"],
        "magic_valid": is_magic(square),
        "note": ("Some cells are <= 0 (small birth month) — the square is still "
                 "mathematically magic." if has_neg else None),
        "title": "Janma Yantra (Birth Magic Square)",
        "subtitle": f"DOB {date_str}  •  Moolank {core['moolank']}, Bhagyank {core['bhagyank']}",
        "footer": f"Every line totals {sum(square[0])}",
    }


def build_planet(key: str) -> dict:
    key = key.lower()
    if key not in PLANETS:
        raise ValueError(f"unknown planet {key!r}; choose from {', '.join(PLANETS)} or 'all'")
    p = PLANETS[key]
    square = make_3x3(p["magic_sum"])
    return {
        "kind": "planet",
        "planet": key,
        "planet_en": p["en"],
        "square": square,
        "magic_sum": p["magic_sum"],
        "day": p["day"],
        "bija_mantra": p["bija"],
        "helps": p["helps"],
        "magic_valid": is_magic(square),
        "title": f"{p['en']} Yantra ({key.title()})",
        "subtitle": f"{p['day']}  •  magic sum {p['magic_sum']}",
        "footer": p["bija"],
    }


def build_target(target: int) -> dict:
    square = make_3x3(target)
    has_neg = any(v <= 0 for row in square for v in row)
    return {
        "kind": "target",
        "square": square,
        "magic_sum": target,
        "magic_valid": is_magic(square),
        "note": ("Target is small — some cells are <= 0 but the square is still "
                 "magic." if has_neg else None),
        "title": f"Magic Square Yantra ({target})",
        "subtitle": f"Centre {target // 3}  •  every line totals {target}",
        "footer": f"Every line totals {target}",
    }


# --- CLI --------------------------------------------------------------------

def emit(result: dict, args, svg_path=None):
    if svg_path:
        svg = render_svg(result["square"], result["title"],
                         result.get("subtitle", ""), result.get("footer", ""))
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        result["svg_path"] = svg_path
    if args.json:
        return
    print(render_text(result["square"], result["title"],
                      result.get("subtitle", ""), result.get("footer", "")))
    if result.get("note"):
        print(f"  Note: {result['note']}")
    if svg_path:
        print(f"  SVG written: {svg_path}")
    if result["kind"] == "planet":
        print(f"  Best day: {result['day']}  |  Helps with: {result['helps']}")
        print(f"  Bija mantra: {result['bija_mantra']}")


def main():
    ap = argparse.ArgumentParser(description="Generate a numeric (magic-square) yantra.")
    ap.add_argument("--date", help="Date of birth YYYY-MM-DD (personalised 4x4 birth yantra)")
    ap.add_argument("--planet", help="Navagraha 3x3 yantra: surya/chandra/mangal/budh/"
                                     "guru/shukra/shani/rahu/ketu, or 'all'")
    ap.add_argument("--target", type=int, help="Custom 3x3 magic sum (multiple of 3)")
    ap.add_argument("--svg", default=None,
                    help="Write an SVG image. With --planet all, used as a filename prefix.")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    try:
        if args.planet:
            if args.planet.lower() == "all":
                results = []
                for key in PLANETS:
                    res = build_planet(key)
                    spath = None
                    if args.svg:
                        stem, ext = os.path.splitext(args.svg)
                        spath = f"{stem or 'yantra'}_{key}{ext or '.svg'}"
                    emit(res, args, spath)
                    if not args.json:
                        print()
                    results.append(res)
                if args.json:
                    print(json.dumps({"yantras": results, "disclaimer": DISCLAIMER}, indent=2))
                return
            result = build_planet(args.planet)
        elif args.target is not None:
            result = build_target(args.target)
        elif args.date:
            result = build_birthday(args.date)
        else:
            ap.error("provide one of --date, --planet, or --target")
    except Exception as e:  # noqa: BLE001 — clean message to the agent
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    emit(result, args, args.svg)
    if args.json:
        result["disclaimer"] = DISCLAIMER
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

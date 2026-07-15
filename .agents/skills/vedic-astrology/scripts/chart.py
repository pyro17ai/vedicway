#!/usr/bin/env python3
"""
chart.py — Render a kundli as an ASCII diagram (South or North Indian style).

Draws any divisional chart (D1 by default, or any Shodasavarga division) in the
two common visual conventions:

  * South Indian — a fixed 4x4 grid, signs in fixed cells (Pisces top-left,
    clockwise), planets dropped into their sign. Geometrically exact.
  * North Indian — the diamond, houses fixed by position (House 1 top-centre,
    counter-clockwise), the Lagna sign written into House 1. Each region is
    labelled with its house number so the placement is unambiguous.

Usage:
    python chart.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--style south|north|both] [--varga D1] [--json]

Disclaimer: cultural / educational use only. Not predictive of real outcomes.
"""

from __future__ import annotations

import argparse
import json
import sys

import core

ABBR = {"Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju",
        "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"}
SIGN_ABBR = ["Ar", "Ta", "Ge", "Cn", "Le", "Vi", "Li", "Sc", "Sg", "Cp", "Aq", "Pi"]

# South Indian fixed grid: (row, col) -> sign number (1..12).
SOUTH_CELLS = {
    (0, 0): 12, (0, 1): 1, (0, 2): 2, (0, 3): 3,
    (1, 3): 4, (2, 3): 5, (3, 3): 6,
    (3, 2): 7, (3, 1): 8, (3, 0): 9,
    (2, 0): 10, (1, 0): 11,
}


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def _varga_div(arg: str) -> int:
    tok = arg.strip().upper().lstrip("D")
    n = int(tok) if tok else 1
    if n not in core.SUPPORTED_VARGAS:
        raise ValueError(f"D{n} is not supported. Supported: {core.SUPPORTED_VARGAS}")
    return n


def compute(args) -> dict:
    core.init_engine(
        args.ayanamsa, node=getattr(args, "node", "mean"),
        topocentric=not getattr(args, "geocentric", False),
        lat=args.lat, lon=args.lon, ephemeris=getattr(args, "ephemeris", "moshier"),
    )
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)
    div = _varga_div(args.varga)

    asc = core.ascendant(jd, args.lat, args.lon)
    positions = core.all_planet_positions(jd)

    # Sign (1..12) of each point in the requested division.
    asc_sign = core.varga_sign(asc["longitude"], div)
    sign_of = {n: core.varga_sign(positions[n]["longitude"], div) for n in core.PLANET_ORDER}

    # Planets grouped by sign.
    by_sign = {s: [] for s in range(1, 13)}
    for n in core.PLANET_ORDER:
        by_sign[sign_of[n]].append(ABBR[n])

    return {"div": div, "asc_sign": asc_sign, "by_sign": by_sign,
            "lagna_sign_name": core.SIGNS[asc_sign - 1]}


# --------------------------------------------------------------------------- #
# South Indian (exact grid)
# --------------------------------------------------------------------------- #
def render_south(data: dict) -> str:
    div, asc_sign, by_sign = data["div"], data["asc_sign"], data["by_sign"]
    CW = 13  # cell inner width
    def cell(r, c):
        s = SOUTH_CELLS.get((r, c))
        if s is None:
            if (r, c) == (1, 1):
                return [f"D{div}".center(CW), "chart".center(CW), "".center(CW)]
            if (r, c) == (1, 2):
                return ["South".center(CW), "Indian".center(CW), "".center(CW)]
            return ["".center(CW)] * 3
        tag = SIGN_ABBR[s - 1] + ("(Asc)" if s == asc_sign else "")
        planets = " ".join(by_sign[s])
        return [tag.ljust(CW), planets[:CW].ljust(CW), planets[CW:2 * CW][:CW].ljust(CW)]

    lines = []
    border = "+" + ("-" * CW + "+") * 4
    for r in range(4):
        lines.append(border)
        rows = [cell(r, c) for c in range(4)]
        for k in range(3):
            lines.append("|" + "|".join(rows[c][k] for c in range(4)) + "|")
    lines.append(border)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# North Indian (diamond; houses fixed, House 1 = Lagna)
# --------------------------------------------------------------------------- #
# House -> (row, col) anchor on the canvas (centre of each region).
# Houses are fixed; House 1 is top-centre, numbering runs counter-clockwise.
NORTH_ANCHORS = {
    1: (3, 30), 2: (2, 15), 3: (6, 8), 4: (9, 15), 5: (13, 8), 6: (16, 15),
    7: (15, 30), 8: (16, 45), 9: (13, 52), 10: (9, 45), 11: (6, 52), 12: (2, 45),
}
CW_H, CH = 61, 19


def _draw_line(canvas, r0, c0, r1, c1):
    steps = max(abs(r1 - r0), abs(c1 - c0))
    for i in range(steps + 1):
        r = round(r0 + (r1 - r0) * i / steps)
        c = round(c0 + (c1 - c0) * i / steps)
        if 0 <= r < CH and 0 <= c < CW_H and canvas[r][c] == " ":
            dr, dc = r1 - r0, c1 - c0
            canvas[r][c] = "\\" if (dr * dc > 0) else "/"


def render_north(data: dict) -> str:
    div, asc_sign, by_sign = data["div"], data["asc_sign"], data["by_sign"]
    canvas = [[" "] * CW_H for _ in range(CH)]
    # Outer border
    for c in range(CW_H):
        canvas[0][c] = canvas[CH - 1][c] = "-"
    for r in range(CH):
        canvas[r][0] = canvas[r][CW_H - 1] = "|"
    # Diagonals (corner to corner) + inner diamond (edge midpoints)
    _draw_line(canvas, 0, 0, CH - 1, CW_H - 1)
    _draw_line(canvas, 0, CW_H - 1, CH - 1, 0)
    mids = [(0, CW_H // 2), (CH // 2, CW_H - 1), (CH - 1, CW_H // 2), (CH // 2, 0)]
    for i in range(4):
        _draw_line(canvas, *mids[i], *mids[(i + 1) % 4])

    def place(r, c, text):
        start = c - len(text) // 2
        for i, ch in enumerate(text):
            cc = start + i
            if 0 < cc < CW_H - 1 and 0 < r < CH - 1:
                canvas[r][cc] = ch

    for h in range(1, 13):
        sign_num = ((asc_sign - 1) + (h - 1)) % 12 + 1
        r, c = NORTH_ANCHORS[h]
        place(r, c, SIGN_ABBR[sign_num - 1])
        planets = " ".join(by_sign[sign_num])
        if planets:
            place(r + 1, c, planets[:15])
    out = ["D{} chart — North Indian (House 1 = Lagna, counter-clockwise)".format(div)]
    out += ["".join(row) for row in canvas]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Render a kundli as an ASCII diagram.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--style", default="both", choices=["south", "north", "both"])
    ap.add_argument("--varga", default="D1", help="Division to draw, e.g. D1, D9, D10 (default D1)")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        data = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(data, indent=2)); return

    out = []
    if args.style in ("south", "both"):
        out.append(render_south(data))
    if args.style in ("north", "both"):
        out.append(render_north(data))
    print(f"Lagna: {data['lagna_sign_name']}  |  D{data['div']} chart\n")
    print("\n\n".join(out))
    print("\nSu=Sun Mo=Moon Ma=Mars Me=Mercury Ju=Jupiter Ve=Venus Sa=Saturn Ra=Rahu Ke=Ketu")
    print("For cultural/educational use only.")


if __name__ == "__main__":
    main()

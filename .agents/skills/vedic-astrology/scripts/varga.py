#!/usr/bin/env python3
"""
varga.py — Divisional (Varga) charts and cross-varga strength.

The Rashi (D1) chart shows the whole life; the divisional charts zoom into one
area each — D10 (Dasamsha) for career, D9 (Navamsa) for marriage/dharma, D7 for
children, D2 for wealth, D24 for education, D30 for adversity, D60 for the
finest karmic layer. A planet that is strong (own sign / exalted) across many
vargas gives steady results in those areas; one that is weak across them
disappoints even if it looks fine in D1.

This script computes the full **Shodasavarga** (16 divisions) for all nine
grahas plus the Lagna, summarises each planet's dignity across the vargas, and
gives a transparent cross-varga strength score.

Usage:
    python varga.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--charts D9,D10,D7] [--ayanamsa lahiri] [--json]

--charts  comma-separated divisions to print in full (default D9,D10). Use
          'all' for the 16 classical Shodasavarga, or 'all+' to also include the
          four non-classical extras D5/D6/D8/D11. The strength summary always
          spans the classical 16 only (the extras are display-only).

Disclaimer: cultural / educational use only. Not predictive of real outcomes.
"""

from __future__ import annotations

import argparse
import json
import sys

import core

POINTS = core.PLANET_ORDER + ["Lagna"]

# Transparent cross-varga dignity weights (NOT the classical Vimshopaka table —
# this is the skill's own honest scheme, documented in references/vargas.md).
DIGNITY_SCORE = {"exalted": 1.0, "own sign": 1.0, "friend": 0.66,
                 "neutral": 0.5, "enemy": 0.33, "debilitated": 0.0, "node": 0.5}

# Shadvarga group weights (the one classical weighting we use, sums to 20).
SHADVARGA_WEIGHTS = {1: 6, 2: 2, 3: 4, 9: 5, 12: 2, 30: 1}


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def _dignity_in(planet: str, sign_num: int) -> str:
    """Dignity of a planet in a varga sign. Nodes use friendship to the sign lord."""
    if planet in ("Rahu", "Ketu"):
        return "node"
    base = core.dignity(planet, sign_num)
    if base != "neutral":
        return base
    lord = core.SIGN_LORD[sign_num]
    if lord == planet:
        return "own sign"
    return core.natural_relation(planet, lord)


def compute(args) -> dict:
    core.init_engine(
        args.ayanamsa, node=getattr(args, "node", "mean"),
        topocentric=not getattr(args, "geocentric", False),
        lat=args.lat, lon=args.lon, ephemeris=getattr(args, "ephemeris", "moshier"),
    )
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)

    asc = core.ascendant(jd, args.lat, args.lon)
    positions = core.all_planet_positions(jd)
    lons = {name: positions[name]["longitude"] for name in core.PLANET_ORDER}
    lons["Lagna"] = asc["longitude"]

    # Sign for every point in every supported division (the 16 Shodasavarga plus
    # the 4 non-classical extras). The cross-varga strength below still spans ONLY
    # the classical 16 — the extras are available for display, not scoring.
    charts: dict = {}
    for d_div in core.SUPPORTED_VARGAS:
        charts[d_div] = {pt: core.varga_sign(lons[pt], d_div) for pt in POINTS}

    # Per-planet dignity across the 16 vargas + transparent strength score.
    strength = {}
    for planet in core.PLANET_ORDER:
        per_varga = {}
        own_exalt = 0
        debil = 0
        weighted = 0.0
        wsum = 0.0
        shad = 0.0
        for d_div in core.SHODASAVARGA:
            sgn = charts[d_div][planet]
            dig = _dignity_in(planet, sgn)
            per_varga[d_div] = {"sign_num": sgn, "sign": core.SIGNS[sgn - 1], "dignity": dig}
            if dig in ("own sign", "exalted"):
                own_exalt += 1
            if dig == "debilitated":
                debil += 1
            sc = DIGNITY_SCORE[dig]
            weighted += sc
            wsum += 1
            if d_div in SHADVARGA_WEIGHTS:
                shad += sc * SHADVARGA_WEIGHTS[d_div]
        strength[planet] = {
            "per_varga": per_varga,
            "own_or_exalted_count": own_exalt,
            "debilitated_count": debil,
            "varga_bala_pct": round(100 * weighted / wsum, 1),
            "shadvarga_score_of_20": round(shad, 2),
        }

    return {
        "input": {"date": args.date, "time": args.time, "lat": args.lat,
                  "lon": args.lon, "timezone": args.tz, "ayanamsa": args.ayanamsa},
        "lagna_sign": asc["sign"],
        "charts": charts,
        "strength": strength,
    }


def _requested_divisions(arg: str) -> list[int]:
    if not arg:
        return [9, 10]
    if arg.strip().lower() == "all":
        return list(core.SHODASAVARGA)            # 'all' = the classical 16
    if arg.strip().lower() == "all+":
        return list(core.SUPPORTED_VARGAS)        # 'all+' = 16 classical + 4 extras
    out = []
    for tok in arg.split(","):
        tok = tok.strip().upper().lstrip("D")
        if not tok:
            continue
        n = int(tok)
        if n not in core.SUPPORTED_VARGAS:
            raise ValueError(f"D{n} is not supported. Supported: {core.SUPPORTED_VARGAS}")
        out.append(n)
    return out or [9, 10]


def render_text(result: dict, divisions: list[int]) -> str:
    L = []
    A = L.append
    A("=" * 70)
    A("  DIVISIONAL CHARTS (VARGAS)")
    A("=" * 70)
    A(f"  Lagna (D1): {result['lagna_sign']}")
    A("-" * 70)

    for d_div in divisions:
        A(f"\n  D{d_div} — {core.VARGA_PURPOSE[d_div]}")
        A("  " + "-" * 52)
        chart = result["charts"][d_div]
        # Group points by their varga sign for a compact house-style listing.
        for pt in POINTS:
            sgn = chart[pt]
            label = "Asc" if pt == "Lagna" else pt
            dig = "" if pt == "Lagna" else f"  ({_dignity_in(pt, sgn)})"
            A(f"    {label:<8} {core.SIGNS[sgn - 1]:<12}{dig}")

    A("\n" + "=" * 70)
    A("  CROSS-VARGA STRENGTH  (over all 16 Shodasavarga divisions)")
    A("=" * 70)
    A("  Planet     Own/Exalt  Debil   VargaBala   Shadvarga/20")
    A("  " + "-" * 56)
    for planet in core.PLANET_ORDER:
        s = result["strength"][planet]
        A(f"  {planet:<10} {s['own_or_exalted_count']:>5}/16   {s['debilitated_count']:>4}    "
          f"{s['varga_bala_pct']:>6.1f}%      {s['shadvarga_score_of_20']:>5.2f}")
    A("  " + "-" * 56)
    A("  Own/Exalt = vargas where the planet is in own sign or exalted (more = better).")
    A("  VargaBala = transparent dignity score across all 16 (this skill's own scheme,")
    A("  NOT the classical Vimshopaka). Shadvarga/20 weights D1,D2,D3,D9,D12,D30.")
    A("=" * 70)
    A("  For cultural/educational use only. Not predictive of real outcomes.")
    A("=" * 70)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Compute divisional (varga) charts + cross-varga strength.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--charts", default="D9,D10",
                    help="Divisions to print, e.g. 'D9,D10,D7'; 'all' = 16 classical; "
                         "'all+' = +D5/D6/D8/D11 extras (default D9,D10)")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        divisions = _requested_divisions(args.charts)
        result = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result, divisions))


if __name__ == "__main__":
    main()

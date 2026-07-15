#!/usr/bin/env python3
"""
gochar.py — Transits (gochar), Sade Sati, and transit strength.

A dasha says *what* theme is active; the transiting planets say *when* it fires.
This script places today's (or any date's) planets against the natal chart,
counted from both the natal Moon (Chandra Lagna — the classical reference for
gochar) and the natal Lagna, flags **Sade Sati** and the **Dhaiya** (Kantaka /
Ashtama Shani) Saturn phases, reports the slow-planet transits (Saturn, Jupiter,
Rahu/Ketu), and grades each transit by the natal Sarvashtakavarga bindus in the
sign being transited (a transit through a high-bindu sign delivers; through a
low-bindu sign struggles).

Usage:
    python gochar.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--on 2026-06-04] [--ayanamsa lahiri] [--json]

--on  the transit date to read (default: today). Moon transit is time-sensitive;
      this script samples the transit sky at noon of --on in the birth timezone.

Disclaimer: cultural / educational use only. Not predictive of real outcomes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime

import core
import strength as strength_mod

SLOW = ["Saturn", "Jupiter", "Rahu", "Ketu"]

# House-from-Moon transit nature for the slow, classically-emphasised planets.
# (Standard gochar good/bad houses counted from the natal Moon.)
GOOD_FROM_MOON = {
    "Saturn": {3, 6, 11},
    "Jupiter": {2, 5, 7, 9, 11},
    "Sun": {3, 6, 10, 11},
    "Mars": {3, 6, 11},
    "Mercury": {2, 4, 6, 8, 10, 11},
    "Venus": {1, 2, 3, 4, 5, 8, 9, 11, 12},
    "Moon": {1, 3, 6, 7, 10, 11},
    "Rahu": {3, 6, 11},
    "Ketu": {3, 6, 11},
}

SADE_SATI_PHASE = {
    12: "Rising phase (Saturn in the 12th from Moon) — onset; expenses, sleep "
        "disturbance, foreign/letting-go themes begin.",
    1: "Peak phase (Saturn over the Moon) — the heaviest stretch; pressure on "
       "mind, health, and confidence. Greatest test and greatest maturing.",
    2: "Setting phase (Saturn in the 2nd from Moon) — winding down; strain on "
       "finances, family, and speech, then gradual relief.",
}
DHAIYA = {
    4: "Ardhashtama Shani (Saturn in the 4th from Moon) — 'small panoti': "
       "pressure on home, mother, property, and peace of mind.",
    8: "Ashtama Shani (Saturn in the 8th from Moon) — 'small panoti': health, "
       "obstacles, sudden disruptions, and chronic worry.",
}


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def compute(args) -> dict:
    core.init_engine(
        args.ayanamsa, node=getattr(args, "node", "mean"),
        topocentric=not getattr(args, "geocentric", False),
        lat=args.lat, lon=args.lon, ephemeris=getattr(args, "ephemeris", "moshier"),
    )
    # --- Natal chart ---
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    jd_natal = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)
    asc = core.ascendant(jd_natal, args.lat, args.lon)
    natal = core.all_planet_positions(jd_natal)
    moon_sign = natal["Moon"]["sign_num"]
    asc_sign = asc["sign_num"]

    # Natal Sarvashtakavarga (reused for transit grading).
    av = strength_mod.compute_ashtakavarga(natal, asc_sign)
    sav = av["sav"]["per_sign"]   # 12-element, index 0 = Aries

    # --- Transit sky at noon of --on ---
    ty, tm, td = (int(x) for x in args.on.split("-"))
    jd_tr = core.to_julian_ut(ty, tm, td, 12, 0, 0, args.tz)
    transit = core.all_planet_positions(jd_tr)

    rows = []
    for name in core.PLANET_ORDER:
        t_sign = transit[name]["sign_num"]
        h_moon = core.house_of(t_sign, moon_sign)
        h_asc = core.house_of(t_sign, asc_sign)
        bindus = sav[t_sign - 1]
        nature = "favourable" if h_moon in GOOD_FROM_MOON.get(name, set()) else "challenging"
        if bindus >= 30:
            av_note = "strong (≥30 SAV bindus)"
        elif bindus <= 25:
            av_note = "weak (≤25 SAV bindus)"
        else:
            av_note = "moderate"
        rows.append({
            "planet": name,
            "sign": transit[name]["sign"],
            "nakshatra": transit[name]["nakshatra"],
            "retrograde": transit[name]["retrograde"],
            "house_from_moon": h_moon,
            "house_from_lagna": h_asc,
            "nature_from_moon": nature,
            "sav_bindus": bindus,
            "av_strength": av_note,
        })

    # --- Sade Sati / Dhaiya from Saturn's house from Moon ---
    sat_house = core.house_of(transit["Saturn"]["sign_num"], moon_sign)
    saturn_panoti = {"active": False, "type": None, "phase_house": sat_house, "note": None}
    if sat_house in SADE_SATI_PHASE:
        saturn_panoti.update(active=True, type="Sade Sati", note=SADE_SATI_PHASE[sat_house])
    elif sat_house in DHAIYA:
        saturn_panoti.update(active=True, type="Dhaiya", note=DHAIYA[sat_house])
    else:
        saturn_panoti["note"] = (f"No Sade Sati or Dhaiya now — Saturn is in the "
                                 f"{sat_house}th from your Moon.")

    return {
        "input": {"date": args.date, "time": args.time, "lat": args.lat,
                  "lon": args.lon, "timezone": args.tz, "ayanamsa": args.ayanamsa},
        "on": args.on,
        "natal_moon_sign": core.SIGNS[moon_sign - 1],
        "natal_lagna_sign": asc["sign"],
        "saturn_panoti": saturn_panoti,
        "transits": rows,
    }


def render_text(r: dict) -> str:
    L = []
    A = L.append
    A("=" * 70)
    A("  GOCHAR (TRANSITS) — sky vs natal chart")
    A("=" * 70)
    A(f"  Reading for : {r['on']}   (transit sky sampled at noon)")
    A(f"  Natal Moon  : {r['natal_moon_sign']}   |   Natal Lagna: {r['natal_lagna_sign']}")
    A("-" * 70)

    sp = r["saturn_panoti"]
    A("  SATURN — SADE SATI / DHAIYA")
    if sp["active"]:
        A(f"    ⚠ {sp['type']} ACTIVE.")
        A(f"      {sp['note']}")
    else:
        A(f"    ✓ {sp['note']}")
    A("")

    A("  ALL TRANSITS  (house counted from the Moon = classical gochar reference)")
    A("  Planet    Sign          fromMoon  fromLagna  Nature        AV")
    A("  " + "-" * 64)
    for t in r["transits"]:
        rx = "(R)" if t["retrograde"] else ""
        A(f"  {t['planet']:<7}{rx:<3} {t['sign']:<12}  {t['house_from_moon']:>5}   "
          f"{t['house_from_lagna']:>6}    {t['nature_from_moon']:<12} {t['sav_bindus']:>2}")
    A("  " + "-" * 64)
    A("  Nature = classical good/bad transit house from the Moon for that planet.")
    A("  AV = natal Sarvashtakavarga bindus in the transited sign (≥30 strong, ≤25 weak).")
    A("")
    A("  Slow movers that set the year's tone:")
    for t in r["transits"]:
        if t["planet"] in SLOW:
            A(f"    • {t['planet']}: {t['sign']} — {t['house_from_moon']}th from Moon, "
              f"{t['nature_from_moon']}, {t['av_strength']}.")
    A("=" * 70)
    A("  For cultural/educational use only. Transits modulate the running dasha;")
    A("  read them together. Not predictive of real outcomes.")
    A("=" * 70)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Transits, Sade Sati, and transit strength.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--on", default=date.today().isoformat(),
                    help="Transit date YYYY-MM-DD (default: today)")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        datetime.strptime(args.on, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: --on must be YYYY-MM-DD, got '{args.on}'", file=sys.stderr)
        sys.exit(1)

    try:
        result = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

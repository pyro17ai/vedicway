#!/usr/bin/env python3
"""
lucky.py — the seeker's lucky profile: day, colour, number, direction, gem, metal.

Many questions ("my lucky colour / day / number / direction", "which colour car",
"which house number", "which day to decide") reduce to one thing: the supportive
planets for this chart. Those are the **Lagna lord** (the planet that runs your
whole self), the **Moon-sign lord**, and the **Yogakaraka** if the chart has one.
This script reads their classical attributes and a numerology radical (Moolank)
from the birth day, each with its reason.

Usage:
    python lucky.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata [--json]

Disclaimer: cultural / educational use only. Not advice; no proven effect.
"""

from __future__ import annotations

import argparse
import json
import sys

import core
import astro_claude as ac

# Classical attributes per planet (day, colour, Chaldean number, direction, metal).
ATTR = {
    "Sun":     {"day": "Sunday",    "colour": "Red / Orange / Gold", "number": 1, "dir": "East",        "metal": "Gold / Copper",  "deity": "Surya / Shiva"},
    "Moon":    {"day": "Monday",    "colour": "White / Cream / Silver","number": 2,"dir": "North-West",  "metal": "Silver",         "deity": "Parvati / Chandra"},
    "Mars":    {"day": "Tuesday",   "colour": "Red / Coral",         "number": 9, "dir": "South",        "metal": "Copper",         "deity": "Hanuman / Kartikeya"},
    "Mercury": {"day": "Wednesday", "colour": "Green",               "number": 5, "dir": "North",        "metal": "Brass / Bronze", "deity": "Vishnu / Ganesha"},
    "Jupiter": {"day": "Thursday",  "colour": "Yellow / Gold",       "number": 3, "dir": "North-East",   "metal": "Gold",           "deity": "Brihaspati / Vishnu"},
    "Venus":   {"day": "Friday",    "colour": "White / Pastel / Pink","number": 6,"dir": "South-East",   "metal": "Silver / Platinum","deity": "Lakshmi"},
    "Saturn":  {"day": "Saturday",  "colour": "Blue / Black",        "number": 8, "dir": "West",         "metal": "Iron / Steel",   "deity": "Shani / Hanuman"},
    "Rahu":    {"day": "Saturday",  "colour": "Smoky / Grey",        "number": 4, "dir": "South-West",   "metal": "Lead",           "deity": "Durga"},
    "Ketu":    {"day": "Tuesday",   "colour": "Multi / Brown",       "number": 7, "dir": "North-West",   "metal": "Mixed",          "deity": "Ganesha"},
}
GEM = ac.GEM


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def _reduce(n: int) -> int:
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n


def compute(args) -> dict:
    core.init_engine(args.ayanamsa, node=getattr(args, "node", "mean"),
                     topocentric=not getattr(args, "geocentric", False),
                     lat=args.lat, lon=args.lon, ephemeris=getattr(args, "ephemeris", "moshier"))
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)
    asc = core.ascendant(jd, args.lat, args.lon)
    asc_sign = asc["sign_num"]
    pos = core.all_planet_positions(jd)
    moon_sign = pos["Moon"]["sign_num"]

    lagna_lord = core.SIGN_LORD[asc_sign]
    moon_lord = core.SIGN_LORD[moon_sign]

    # Yogakaraka (if any) via the functional engine.
    yk = None
    for p in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"):
        house = core.house_of(pos[p]["sign_num"], asc_sign)
        if ac.functional_nature(p, asc_sign, house)["is_yogakaraka"]:
            yk = p
            break

    # Supportive planets, de-duplicated, in priority order.
    supportive, seen = [], set()
    for tag, pl in (("Lagna lord", lagna_lord), ("Yogakaraka", yk), ("Moon-sign lord", moon_lord)):
        if pl and pl not in seen:
            supportive.append({"role": tag, "planet": pl})
            seen.add(pl)

    primary = supportive[0]["planet"]
    moolank = _reduce(d)                      # radical number from the birth day

    def attrs(pl):
        a = dict(ATTR[pl]); a["gem"] = GEM[pl]; a["planet"] = pl
        a["planet_hi"] = core.PLANET_HINDI[pl]
        return a

    return {
        "input": {"date": args.date, "time": args.time, "lat": args.lat,
                  "lon": args.lon, "timezone": args.tz, "ayanamsa": args.ayanamsa},
        "lagna_sign": asc["sign"], "moon_sign": pos["Moon"]["sign"],
        "lagna_lord": lagna_lord, "moon_lord": moon_lord, "yogakaraka": yk,
        "supportive": [{**s, **attrs(s["planet"])} for s in supportive],
        "moolank": moolank,
        "lucky": {
            "days": sorted({ATTR[s["planet"]]["day"] for s in supportive}),
            "colours": [ATTR[s["planet"]]["colour"] for s in supportive],
            "numbers": sorted({ATTR[primary]["number"], moolank}),
            "directions": sorted({ATTR[s["planet"]]["dir"] for s in supportive}),
            "metals": sorted({ATTR[s["planet"]]["metal"] for s in supportive}),
            "gem": GEM[primary],
            "deity": ATTR[primary]["deity"],
        },
    }


def render_text(r: dict) -> str:
    L = []
    A = L.append
    A("=" * 64)
    A("  YOUR LUCKY PROFILE")
    A("=" * 64)
    A(f"  Lagna: {core.sign_hi(r['lagna_sign'])}   |   Moon: {core.sign_hi(r['moon_sign'])}")
    A("  Your fortune is carried by the planets that rule and support your chart:")
    for s in r["supportive"]:
        A(f"    • {s['role']}: {core.planet_hi(s['planet'])}")
    A("-" * 64)
    lk = r["lucky"]
    A(f"  Lucky days       : {', '.join(lk['days'])}")
    A(f"     why: the weekday(s) ruled by your supportive planet(s).")
    A(f"  Lucky colours    : {', '.join(lk['colours'])}")
    A(f"     why: the colour(s) of your supportive planet(s).")
    A(f"  Lucky numbers    : {', '.join(map(str, lk['numbers']))}")
    A(f"     why: your Moolank (birth-day radical = {r['moolank']}) + your "
      f"Lagna-lord's number.")
    A(f"  Lucky directions : {', '.join(lk['directions'])}")
    A(f"     why: the classical direction(s) of your supportive planet(s) — face "
      f"these for important work.")
    A(f"  Lucky metals     : {', '.join(lk['metals'])}")
    A(f"  Favoured gem     : {lk['gem']}  (your strongest supportive planet)")
    A(f"  Ishta / deity    : {lk['deity']}")
    A("-" * 64)
    A("  Use these for choices that ask for a 'lucky' factor — a colour for a car or")
    A("  home, a day to sign or decide, a direction to sit facing. For a lucky")
    A("  NUMBER on a vehicle/house/mobile, also run the numerology skill.")
    A("=" * 64)
    A("  For cultural/educational use only. Not predictive of real outcomes.")
    A("=" * 64)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="The seeker's lucky day/colour/number/direction profile.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        result = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

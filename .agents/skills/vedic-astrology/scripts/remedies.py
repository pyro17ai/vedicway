#!/usr/bin/env python3
"""
remedies.py — Traditional planetary remedies (upaya).

Given a chart, this flags the planets a classical practitioner would look to
propitiate — the running **Mahadasha lord**, and any planet that is **weak or
afflicted** (debilitated, combust, or sitting in a dusthana 6/8/12) — and lists
the traditional remedy set for each: deity, beej mantra, gemstone, metal, day,
colour, and charity (daan).

A note on gemstones: tradition reserves a planet's gemstone for *strengthening*
a benefic, well-meaning planet — NOT for an afflicted malefic, where mantra,
charity, and service are preferred. The output marks each planet "strengthen"
vs "pacify" accordingly. Blue sapphire (Saturn), hessonite (Rahu), and cat's eye
(Ketu) are traditionally *tested* before wearing; never advise wearing one
casually.

Usage:
    python remedies.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata [--on 2026-06-04] [--json]

Disclaimer: these are TRADITIONAL CULTURAL practices, recorded for educational
interest only. They are not medical, financial, or psychological advice and have
no scientifically demonstrated effect. Do not spend money on gemstones or rituals
on the strength of this output.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime

import core
import dasha as dasha_mod

REMEDIES = {
    "Sun": {"deity": "Surya / Shiva", "mantra": "Om Hraam Hreem Hraum Sah Suryaya Namah",
            "gem": "Ruby (manik)", "metal": "Gold/Copper", "day": "Sunday", "colour": "Red",
            "daan": "wheat, jaggery, copper, red cloth"},
    "Moon": {"deity": "Parvati / Shiva", "mantra": "Om Shraam Shreem Shraum Sah Chandraya Namah",
             "gem": "Pearl (moti)", "metal": "Silver", "day": "Monday", "colour": "White",
             "daan": "rice, milk, white cloth, silver"},
    "Mars": {"deity": "Hanuman / Kartikeya", "mantra": "Om Kraam Kreem Kraum Sah Bhaumaya Namah",
             "gem": "Red coral (moonga)", "metal": "Copper", "day": "Tuesday", "colour": "Red",
             "daan": "masoor dal, red cloth, jaggery; recite Hanuman Chalisa"},
    "Mercury": {"deity": "Vishnu / Ganesha", "mantra": "Om Braam Breem Braum Sah Budhaya Namah",
                "gem": "Emerald (panna)", "metal": "Gold", "day": "Wednesday", "colour": "Green",
                "daan": "green moong, green cloth; feed green fodder to cows"},
    "Jupiter": {"deity": "Brihaspati / Vishnu", "mantra": "Om Graam Greem Graum Sah Gurave Namah",
                "gem": "Yellow sapphire (pukhraj)", "metal": "Gold", "day": "Thursday", "colour": "Yellow",
                "daan": "turmeric, chana dal, gold, books; serve teachers/priests"},
    "Venus": {"deity": "Lakshmi", "mantra": "Om Draam Dreem Draum Sah Shukraya Namah",
              "gem": "Diamond / white sapphire", "metal": "Silver", "day": "Friday", "colour": "White",
              "daan": "sugar, curd, white/silk cloth, perfume"},
    "Saturn": {"deity": "Shani / Hanuman", "mantra": "Om Praam Preem Praum Sah Shanaye Namah",
               "gem": "Blue sapphire (neelam) — TEST FIRST", "metal": "Iron", "day": "Saturday",
               "colour": "Black/Dark blue", "daan": "black sesame, mustard oil, iron, black cloth; "
               "serve the elderly/labourers, feed crows"},
    "Rahu": {"deity": "Durga / Bhairava", "mantra": "Om Bhraam Bhreem Bhraum Sah Rahave Namah",
             "gem": "Hessonite (gomed) — TEST FIRST", "metal": "Lead/Mixed", "day": "Saturday",
             "colour": "Smoky/Dark", "daan": "mustard, coconut, blue cloth, sesame"},
    "Ketu": {"deity": "Ganesha / Shiva", "mantra": "Om Sraam Sreem Sraum Sah Ketave Namah",
             "gem": "Cat's eye (lehsunia) — TEST FIRST", "metal": "Mixed", "day": "Tuesday",
             "colour": "Multicolour/Grey", "daan": "blanket, multicoloured cloth, sesame; serve dogs"},
}

DUSTHANA = {6, 8, 12}


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def _current_maha(args) -> str:
    class _A: pass
    da = _A()
    for k in ("date", "time", "lat", "lon", "tz", "ayanamsa"):
        setattr(da, k, getattr(args, k))
    da.node = getattr(args, "node", "mean")
    da.ephemeris = getattr(args, "ephemeris", "moshier")
    da.geocentric = getattr(args, "geocentric", False)
    da.levels = 1
    tl = dasha_mod.compute_dasha(da)
    for md in tl["mahadashas"]:
        if md["start"] <= args.on < md["end"]:
            return md["lord"]
    return tl["mahadashas"][0]["lord"]


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
    asc_sign = asc["sign_num"]
    positions = core.all_planet_positions(jd)
    sun_lon = positions["Sun"]["longitude"]

    maha = _current_maha(args)

    flagged = []
    for name in core.PLANET_ORDER:
        p = positions[name]
        house = core.house_of(p["sign_num"], asc_sign)
        dig = core.dignity(name, p["sign_num"])
        combust = (name not in ("Sun", "Rahu", "Ketu")
                   and core.is_combust(name, p["longitude"], sun_lon, p["retrograde"]))
        reasons = []
        if name == maha:
            reasons.append("running Mahadasha lord")
        if dig == "debilitated":
            reasons.append("debilitated")
        if combust:
            reasons.append("combust")
        if house in DUSTHANA:
            reasons.append(f"in dusthana (House {house})")
        if not reasons:
            continue
        # Gemstone advice: strengthen only if not an afflicted malefic placement.
        afflicted = ("debilitated" in reasons) or ("combust" in reasons)
        approach = "pacify (mantra/charity/service preferred; avoid the gemstone)" \
            if afflicted or name in ("Saturn", "Rahu", "Ketu") \
            else "strengthen (gemstone is traditionally allowed)"
        flagged.append({
            "planet": name, "house": house, "dignity": dig, "combust": combust,
            "reasons": reasons, "approach": approach, "remedies": REMEDIES[name],
        })

    return {
        "input": {"date": args.date, "time": args.time, "lat": args.lat,
                  "lon": args.lon, "timezone": args.tz, "ayanamsa": args.ayanamsa},
        "on": args.on, "lagna_sign": asc["sign"], "mahadasha_lord": maha,
        "flagged": flagged,
    }


def render_text(r: dict) -> str:
    L = []
    A = L.append
    A("=" * 70)
    A("  TRADITIONAL REMEDIES (UPAYA)")
    A("=" * 70)
    A(f"  Lagna: {r['lagna_sign']}   |   Running Mahadasha: {r['mahadasha_lord']}   |   as of {r['on']}")
    A("  ⚠ TRADITION & CULTURE ONLY — not medical/financial/psychological advice,")
    A("    and no demonstrated effect. Do NOT buy gemstones on this basis.")
    A("-" * 70)
    if not r["flagged"]:
        A("  No planet flags as the dasha lord, debilitated, combust, or in a")
        A("  dusthana right now. Tradition would say: simply continue ishta-devata")
        A("  worship and charity on the relevant weekdays.")
    for f in r["flagged"]:
        rem = f["remedies"]
        A(f"\n  {f['planet'].upper()}  — {', '.join(f['reasons'])}")
        A(f"    Approach : {f['approach']}")
        A(f"    Deity    : {rem['deity']}")
        A(f"    Mantra   : {rem['mantra']}")
        A(f"    Gemstone : {rem['gem']}")
        A(f"    Day/Colour: {rem['day']} / {rem['colour']}   |   Metal: {rem['metal']}")
        A(f"    Charity  : {rem['daan']}")
    A("\n" + "=" * 70)
    A("  Gemstones (esp. blue sapphire, hessonite, cat's eye) must be TESTED before")
    A("  wearing in tradition; mantra, charity, and service carry no such risk.")
    A("  For cultural/educational use only.")
    A("=" * 70)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Traditional planetary remedies for weak/afflicted/dasha planets.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--on", default=date.today().isoformat(),
                    help="Date for the running-dasha check (default: today)")
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

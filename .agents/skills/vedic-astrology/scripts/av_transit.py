#!/usr/bin/env python3
"""av_transit.py — Ashtakavarga-weighted transit reading.

A planet's transit through a sign is judged in classical Vedic astrology by the
Ashtakavarga bindus that sign carries: the Sarvashtakavarga (SAV) total and the
transiting planet's own Bhinnashtakavarga (BAV). High bindus (SAV >= 30, or the
planet's BAV >= 4-5) make a transit supportive; low bindus (SAV <= 25) make it
strained. This script computes the natal Ashtakavarga, then for a chosen date
reports, for each transiting planet, the SAV and own-BAV of the sign it occupies.

Reuses strength.py's verified Ashtakavarga. For cultural/educational use only.
"""
import argparse
import json
from datetime import date

import core
from strength import compute_ashtakavarga


def _parse_time(t):
    parts = t.split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    return hh, mm, ss


def _rating(sav):
    if sav >= 30:
        return "supportive (high SAV)"
    if sav <= 25:
        return "strained (low SAV)"
    return "mixed"


def compute(args):
    core.init_engine(
        args.ayanamsa,
        node=getattr(args, "node", "mean"),
        topocentric=not getattr(args, "geocentric", False),
        lat=args.lat, lon=args.lon,
        ephemeris=getattr(args, "ephemeris", "moshier"),
    )
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    birth_jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)

    natal = core.all_planet_positions(birth_jd)
    asc = core.ascendant(birth_jd, args.lat, args.lon)
    av = compute_ashtakavarga(natal, asc["sign_num"])
    sav = av["sav"]["per_sign"]
    bav = av["bav"]

    oy, om, od = (int(x) for x in args.on.split("-"))
    # transit chart at noon of the chosen day (positions of slow planets barely move)
    import swisseph as swe
    tjd = swe.julday(oy, om, od, 6.5, swe.GREG_CAL)  # ~noon IST in UT
    transit = core.all_planet_positions(tjd)

    focus = args.planets.split(",") if args.planets else ["Jupiter", "Saturn", "Rahu", "Ketu"]
    rows = []
    for p in focus:
        p = p.strip().title()
        if p not in transit:
            continue
        s = transit[p]["sign_num"]
        own_bav = bav.get(p, {}).get("per_sign", [None] * 12)[s - 1] if p in bav else None
        rows.append({
            "planet": p,
            "transiting_sign": core.SIGNS[s - 1],
            "sav_bindu": sav[s - 1],
            "own_bav_bindu": own_bav,
            "rating": _rating(sav[s - 1]),
        })

    return {
        "input": {"date": args.date, "time": args.time, "lat": args.lat, "lon": args.lon,
                  "timezone": args.tz, "on": args.on, "ayanamsa": args.ayanamsa},
        "natal_sav_total": av["sav"]["total"],
        "transits": rows,
        "note": "SAV >= 30 supportive, <= 25 strained; a planet's own BAV >= 4 helps its "
                "own transit. Cultural/educational use only.",
    }


def render_text(r):
    o = []
    A = o.append
    A("=" * 62)
    A(f"  ASHTAKAVARGA TRANSIT — bindu strength on {r['input']['on']}")
    A("=" * 62)
    A(f"  Natal SAV total: {r['natal_sav_total']} (avg 28/sign)")
    A("-" * 62)
    A("  Planet    Transiting sign   SAV   own-BAV   Reading")
    A("  " + "-" * 54)
    for t in r["transits"]:
        bav = "-" if t["own_bav_bindu"] is None else str(t["own_bav_bindu"])
        A(f"  {t['planet']:<8}  {t['transiting_sign']:<14}  {t['sav_bindu']:>3}   {bav:>5}     {t['rating']}")
    A("=" * 62)
    A("  " + r["note"])
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser(description="Ashtakavarga-weighted transit reading.")
    ap.add_argument("--date", required=True, help="Birth date YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="Birth time HH:MM[:SS]")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--on", default=date.today().isoformat(), help="Transit date YYYY-MM-DD")
    ap.add_argument("--planets", default="", help="comma list (default Jupiter,Saturn,Rahu,Ketu)")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = compute(args)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result))


if __name__ == "__main__":
    main()

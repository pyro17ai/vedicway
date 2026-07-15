#!/usr/bin/env python3
"""chalit.py — Bhava Chalit (cusp-based house) chart.

Whole-sign houses (the Vedic default) equate one sign to one house. But a planet
near a sign edge can physically belong to the adjacent BHAVA once real house cusps
are drawn. This chart computes Placidus/Sripati cusps and assigns each planet to
the bhava whose cusp span actually contains it — then flags every planet whose
cusp-based house differs from its whole-sign house. Those are exactly the planets
whose house-based reading (career in the 10th, marriage in the 7th, ...) is most
sensitive to birth-time accuracy.

Use it to confirm a D1 house judgment before trusting it. For cultural/educational
use only.
"""
import argparse
import json
import sys

import core

ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th",
           7: "7th", 8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th"}


def _parse_time(t):
    parts = t.split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    return hh, mm, ss


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
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)

    asc = core.ascendant(jd, args.lat, args.lon)
    asc_sign = asc["sign_num"]
    cusps = core.house_cusps(jd, args.lat, args.lon, args.cusp_system)
    positions = core.all_planet_positions(jd)

    rows = []
    shifts = 0
    for name, info in positions.items():
        whole = core.house_of(info["sign_num"], asc_sign)
        chalit = core.bhava_of(info["longitude"], cusps)
        shifted = whole != chalit
        if shifted:
            shifts += 1
        rows.append({
            "planet": name,
            "sign": info["sign"],
            "degree_in_sign": info["degree_in_sign"],
            "whole_sign_house": whole,
            "chalit_house": chalit,
            "shifted": shifted,
        })

    return {
        "input": {
            "date": args.date, "time": args.time, "lat": args.lat, "lon": args.lon,
            "timezone": args.tz, "ayanamsa": args.ayanamsa,
            "cusp_system": args.cusp_system,
            "topocentric": not getattr(args, "geocentric", False),
        },
        "ascendant": asc,
        "cusps_deg": [round(c, 4) for c in cusps],
        "planets": rows,
        "shift_count": shifts,
    }


def render_text(r):
    out = []
    A = out.append
    A("=" * 60)
    A("  BHAVA CHALIT — cusp-based house chart")
    A("=" * 60)
    A(f"  Lagna: {r['ascendant']['sign']} {r['ascendant']['degree_in_sign']:.2f}deg"
      f"  |  cusps: {r['input']['cusp_system']}")
    A("-" * 60)
    A("  Planet    Sign         Deg     Whole-sign   Chalit    Shift")
    A("  " + "-" * 56)
    for p in r["planets"]:
        flag = "  <-- moved" if p["shifted"] else ""
        A(f"  {p['planet']:<8}  {p['sign']:<11}  {p['degree_in_sign']:>5.2f}   "
          f"{ORDINAL[p['whole_sign_house']]:<10}   {ORDINAL[p['chalit_house']]:<7}{flag}")
    A("  " + "-" * 56)
    if r["shift_count"]:
        moved = ", ".join(p["planet"] for p in r["planets"] if p["shifted"])
        A(f"  {r['shift_count']} planet(s) change house in the chalit chart: {moved}.")
        A("  Their house-based reading is birth-time sensitive — confirm the time.")
    else:
        A("  No planet changes house — whole-sign and chalit agree here.")
    A("=" * 60)
    A("  For cultural/educational use only. Not predictive of real outcomes.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Bhava Chalit (cusp-based house) chart.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--cusp-system", default="placidus", dest="cusp_system",
                    choices=["placidus", "equal"],
                    help="cusp scheme for the chalit chart (default placidus)")
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

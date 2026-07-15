#!/usr/bin/env python3
"""kp.py — Krishnamurti Paddhati (KP) sub-lords, cuspal sub-lords, ruling planets.

KP refines Vedic astrology with the SUB-LORD: each nakshatra is split into nine
unequal sub-parts in Vimshottari proportions, and the sub-lord of a point is the
single most decisive factor in KP. This script reports, for the natal moment:

  - Planetary sub-lords: each planet's Rashi lord -> Nakshatra (star) lord -> Sub lord.
  - Cuspal sub-lords (CSL): the sub-lord of each of the 12 Placidus house cusps —
    in KP the CSL decides whether that house's matters fructify.
  - Ruling Planets (RP): the lords in force at the moment (day lord, Moon's star &
    rashi lord, Lagna's star, rashi & sub lord) — KP's tool for timing & horary.

Uses Placidus cusps (the KP standard). For cultural/educational use only.
"""
import argparse
import json

import core



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

    positions = core.all_planet_positions(jd)
    planets = {}
    for name, info in positions.items():
        kp = core.kp_lords(info["longitude"])
        planets[name] = {
            "longitude": info["longitude"],
            "sign": kp["sign"],
            "rashi_lord": kp["rashi_lord"],
            "star_lord": kp["star_lord"],
            "sub_lord": kp["sub_lord"],
            "retrograde": info["retrograde"],
        }

    cusps = core.house_cusps(jd, args.lat, args.lon, "placidus")
    cuspal = []
    for i, c in enumerate(cusps, start=1):
        kp = core.kp_lords(c)
        cuspal.append({
            "house": i, "cusp_deg": round(c, 4), "sign": kp["sign"],
            "rashi_lord": kp["rashi_lord"], "star_lord": kp["star_lord"],
            "sub_lord": kp["sub_lord"],
        })

    # Ruling planets. The KP day lord follows the VEDIC day (sunrise-to-sunrise),
    # not the civil midnight weekday — a birth before sunrise belongs to the
    # previous weekday's lord.
    day_lord = core.WEEKDAY_LORD[core.vedic_vara(jd, args.lat, args.lon, args.tz)]
    moon_kp = core.kp_lords(positions["Moon"]["longitude"])
    asc = core.ascendant(jd, args.lat, args.lon)
    asc_kp = core.kp_lords(asc["longitude"])
    ruling = {
        "day_lord": day_lord,
        "moon_rashi_lord": moon_kp["rashi_lord"],
        "moon_star_lord": moon_kp["star_lord"],
        "moon_sub_lord": moon_kp["sub_lord"],
        "lagna_rashi_lord": asc_kp["rashi_lord"],
        "lagna_star_lord": asc_kp["star_lord"],
        "lagna_sub_lord": asc_kp["sub_lord"],
    }

    return {
        "input": {"date": args.date, "time": args.time, "lat": args.lat, "lon": args.lon,
                  "timezone": args.tz, "ayanamsa": args.ayanamsa, "cusps": "placidus"},
        "ascendant": {"sign": asc["sign"], "longitude": asc["longitude"],
                      "sub_lord": asc_kp["sub_lord"]},
        "planets": planets,
        "cuspal_sub_lords": cuspal,
        "ruling_planets": ruling,
        "note": "KP sub-lord = the decisive factor. Cuspal sub-lord (CSL) governs "
                "whether a house's matters fructify. Cultural/educational use only.",
    }


def render_text(r):
    o = []
    A = o.append
    A("=" * 66)
    A("  KRISHNAMURTI PADDHATI (KP) — sub-lords & ruling planets")
    A("=" * 66)
    A(f"  Lagna: {r['ascendant']['sign']}  (sub-lord {r['ascendant']['sub_lord']})")
    A("-" * 66)
    A("  Planet    Sign         RashiLord  StarLord   SubLord   R")
    A("  " + "-" * 58)
    for name, p in r["planets"].items():
        rr = "R" if p["retrograde"] else ""
        A(f"  {name:<8}  {p['sign']:<11}  {p['rashi_lord']:<9}  {p['star_lord']:<9}  "
          f"{p['sub_lord']:<8}  {rr}")
    A("-" * 66)
    A("  Cuspal sub-lords (the KP fructification key):")
    A("  Hse  Sign         RashiLord  StarLord   SubLord")
    A("  " + "-" * 54)
    for c in r["cuspal_sub_lords"]:
        A(f"  {c['house']:>2}   {c['sign']:<11}  {c['rashi_lord']:<9}  {c['star_lord']:<9}  {c['sub_lord']}")
    A("-" * 66)
    rp = r["ruling_planets"]
    A("  Ruling planets (for timing / horary):")
    A(f"    Day lord            : {rp['day_lord']}")
    A(f"    Moon  rashi/star/sub: {rp['moon_rashi_lord']} / {rp['moon_star_lord']} / {rp['moon_sub_lord']}")
    A(f"    Lagna rashi/star/sub: {rp['lagna_rashi_lord']} / {rp['lagna_star_lord']} / {rp['lagna_sub_lord']}")
    A("=" * 66)
    A("  For cultural/educational use only. Not predictive of real outcomes.")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser(description="KP sub-lords, cuspal sub-lords, ruling planets.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--ayanamsa", default="kp",
                    help="default 'kp' (KP-Newcomb); use 'lahiri' to match the rest of the skill")
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

#!/usr/bin/env python3
"""
kundli.py — Compute a Vedic birth chart (D1 Rashi chart).

Outputs planetary sidereal positions, signs, whole-sign houses, the Lagna
(ascendant), and each planet's nakshatra + pada, plus retrograde flags.

Usage:
    python kundli.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--ayanamsa lahiri] [--house-system whole_sign] [--json]

All angles are sidereal. Default ayanamsa = Lahiri.
"""

from __future__ import annotations

import argparse
import json
import sys

import core


def compute_kundli(args) -> dict:
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

    asc = core.ascendant(jd, args.lat, args.lon, args.house_system)
    asc_sign_num = asc["sign_num"]

    planets = core.all_planet_positions(jd)
    sun_lon = planets["Sun"]["longitude"]
    for name, info in planets.items():
        info["house"] = core.house_of(info["sign_num"], asc_sign_num)
        info["dignity"] = core.dignity(name, info["sign_num"])
        info["vargottama"] = core.is_vargottama(info["longitude"])
        info["navamsa_sign"] = core.SIGNS[info["navamsa_sign_num"] - 1]
        info["combust"] = (
            False if name in ("Sun", "Rahu", "Ketu")
            else core.is_combust(name, info["longitude"], sun_lon, info["retrograde"])
        )

    return {
        "input": {
            "date": args.date, "time": args.time, "lat": args.lat,
            "lon": args.lon, "timezone": args.tz,
            "ayanamsa": args.ayanamsa, "house_system": args.house_system,
            "node": getattr(args, "node", "mean"),
            "topocentric": not getattr(args, "geocentric", False),
        },
        "julian_day_ut": round(jd, 6),
        "ayanamsa_deg": round(core.ayanamsa_value(jd), 6),
        "ascendant": asc,
        "planets": planets,
        "western_sun_sign": core.western_sun_sign(jd),
    }


def _parse_time(t: str):
    parts = t.split(":")
    hh = int(parts[0]); mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    return hh, mm, ss


def render_text(result: dict) -> str:
    asc = result["ascendant"]
    lines = []
    lines.append("=" * 60)
    lines.append("  KUNDLI — Vedic Birth Chart (D1 Rashi)")
    lines.append("=" * 60)
    i = result["input"]
    lines.append(f"  Born: {i['date']} {i['time']} ({i['timezone']})")
    lines.append(f"  Place: lat {i['lat']}, lon {i['lon']}")
    frame = "topocentric" if i.get("topocentric") else "geocentric"
    lines.append(f"  Ayanamsa: {i['ayanamsa'].title()} ({result.get('ayanamsa_deg')}°) "
                 f"| Houses: {i['house_system']} | {frame} | {i.get('node','mean')}-node")
    lines.append("-" * 60)
    lines.append(f"  Lagna (Ascendant): {asc['sign']} "
                 f"{core.deg_to_dms(asc['degree_in_sign'])} "
                 f"| {asc['nakshatra']} pada {asc['pada']}")
    if result.get("western_sun_sign"):
        lines.append(f"  Western (tropical) Sun sign: {result['western_sun_sign']}  "
                     f"(popular 'star sign' — tropical zodiac, differs from the "
                     f"sidereal Vedic chart)")
    lines.append("-" * 60)
    header = (f"  {'Planet':<9}{'Sign':<12}{'Deg':<10}{'Ho':<4}"
              f"{'Nakshatra':<16}{'Pd':<4}{'D9':<12}{'Dignity':<12}{'Flags'}")
    lines.append(header)
    lines.append("  " + "-" * 72)
    order = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
    for name in order:
        p = result["planets"][name]
        tag = name + ("(R)" if p["retrograde"] and name not in ("Rahu", "Ketu") else "")
        flags = []
        if p.get("combust"):
            flags.append("combust")
        if p.get("vargottama"):
            flags.append("vargottama")
        lines.append(
            f"  {tag:<9}{p['sign']:<12}{core.deg_to_dms(p['degree_in_sign']):<10}"
            f"{p['house']:<4}{p['nakshatra']:<16}{p['pada']:<4}"
            f"{p.get('navamsa_sign',''):<12}{p['dignity']:<12}{', '.join(flags)}"
        )
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Compute a Vedic birth chart (kundli).")
    ap.add_argument("--date", required=True, help="Birth date YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="Birth time HH:MM[:SS], 24h local")
    ap.add_argument("--lat", type=float, required=True, help="Latitude (deg, N positive)")
    ap.add_argument("--lon", type=float, required=True, help="Longitude (deg, E positive)")
    ap.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--house-system", default=core.DEFAULT_HOUSE_SYSTEM, dest="house_system")
    ap.add_argument("--node", default="mean", choices=["mean", "true"],
                    help="Lunar node model for Rahu/Ketu (default mean)")
    ap.add_argument("--geocentric", action="store_true",
                    help="Use geocentric positions (default is topocentric)")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"],
                    help="moshier=offline (default), swiss=requires .se1 files")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    try:
        result = compute_kundli(args)
    except Exception as e:  # noqa: BLE001 — surface a clean message to the agent
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""transit_timeline.py — slow-planet ingress timeline over a date range.

gochar.py answers "where are the transits right now". This answers "what changes
across the next N months/years": it finds the exact dates the slow, classically
weighted planets (Jupiter, Saturn, Rahu, Ketu) change sign within a range, the
house each enters counted from the natal Moon (the gochar reference), and flags
Sade Sati / Dhaiya phases. Ingress = a planet's sidereal longitude crossing a 30°
sign boundary; the exact instant is found by bisection.

Pair with dasha for the backdrop and gochar for the present snapshot. For
cultural/educational use only.
"""
import argparse
import json
from datetime import date

import swisseph as swe

import core

SLOW = ["Jupiter", "Saturn", "Rahu", "Ketu"]
ORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th",
       8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th"}
SADE_DHAIYA = {12: "Sade Sati (rising)", 1: "Sade Sati (peak)", 2: "Sade Sati (setting)",
               4: "Dhaiya (Ardhashtama)", 8: "Dhaiya (Ashtama)"}


def _parse_time(t):
    parts = t.split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    return hh, mm, ss


def _lon(jd, planet):
    if planet == "Ketu":
        l, _ = core.sidereal_longitude(jd, core.PLANETS["Rahu"])
        return (l + 180.0) % 360.0
    l, _ = core.sidereal_longitude(jd, core.PLANETS[planet])
    return l


def _sign(jd, planet):
    return int(_lon(jd, planet) // 30) + 1


def _bisect_ingress(planet, jd_lo, jd_hi):
    """Refine the ingress instant between two days that straddle a sign change."""
    s_lo = _sign(jd_lo, planet)
    for _ in range(40):
        mid = (jd_lo + jd_hi) / 2.0
        if _sign(mid, planet) == s_lo:
            jd_lo = mid
        else:
            jd_hi = mid
    return jd_hi


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
    moon_sign = natal["Moon"]["sign_num"]

    fy, fm, fd = (int(x) for x in args.start.split("-"))
    ty, tm, td = (int(x) for x in args.end.split("-"))
    jd_start = swe.julday(fy, fm, fd, 12.0, swe.GREG_CAL)
    jd_end = swe.julday(ty, tm, td, 12.0, swe.GREG_CAL)
    if jd_end <= jd_start:
        raise SystemExit("--end must be after --start")

    events = []
    for planet in SLOW:
        prev = jd_start
        prev_sign = _sign(prev, planet)
        jd = jd_start + 1.0
        while jd <= jd_end:
            s = _sign(jd, planet)
            if s != prev_sign:
                exact = _bisect_ingress(planet, prev, jd)
                t_sign = _sign(exact, planet)
                h = core.house_of(t_sign, moon_sign)
                ev = {
                    "planet": planet,
                    "date_local": core.jd_to_local(exact, args.tz).date().isoformat(),
                    "enters_sign": core.SIGNS[t_sign - 1],
                    "house_from_moon": h,
                }
                if planet == "Saturn" and h in SADE_DHAIYA:
                    ev["phase"] = SADE_DHAIYA[h]
                events.append(ev)
                prev_sign = s
            prev = jd
            jd += 1.0

    events.sort(key=lambda e: e["date_local"])
    return {
        "input": {"date": args.date, "time": args.time, "lat": args.lat, "lon": args.lon,
                  "timezone": args.tz, "start": args.start, "end": args.end,
                  "ayanamsa": args.ayanamsa},
        "natal_moon_sign": core.SIGNS[moon_sign - 1],
        "ingress_events": events,
    }


def render_text(r):
    o = []
    A = o.append
    A("=" * 64)
    A("  TRANSIT TIMELINE — slow-planet ingresses (house from natal Moon)")
    A("=" * 64)
    A(f"  Natal Moon: {r['natal_moon_sign']}   |   "
      f"{r['input']['start']} -> {r['input']['end']}")
    A("-" * 64)
    if not r["ingress_events"]:
        A("  No slow-planet sign changes in this range.")
    for e in r["ingress_events"]:
        ph = f"   [{e['phase']}]" if "phase" in e else ""
        A(f"  {e['date_local']}  {e['planet']:<8} enters {e['enters_sign']:<11}"
          f" ({ORD[e['house_from_moon']]} from Moon){ph}")
    A("=" * 64)
    A("  Pair with dasha (backdrop) and gochar (now). Cultural/educational use only.")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser(description="Slow-planet transit ingress timeline over a range.")
    ap.add_argument("--date", required=True, help="Birth date YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="Birth time HH:MM[:SS]")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--start", default=date.today().isoformat(), help="Range start YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="Range end YYYY-MM-DD")
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

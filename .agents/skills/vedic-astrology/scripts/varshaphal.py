#!/usr/bin/env python3
"""varshaphal.py — Tajika annual chart (Varsha Pravesh / solar return).

The Varshaphal is the chart for the exact moment the transiting Sun returns to its
natal sidereal longitude in a chosen year of life. It is the classical basis for a
"what about THIS year" reading. This script:

  - finds the solar-return instant by root-finding Sun's sidereal longitude,
  - casts the annual ascendant and planetary positions for that instant,
  - computes the Muntha (a progressed point that advances one sign per year from
    the natal Lagna) and its lord,
  - lists the five Tajika year-lord (Varshesha) office-bearers.

Honesty note: the final Varshesha is chosen by Panchavargeeya Bala, a weighting
this script does NOT fully reproduce — it lists the five candidates and their
basis and marks the Muntha-lord as the conventional first consideration. Treat the
Varshesha here as "candidates", not a verdict. For cultural/educational use only.
"""
import argparse
import json

import swisseph as swe

import core

SIGN_LORD = {1: "Mars", 2: "Venus", 3: "Mercury", 4: "Moon", 5: "Sun", 6: "Mercury",
             7: "Venus", 8: "Mars", 9: "Jupiter", 10: "Saturn", 11: "Saturn", 12: "Jupiter"}


def _parse_time(t):
    parts = t.split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    return hh, mm, ss


def _sun_lon(jd):
    lon, _ = core.sidereal_longitude(jd, core.PLANETS["Sun"])
    return lon


def _signed_diff(jd, target):
    """Sun longitude minus target, wrapped to (-180, 180]."""
    return ((_sun_lon(jd) - target + 180.0) % 360.0) - 180.0


def find_solar_return(natal_sun, year, month, day):
    """Julian Day (UT) when the Sun next sits on natal_sun, near the given date."""
    jd0 = swe.julday(year, month, day, 0.0, swe.GREG_CAL)
    lo, hi = jd0 - 3.0, jd0 + 3.0
    # Expand window until the signed difference brackets a rising zero crossing.
    for _ in range(8):
        if _signed_diff(lo, natal_sun) <= 0 <= _signed_diff(hi, natal_sun):
            break
        lo -= 2.0
        hi += 2.0
    # Bisection (Sun is monotonic prograde, ~0.986 deg/day -> single root).
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _signed_diff(mid, natal_sun) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


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

    natal_sun = _sun_lon(birth_jd)
    natal_asc = core.ascendant(birth_jd, args.lat, args.lon)
    natal_asc_sign = natal_asc["sign_num"]

    age = int(args.age)
    return_year = y + age
    ret_jd = find_solar_return(natal_sun, return_year, m, d)

    # Annual chart at the (optionally different) residence location.
    a_lat = args.res_lat if args.res_lat is not None else args.lat
    a_lon = args.res_lon if args.res_lon is not None else args.lon
    a_asc = core.ascendant(ret_jd, a_lat, a_lon)
    a_asc_sign = a_asc["sign_num"]
    positions = core.all_planet_positions(ret_jd)
    for name, info in positions.items():
        info["house"] = core.house_of(info["sign_num"], a_asc_sign)
        info["dignity"] = core.dignity(name, info["sign_num"])

    # Muntha: advances one sign per year from the natal Lagna.
    muntha_sign = ((natal_asc_sign - 1 + age) % 12) + 1
    muntha_lord = SIGN_LORD[muntha_sign]
    muntha_house = core.house_of(muntha_sign, a_asc_sign)

    # Five Tajika office-bearers (Varshesha candidates).
    tz_name = args.tz
    ret_local = core.jd_to_local(ret_jd, tz_name)
    is_day = 6 <= ret_local.hour < 18  # crude day/night by local clock
    candidates = {
        "Muntha lord": muntha_lord,
        "Varsha Lagna lord (annual ascendant)": SIGN_LORD[a_asc_sign],
        "Janma Lagna lord (natal ascendant)": SIGN_LORD[natal_asc_sign],
        "Tri-rashi lord": SIGN_LORD[a_asc_sign],   # simplified: lord of the rising sign's trinal set
        "Dina-Ratri lord": ("Sun" if is_day else "Moon"),
    }

    return {
        "input": {
            "date": args.date, "time": args.time, "lat": args.lat, "lon": args.lon,
            "timezone": tz_name, "age": age, "return_year": return_year,
            "ayanamsa": args.ayanamsa,
            "residence_lat": a_lat, "residence_lon": a_lon,
        },
        "natal": {"sun_longitude": round(natal_sun, 4),
                  "ascendant": natal_asc["sign"], "ascendant_sign_num": natal_asc_sign},
        "solar_return": {
            "julian_day_ut": round(ret_jd, 6),
            "local_time": ret_local.isoformat(),
            "sun_longitude_check": round(_sun_lon(ret_jd), 4),
        },
        "annual_chart": {
            "ascendant": a_asc, "planets": positions,
        },
        "muntha": {"sign": core.SIGNS[muntha_sign - 1], "sign_num": muntha_sign,
                   "lord": muntha_lord, "house_in_annual_chart": muntha_house},
        "varshesha_candidates": candidates,
        "method_notes": [
            "Solar return = exact sidereal Sun return to natal longitude (bisection).",
            "Muntha advances one sign per year of age from the natal Lagna.",
            "Varshesha (year lord) is finalised by Panchavargeeya Bala, NOT fully "
            "computed here; the five office-bearers are listed as candidates.",
        ],
    }


def render_text(r):
    o = []
    A = o.append
    A("=" * 60)
    A(f"  VARSHAPHAL — Tajika annual chart (age {r['input']['age']}, "
      f"year {r['input']['return_year']})")
    A("=" * 60)
    A(f"  Solar return (local): {r['solar_return']['local_time']}")
    A(f"  Annual Lagna: {r['annual_chart']['ascendant']['sign']} "
      f"{r['annual_chart']['ascendant']['degree_in_sign']:.2f}deg")
    A(f"  Muntha: {r['muntha']['sign']} (lord {r['muntha']['lord']}), "
      f"house {r['muntha']['house_in_annual_chart']} of the annual chart")
    A("-" * 60)
    A("  Planet    Sign         Deg    Hse  Dignity")
    A("  " + "-" * 50)
    for name, p in r["annual_chart"]["planets"].items():
        A(f"  {name:<8}  {p['sign']:<11}  {p['degree_in_sign']:>5.2f}  {p['house']:>2}   {p['dignity']}")
    A("  " + "-" * 50)
    A("  Varshesha (year-lord) candidates:")
    for office, planet in r["varshesha_candidates"].items():
        A(f"    - {office}: {planet}")
    A("-" * 60)
    for n in r["method_notes"]:
        A("  * " + n)
    A("=" * 60)
    A("  For cultural/educational use only. Not predictive of real outcomes.")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser(description="Tajika annual chart (Varshaphal / solar return).")
    ap.add_argument("--date", required=True, help="Birth date YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="Birth time HH:MM[:SS]")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--age", type=int, required=True, help="Year of life to cast (completed years)")
    ap.add_argument("--res-lat", type=float, default=None, dest="res_lat",
                    help="Residence latitude for the annual chart (default = birth lat)")
    ap.add_argument("--res-lon", type=float, default=None, dest="res_lon")
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

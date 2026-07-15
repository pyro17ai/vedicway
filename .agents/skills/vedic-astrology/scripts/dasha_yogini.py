#!/usr/bin/env python3
"""
dasha_yogini.py — Compute the Yogini Dasha timeline from birth.

The Yogini Dasha is a **36-year** cycle of eight Yoginis, each ruled by a planet
and lasting a fixed number of years (1+2+...+8 = 36). It is a popular companion
to the Vimshottari (120-year) system — cross-read the two for timing.

  #  Yogini    Lord      Years
  1  Mangala   Moon      1
  2  Pingala   Sun       2
  3  Dhanya    Jupiter   3
  4  Bhramari  Mars      4
  5  Bhadrika  Mercury   5
  6  Ulka      Saturn    6
  7  Siddha    Venus     7
  8  Sankata   Rahu      8

Starting Yogini: (janma-nakshatra number + 3) mod 8 (a remainder of 0 = the 8th,
Sankata). The balance of the first period is the unspent fraction of the birth
nakshatra — exactly as in Vimshottari. The sequence then cycles in order.

Usage:
    python dasha_yogini.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--ayanamsa lahiri] [--levels 2] [--years 108] [--json]

--levels 1 => Mahadasha only; 2 => Mahadasha + Antardasha (default).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

import core

# Classical jyotish uses 365.25 days/year for dasha proportioning.
DAYS_PER_YEAR = 365.25

# The eight Yoginis in order, with ruling planet and length in years.
YOGINIS = [
    {"yogini": "Mangala", "lord": "Moon", "years": 1},
    {"yogini": "Pingala", "lord": "Sun", "years": 2},
    {"yogini": "Dhanya", "lord": "Jupiter", "years": 3},
    {"yogini": "Bhramari", "lord": "Mars", "years": 4},
    {"yogini": "Bhadrika", "lord": "Mercury", "years": 5},
    {"yogini": "Ulka", "lord": "Saturn", "years": 6},
    {"yogini": "Siddha", "lord": "Venus", "years": 7},
    {"yogini": "Sankata", "lord": "Rahu", "years": 8},
]
CYCLE_YEARS = sum(y["years"] for y in YOGINIS)   # 36

# Short, plain-language temperament of each Yogini (cultural tradition).
YOGINI_NOTE = {
    "Mangala": "auspicious beginnings, ease and good fortune",
    "Pingala": "drive and visibility, but some friction with authority",
    "Dhanya": "wisdom, learning, and steady fortune",
    "Bhramari": "movement, energy, travel and change",
    "Bhadrika": "communication, trade, and quick intelligence",
    "Ulka": "delays and hard lessons that build resilience",
    "Siddha": "comfort, success, and fulfilment",
    "Sankata": "obstacles and upheaval that test, then transform",
}


def _fmt_day(dt: datetime) -> str:
    """Round to the NEAREST day so a boundary at 23:00 doesn't show as the
    previous date; adjacent periods share the cursor, so end == next start."""
    return (dt + timedelta(hours=12)).strftime("%Y-%m-%d")


def _moon_nakshatra_fraction(jd: float) -> tuple[int, float, float]:
    """Return (nakshatra_index 0..26, fraction_elapsed 0..1, moon_longitude)."""
    moon_lon, _ = core.sidereal_longitude(jd, core.PLANETS["Moon"])
    nak_index = int(moon_lon // core.NAKSHATRA_SPAN)
    fraction = (moon_lon % core.NAKSHATRA_SPAN) / core.NAKSHATRA_SPAN
    return nak_index, fraction, moon_lon


def _starting_index(nak_index: int) -> int:
    """0-based index into YOGINIS of the Yogini ruling at birth.

    Classical rule: (janma-nakshatra number + 3) mod 8, with a remainder of 0
    denoting the 8th Yogini (Sankata). nak_index is 0-based, so the nakshatra
    number is nak_index + 1.
    """
    nak_num = nak_index + 1
    r = (nak_num + 3) % 8           # 0..7, where 0 means the 8th Yogini
    return (r - 1) % 8             # -> 0..7 index (0 maps to 7 = Sankata)


def _sequence_from(start_idx: int, count: int) -> list[int]:
    """`count` Yogini indices cycling from start_idx."""
    return [(start_idx + i) % 8 for i in range(count)]


def _subperiods(maha_idx: int, start_dt: datetime, maha_years: float,
                levels: int) -> list[dict]:
    """Divide a period into 8 sub-periods proportional to Yogini years.

    Sub-period length = parent_years * (sub_yogini_years / 36).
    """
    subs = []
    cursor = start_dt
    for idx in _sequence_from(maha_idx, 8):
        y = YOGINIS[idx]
        sub_years = maha_years * (y["years"] / CYCLE_YEARS)
        end = cursor + timedelta(days=sub_years * DAYS_PER_YEAR)
        node = {
            "yogini": y["yogini"],
            "lord": y["lord"],
            "start": _fmt_day(cursor),
            "end": _fmt_day(end),
            "years": round(sub_years, 3),
        }
        if levels >= 3:
            node["pratyantardashas"] = _subperiods(idx, cursor, sub_years, levels - 1)
        subs.append(node)
        cursor = end
    return subs


def compute_yogini_dasha(args) -> dict:
    core.init_engine(
        args.ayanamsa,
        node=getattr(args, "node", "mean"),
        topocentric=not getattr(args, "geocentric", False),
        lat=args.lat, lon=args.lon,
        ephemeris=getattr(args, "ephemeris", "moshier"),
    )
    y, m, d = (int(x) for x in args.date.split("-"))
    parts = args.time.split(":")
    hh = int(parts[0]); mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)

    nak_index, fraction, moon_lon = _moon_nakshatra_fraction(jd)
    start_idx = _starting_index(nak_index)

    import swisseph as swe
    yy, mo, dd, ut_hour = swe.revjul(jd, swe.GREG_CAL)
    birth_dt = datetime(yy, mo, dd) + timedelta(hours=ut_hour)

    # Balance of the first Yogini = unspent fraction of the birth nakshatra.
    first = YOGINIS[start_idx]
    balance_years = first["years"] * (1.0 - fraction)

    # Roll forward enough Yoginis to cover the requested span.
    n_periods = 1
    acc = balance_years
    while acc < args.years:
        acc += YOGINIS[(start_idx + n_periods) % 8]["years"]
        n_periods += 1

    periods = []
    cursor = birth_dt
    for i, idx in enumerate(_sequence_from(start_idx, n_periods)):
        yog = YOGINIS[idx]
        span_years = balance_years if i == 0 else yog["years"]
        end = cursor + timedelta(days=span_years * DAYS_PER_YEAR)
        entry = {
            "yogini": yog["yogini"],
            "lord": yog["lord"],
            "start": _fmt_day(cursor),
            "end": _fmt_day(end),
            "years": round(span_years, 3),
            "note": YOGINI_NOTE[yog["yogini"]],
        }
        if args.levels >= 2:
            entry["antardashas"] = _subperiods(idx, cursor, span_years, args.levels)
        periods.append(entry)
        cursor = end

    return {
        "input": {
            "date": args.date, "time": args.time, "lat": args.lat,
            "lon": args.lon, "timezone": args.tz, "ayanamsa": args.ayanamsa,
        },
        "system": "Yogini Dasha",
        "cycle_years": CYCLE_YEARS,
        "moon_longitude": round(moon_lon, 4),
        "moon_nakshatra": core.NAKSHATRAS[nak_index],
        "starting_yogini": first["yogini"],
        "starting_lord": first["lord"],
        "balance_at_birth_years": round(balance_years, 3),
        "mahadashas": periods,
        "disclaimer": (
            "Yogini Dasha is a 36-year timing system best read ALONGSIDE the "
            "Vimshottari dasha and current transits, never alone. For cultural "
            "and educational use only — not a prediction of real outcomes."
        ),
    }


def render_text(result: dict) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("  YOGINI DASHA  (36-year cycle)")
    lines.append("=" * 60)
    lines.append(f"  Moon nakshatra: {result['moon_nakshatra']} "
                 f"(lon {result['moon_longitude']}°)")
    lines.append(f"  Starting Yogini: {result['starting_yogini']} "
                 f"({result['starting_lord']}) | balance at birth: "
                 f"{result['balance_at_birth_years']} yrs")
    lines.append("-" * 60)
    for md in result["mahadashas"]:
        lines.append(f"  {md['yogini']:<9} ({md['lord']:<7}) "
                     f"{md['start']} → {md['end']}  ({md['years']} yrs)")
        for ad in md.get("antardashas", []):
            lines.append(f"        ↳ {ad['yogini']:<9} ({ad['lord']:<7}) "
                         f"{ad['start']} → {ad['end']}")
    lines.append("-" * 60)
    lines.append("  " + result["disclaimer"])
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Compute Yogini dasha periods (36-year cycle).")
    ap.add_argument("--date", required=True, help="Birth date YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="Birth time HH:MM[:SS], 24h local")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--levels", type=int, default=2, choices=[1, 2, 3],
                    help="1=Mahadasha, 2=+Antardasha (default), 3=+Pratyantardasha")
    ap.add_argument("--years", type=float, default=108.0,
                    help="How many years from birth to project (default 108 = 3 cycles)")
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true",
                    help="Use geocentric positions (default is topocentric)")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        result = compute_yogini_dasha(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

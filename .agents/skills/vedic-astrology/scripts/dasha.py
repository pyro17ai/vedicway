#!/usr/bin/env python3
"""
dasha.py — Compute the Vimshottari Dasha timeline from birth.

The Vimshottari system is a 120-year cycle. The starting Mahadasha and the
balance of that first period are derived from the Moon's exact position within
its nakshatra at birth. We then roll forward through the 9-planet sequence and,
for each Mahadasha, sub-divide it into Antardashas (bhuktis).

Usage:
    python dasha.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--ayanamsa lahiri] [--levels 2] [--json]

--levels 1 => Mahadasha only; 2 => Mahadasha + Antardasha (default).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

import core

# A sidereal/tropical solar year length used for dasha arithmetic. Classical
# jyotish uses 365.25 days/year for Vimshottari proportioning.
DAYS_PER_YEAR = 365.25


def _fmt_day(dt: datetime) -> str:
    """Format a datetime rounded to the NEAREST day (not floored), so a boundary
    at 23:00 doesn't display as the previous calendar date. Adjacent periods
    share the same cursor value, so end-of-one == start-of-next stays consistent."""
    return (dt + timedelta(hours=12)).strftime("%Y-%m-%d")


def _moon_nakshatra_fraction(jd: float) -> tuple[int, float, float]:
    """Return (nakshatra_index 0..26, fraction_elapsed 0..1, moon_longitude)."""
    moon_lon, _ = core.sidereal_longitude(jd, core.PLANETS["Moon"])
    nak_index = int(moon_lon // core.NAKSHATRA_SPAN)
    pos_in_nak = moon_lon % core.NAKSHATRA_SPAN
    fraction = pos_in_nak / core.NAKSHATRA_SPAN
    return nak_index, fraction, moon_lon


def _sequence_from(lord: str) -> list[str]:
    """Return the 9-planet dasha order starting at `lord`."""
    start = core.DASHA_SEQUENCE.index(lord)
    return [core.DASHA_SEQUENCE[(start + i) % 9] for i in range(9)]


def compute_dasha(args) -> dict:
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
    start_lord = core.DASHA_SEQUENCE[nak_index % 9]

    # Birth as a naive UTC datetime for adding day-deltas. We reconstruct from jd
    # via Swiss Ephemeris to keep a single source of truth.
    import swisseph as swe
    yy, mo, dd, ut_hour = swe.revjul(jd, swe.GREG_CAL)
    birth_dt = datetime(yy, mo, dd) + timedelta(hours=ut_hour)

    # Balance of the first Mahadasha = remaining fraction of that nakshatra.
    full_years = core.DASHA_YEARS[start_lord]
    elapsed_years = fraction * full_years
    balance_years = full_years - elapsed_years

    sequence = _sequence_from(start_lord)
    periods = []
    cursor = birth_dt
    for i, lord in enumerate(sequence):
        span_years = balance_years if i == 0 else core.DASHA_YEARS[lord]
        end = cursor + timedelta(days=span_years * DAYS_PER_YEAR)
        entry = {
            "lord": lord,
            "start": _fmt_day(cursor),
            "end": _fmt_day(end),
            "years": round(span_years, 3),
        }
        if args.levels >= 2:
            entry["antardashas"] = _antardashas(lord, cursor, span_years, args.levels)
        periods.append(entry)
        cursor = end

    return {
        "input": {
            "date": args.date, "time": args.time, "lat": args.lat,
            "lon": args.lon, "timezone": args.tz, "ayanamsa": args.ayanamsa,
        },
        "moon_longitude": round(moon_lon, 4),
        "moon_nakshatra": core.NAKSHATRAS[nak_index],
        "starting_dasha": start_lord,
        "balance_at_birth_years": round(balance_years, 3),
        "mahadashas": periods,
    }


def _antardashas(maha_lord: str, start_dt: datetime, maha_years: float,
                 levels: int = 2) -> list[dict]:
    """Sub-divide a period into 9 sub-periods, proportional to dasha years.

    Used recursively: Antardasha = Mahadasha/9, Pratyantardasha = Antardasha/9.
    Sub-period length = parent_years * (sub_lord_years / 120).
    """
    subs = []
    cursor = start_dt
    for sub_lord in _sequence_from(maha_lord):
        sub_years = maha_years * (core.DASHA_YEARS[sub_lord] / 120.0)
        end = cursor + timedelta(days=sub_years * DAYS_PER_YEAR)
        node = {
            "lord": sub_lord,
            "start": _fmt_day(cursor),
            "end": _fmt_day(end),
            "years": round(sub_years, 3),
        }
        if levels >= 3:
            node["pratyantardashas"] = _antardashas(sub_lord, cursor, sub_years, levels - 1)
        subs.append(node)
        cursor = end
    return subs


def render_text(result: dict) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("  VIMSHOTTARI DASHA")
    lines.append("=" * 60)
    lines.append(f"  Moon nakshatra: {result['moon_nakshatra']} "
                 f"(lon {result['moon_longitude']}°)")
    lines.append(f"  Starting Mahadasha: {result['starting_dasha']} "
                 f"| balance at birth: {result['balance_at_birth_years']} yrs")
    lines.append("-" * 60)
    for md in result["mahadashas"]:
        lines.append(f"  {md['lord']:<9} {md['start']} → {md['end']}  ({md['years']} yrs)")
        for ad in md.get("antardashas", []):
            lines.append(f"        ↳ {ad['lord']:<9} {ad['start']} → {ad['end']}")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Compute Vimshottari dasha periods.")
    ap.add_argument("--date", required=True, help="Birth date YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="Birth time HH:MM[:SS], 24h local")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--levels", type=int, default=2, choices=[1, 2, 3],
                    help="1=Mahadasha, 2=+Antardasha (default), 3=+Pratyantardasha")
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true",
                    help="Use geocentric positions (default is topocentric)")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        result = compute_dasha(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

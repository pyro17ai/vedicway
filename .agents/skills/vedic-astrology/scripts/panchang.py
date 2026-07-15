#!/usr/bin/env python3
"""
panchang.py — Compute the five limbs (panch-anga) of the Vedic almanac.

The five limbs:
  1. Tithi    — lunar day, from the Moon-Sun elongation (12° each, 30 tithis).
  2. Nakshatra— lunar mansion the Moon occupies (13°20' each, 27 nakshatras).
  3. Yoga     — from (Sun + Moon) longitude (13°20' each, 27 yogas).
  4. Karana   — half-tithi (60 per lunar month, 11 repeating types).
  5. Vara     — weekday.

Tithi uses the Moon-minus-Sun difference, so it is ayanamsa-independent.
Nakshatra and Yoga use sidereal longitudes, so the ayanamsa matters; we compute
them in the configured sidereal frame for internal consistency.

Usage:
    python panchang.py --date 2026-06-04 --time 06:00:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--ayanamsa lahiri] [--json]

Note: tithi/nakshatra/yoga/karana change through the day; this reports the
value at the given clock time (default noon if --time omitted).
"""

from __future__ import annotations

import argparse
import json
import sys

import core

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]

# 30 tithi names within a lunar month (Shukla 1-15 then Krishna 1-15).
TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
    "Trayodashi", "Chaturdashi", "Purnima",
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
    "Trayodashi", "Chaturdashi", "Amavasya",
]

YOGA_NAMES = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
    "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
    "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva",
    "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti",
]

# Karana: 7 movable karanas repeat, plus 4 fixed ones around new moon.
MOVABLE_KARANAS = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]
FIXED_KARANAS = ["Shakuni", "Chatushpada", "Naga", "Kimstughna"]

# Which 1-of-8 daytime segment each inauspicious period falls in, by weekday.
# Daytime (sunrise->sunset) is split into 8 equal parts; segment 1 = first part.
RAHU_KAAL_SEG = {"Sunday": 8, "Monday": 2, "Tuesday": 7, "Wednesday": 5,
                 "Thursday": 6, "Friday": 4, "Saturday": 3}
YAMAGANDA_SEG = {"Sunday": 5, "Monday": 4, "Tuesday": 3, "Wednesday": 2,
                 "Thursday": 1, "Friday": 7, "Saturday": 6}
GULIKA_SEG = {"Sunday": 7, "Monday": 6, "Tuesday": 5, "Wednesday": 4,
              "Thursday": 3, "Friday": 2, "Saturday": 1}


def _karana_name(index: int) -> str:
    """index in 0..59 (two karanas per tithi). Maps to the classical scheme."""
    if index == 0:
        return "Kimstughna"          # first half of Shukla Pratipada
    if index >= 57:
        return FIXED_KARANAS[index - 57]  # Shakuni, Chatushpada, Naga
    return MOVABLE_KARANAS[(index - 1) % 7]


def compute_panchang(args) -> dict:
    core.init_engine(args.ayanamsa)
    y, m, d = (int(x) for x in args.date.split("-"))
    t = args.time or "12:00:00"
    parts = t.split(":")
    hh = int(parts[0]); mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)

    sun_lon, _ = core.sidereal_longitude(jd, core.PLANETS["Sun"])
    moon_lon, _ = core.sidereal_longitude(jd, core.PLANETS["Moon"])

    # 1. Tithi — elongation of Moon from Sun (ayanamsa cancels in the difference).
    elong = (moon_lon - sun_lon) % 360.0
    tithi_index = int(elong // 12)                 # 0..29
    paksha = "Shukla" if tithi_index < 15 else "Krishna"

    # 2. Nakshatra — Moon's sidereal mansion.
    nak_index = int(moon_lon // core.NAKSHATRA_SPAN)

    # 3. Yoga — (Sun + Moon) longitude.
    yoga_total = (sun_lon + moon_lon) % 360.0
    yoga_index = int(yoga_total // core.NAKSHATRA_SPAN)

    # 4. Karana — half-tithi.
    karana_index = int(elong // 6) % 60            # 0..59

    # 5. Vara — sunrise-to-sunrise weekday (Vedic convention).
    weekday = core.vedic_vara(jd, args.lat, args.lon, args.tz)

    # Sunrise/sunset + day periods (Rahu Kaal etc.). Anchor on the SAME Vedic day
    # used for the Vara — the sunrise that opens the day containing `jd` — so the
    # weekday label and its Rahu-Kaal segment never disagree (matters for a clock
    # time before sunrise, whose Vedic day began at the previous sunrise).
    opening_sunrise = core.sunrise_before(jd, args.lat, args.lon)
    if opening_sunrise is not None:
        sunrise_jd, sunset_jd = core.next_rise_set(opening_sunrise - 0.05, args.lat, args.lon)
    else:
        jd_midnight = core.to_julian_ut(y, m, d, 0, 0, 0, args.tz)
        sunrise_jd, sunset_jd = core.next_rise_set(jd_midnight, args.lat, args.lon)
    day_periods = _day_periods(sunrise_jd, sunset_jd, weekday, args.tz)

    return {
        "input": {
            "date": args.date, "time": t, "lat": args.lat, "lon": args.lon,
            "timezone": args.tz, "ayanamsa": args.ayanamsa,
        },
        "vara": weekday,
        "tithi": {"name": TITHI_NAMES[tithi_index], "paksha": paksha,
                  "number": (tithi_index % 15) + 1, "index": tithi_index + 1},
        "nakshatra": {"name": core.NAKSHATRAS[nak_index],
                      "lord": core.DASHA_SEQUENCE[nak_index % 9]},
        "yoga": {"name": YOGA_NAMES[yoga_index]},
        "karana": {"name": _karana_name(karana_index)},
        "sunrise": _fmt_clock(sunrise_jd, args.tz),
        "sunset": _fmt_clock(sunset_jd, args.tz),
        **day_periods,
        "sun_longitude": round(sun_lon, 4),
        "moon_longitude": round(moon_lon, 4),
    }


def compute(date: str, time: str | None = None, *, lat: float, lon: float,
            tz: str, ayanamsa: str = core.DEFAULT_AYANAMSA) -> dict:
    """Programmatic entry point — compute the Panchang without argparse.

    Mirrors compute_panchang() but takes explicit params, so other scripts
    (sky.py, astro_claude.py) can reuse the almanac directly.
    """
    ns = argparse.Namespace(date=date, time=time or "12:00:00", lat=lat, lon=lon,
                            tz=tz, ayanamsa=ayanamsa)
    return compute_panchang(ns)


def _fmt_clock(jd, tz_name):
    """Format a Julian Day (UT) as local HH:MM, or None."""
    if jd is None:
        return None
    return core.jd_to_local(jd, tz_name).strftime("%H:%M")


def _day_periods(sunrise_jd, sunset_jd, weekday, tz_name) -> dict:
    """Compute Rahu Kaal, Yamaganda, Gulika (1/8 of daytime) and Abhijit muhurta."""
    if sunrise_jd is None or sunset_jd is None:
        return {"rahu_kaal": None, "yamaganda": None, "gulika": None, "abhijit": None}
    day_len = sunset_jd - sunrise_jd
    seg = day_len / 8.0

    def window(segment_index_1based):
        start = sunrise_jd + (segment_index_1based - 1) * seg
        return f"{_fmt_clock(start, tz_name)}–{_fmt_clock(start + seg, tz_name)}"

    # Abhijit muhurta: 8th of 15 equal daytime muhurtas (straddles solar noon).
    mu = day_len / 15.0
    abhijit_start = sunrise_jd + 7 * mu
    abhijit = f"{_fmt_clock(abhijit_start, tz_name)}–{_fmt_clock(abhijit_start + mu, tz_name)}"

    return {
        "rahu_kaal": window(RAHU_KAAL_SEG[weekday]),
        "yamaganda": window(YAMAGANDA_SEG[weekday]),
        "gulika": window(GULIKA_SEG[weekday]),
        "abhijit": abhijit,
    }


def render_text(result: dict) -> str:
    t = result["tithi"]
    lines = []
    lines.append("=" * 50)
    lines.append("  PANCHANG — Vedic Almanac")
    lines.append("=" * 50)
    i = result["input"]
    lines.append(f"  Date: {i['date']} {i['time']} ({i['timezone']})")
    lines.append(f"  Ayanamsa: {i['ayanamsa'].title()}")
    lines.append("-" * 50)
    lines.append(f"  Vara (weekday) : {result['vara']}")
    lines.append(f"  Tithi          : {t['paksha']} {t['name']} (#{t['number']})")
    lines.append(f"  Nakshatra      : {result['nakshatra']['name']} "
                 f"(lord {result['nakshatra']['lord']})")
    lines.append(f"  Yoga           : {result['yoga']['name']}")
    lines.append(f"  Karana         : {result['karana']['name']}")
    if result.get("sunrise"):
        lines.append("-" * 50)
        lines.append(f"  Sunrise / Sunset: {result['sunrise']} / {result['sunset']}")
    lines.append("-" * 50)
    lines.append("  Inauspicious / auspicious windows (local time):")
    lines.append(f"  Rahu Kaal      : {result.get('rahu_kaal') or 'n/a'}")
    lines.append(f"  Yamaganda      : {result.get('yamaganda') or 'n/a'}")
    lines.append(f"  Gulika Kaal    : {result.get('gulika') or 'n/a'}")
    lines.append(f"  Abhijit Muhurta: {result.get('abhijit') or 'n/a'}  (auspicious)")
    lines.append("=" * 50)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Compute the daily Panchang.")
    ap.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    ap.add_argument("--time", default="12:00:00", help="Local clock time HH:MM[:SS]")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        result = compute_panchang(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

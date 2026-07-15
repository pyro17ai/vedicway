#!/usr/bin/env python3
"""
sky.py — Today's Sky (Aakash Darshan): the daily Hindu Panchang + a detailed read
of how the planets (grahas) are aligned right now. NO birth chart required.

This is the *opening view* of the skill. Before any personal reading, it answers
"what does the sky look like today, and how are the stars aligned":

  1. The five limbs of the Panchang — vara (weekday), tithi, nakshatra, yoga,
     karana — plus sunrise/sunset, Rahu Kaal and the auspicious Abhijit muhurta.
  2. The live sidereal positions of all nine grahas (sign, nakshatra + pada,
     degree, retrograde, combustion, dignity).
  3. The patterns that give the day its character — conjunctions (planets sharing
     a sign), what is retrograde, what is combust, and the slow-mover backdrop
     (Shani, Guru, Rahu/Ketu) that sets the collective, long-term tone.

Astro Claude calls this to OPEN every reading. It also stands alone for "what's
the panchang today" / "how are the stars aligned now" questions, and can be
personalised to a birth chart (house-from-Moon + Sade Sati) via the natal= hook.

Usage:
    python sky.py --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--date 2026-06-04] [--time 12:00:00] [--ayanamsa lahiri] [--json]

--date  the day to read (default: today).  --time  the clock time the live sky is
        sampled at (default: noon); the Moon moves ~1°/2h, so its nakshatra is the
        only fast-changing element.

Disclaimer: cultural / educational use only. The sky is a backdrop, not a verdict;
this is not predictive of real outcomes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date, datetime

import core
import panchang as panchang_mod

# The four slow movers set the era's tone (months to years per sign).
SLOW = ["Saturn", "Jupiter", "Rahu", "Ketu"]


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def _ord(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 11 -> '11th' …"""
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def compute_sky(date_str: str, time_str: str, lat: float, lon: float, tz: str,
                ayanamsa: str = core.DEFAULT_AYANAMSA, natal: dict | None = None) -> dict:
    """Compute today's Panchang + the live planetary alignment.

    natal (optional): {"moon_sign_num": int, "asc_sign_num": int}. When given,
    every transiting graha is also counted as a house from the natal Moon and
    Lagna, and the Saturn-from-Moon Sade Sati / Dhaiya phase is flagged — turning
    the generic sky into a personal one.
    """
    # 1) Almanac for the day at this place. compute_panchang() inits the engine
    #    itself (non-topocentric — its limbs are Sun/Moon-longitude based).
    panch = panchang_mod.compute(date_str, time_str, lat=lat, lon=lon, tz=tz,
                                 ayanamsa=ayanamsa)

    # 2) Live sky — sidereal positions of all nine grahas at the sampled time.
    #    Topocentric (observer on Earth) to match the birth-chart / gochar engine.
    core.init_engine(ayanamsa, topocentric=True, lat=lat, lon=lon)
    y, m, d = (int(x) for x in date_str.split("-"))
    hh, mm, ss = _parse_time(time_str)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, tz)
    pos = core.all_planet_positions(jd)
    sun_lon = pos["Sun"]["longitude"]

    planets: list[dict] = []
    by_sign: dict[int, list[str]] = {}
    for name in core.PLANET_ORDER:
        p = pos[name]
        entry = {
            "planet": name,
            "sign": p["sign"],
            "sign_hi": core.SIGN_HINDI[p["sign"]],
            "sign_num": p["sign_num"],
            "degree": p["degree_in_sign"],
            "nakshatra": p["nakshatra"],
            "pada": p["pada"],
            "retrograde": p["retrograde"],
            "combust": core.is_combust(name, p["longitude"], sun_lon, p["retrograde"]),
            "dignity": core.dignity(name, p["sign_num"]),
        }
        if natal is not None:
            entry["house_from_moon"] = core.house_of(p["sign_num"], natal["moon_sign_num"])
            entry["house_from_lagna"] = core.house_of(p["sign_num"], natal["asc_sign_num"])
        planets.append(entry)
        by_sign.setdefault(p["sign_num"], []).append(name)

    conjunctions = [
        {"sign": core.SIGNS[s - 1], "planets": names}
        for s, names in sorted(by_sign.items()) if len(names) >= 2
    ]
    # Rahu/Ketu are retrograde by nature — exclude them so the insight lists only
    # the meaningful true-motion retrogrades.
    retrogrades = [e["planet"] for e in planets
                   if e["retrograde"] and e["planet"] not in ("Rahu", "Ketu")]
    combust = [e["planet"] for e in planets if e["combust"]]
    slow = [e for e in planets if e["planet"] in SLOW]

    result = {
        "input": {"date": date_str, "time": time_str, "lat": lat, "lon": lon,
                  "timezone": tz, "ayanamsa": ayanamsa},
        "panchang": panch,
        "planets": planets,
        "conjunctions": conjunctions,
        "retrograde": retrogrades,
        "combust": combust,
        "slow_movers": slow,
        "moon": next(e for e in planets if e["planet"] == "Moon"),
        "sun": next(e for e in planets if e["planet"] == "Sun"),
    }
    if natal is not None:
        sat_h = next(e for e in planets if e["planet"] == "Saturn")["house_from_moon"]
        result["sade_sati"] = {
            "active": sat_h in (12, 1, 2),
            "dhaiya": sat_h in (4, 8),
            "saturn_house_from_moon": sat_h,
        }
    return result


def render_block(r: dict, personal: bool = False) -> list[str]:
    """Render the Panchang + alignment as indented lines (shared by the standalone
    view and Astro Claude's opening). Returns a list of lines, no surrounding box.
    """
    L: list[str] = []
    A = L.append
    panch = r["panchang"]
    t = panch["tithi"]

    # --- Panchang (the almanac) ---
    A("  📿 TODAY'S PANCHANG (Hindu almanac)")
    A(f"     Vara (weekday) : {panch['vara']}")
    A(f"     Tithi          : {t['paksha']} {t['name']} (#{t['number']})")
    A(f"     Nakshatra (Moon): {panch['nakshatra']['name']} — lord {panch['nakshatra']['lord']}")
    A(f"     Yoga / Karana  : {panch['yoga']['name']} / {panch['karana']['name']}")
    if panch.get("sunrise"):
        A(f"     Sunrise/Sunset : {panch['sunrise']} / {panch['sunset']}")
    A(f"     Rahu Kaal      : {panch.get('rahu_kaal') or 'n/a'}  (inauspicious — avoid)")
    A(f"     Abhijit Muhurta: {panch.get('abhijit') or 'n/a'}  (auspicious window)")
    A("")

    # --- Planetary alignment (the live sky) ---
    A("  ✨ HOW THE STARS ARE ALIGNED TODAY")
    A("     Graha             Sign            Nakshatra (pada)   Notes")
    A("     " + "-" * 66)
    for e in r["planets"]:
        flags = []
        if e["retrograde"] and e["planet"] not in ("Rahu", "Ketu"):
            flags.append("retrograde")
        if e["combust"]:
            flags.append("combust")
        if e["dignity"] in ("exalted", "debilitated", "own sign"):
            flags.append(e["dignity"])
        if personal and "house_from_moon" in e:
            flags.append(f"{_ord(e['house_from_moon'])} from Moon")
        note = ", ".join(flags)
        A(f"     {core.planet_hi(e['planet']):<17} {e['sign']:<15} "
          f"{e['nakshatra']:<15} ({e['pada']})  {note}")
    A("     " + "-" * 66)
    A("")

    # --- The sky in plain words ---
    moon, sun = r["moon"], r["sun"]
    A("  🪐 THE SKY IN PLAIN WORDS")
    A(f"     • The Moon (Chandra) rides {core.sign_hi(moon['sign'])} in {moon['nakshatra']} —")
    A(f"       this colours today's mood and emotional weather.")
    A(f"     • The Sun (Surya) is in {core.sign_hi(sun['sign'])} — the solar month and season behind it all.")
    for c in r["conjunctions"]:
        names = " + ".join(core.planet_hi(p) for p in c["planets"])
        A(f"     • Conjunction in {core.sign_hi(c['sign'])}: {names} share a sign — their themes blend.")
    if r["retrograde"]:
        rl = ", ".join(core.planet_hi(p) for p in r["retrograde"])
        A(f"     • Retrograde now: {rl} — a time to revisit, review and refine those areas, not force them.")
    if r["combust"]:
        cl = ", ".join(core.planet_hi(p) for p in r["combust"])
        A(f"     • Combust (too near the Sun): {cl} — their natural strength is dimmed for now.")
    sm = ", ".join(f"{core.planet_hi(e['planet'])} in {e['sign']}" + (" (R)" if e["retrograde"] else "")
                   for e in r["slow_movers"])
    A(f"     • Long-term backdrop (the slow movers): {sm}.")
    if personal and r.get("sade_sati"):
        ss = r["sade_sati"]
        h = _ord(ss["saturn_house_from_moon"])
        if ss["active"]:
            A(f"     • For YOU: Shani is the {h} from your natal Moon — SADE SATI is active "
              f"(a demanding, maturing phase).")
        elif ss["dhaiya"]:
            A(f"     • For YOU: Shani is the {h} from your natal Moon — a Dhaiya (small panoti) phase.")
        else:
            A(f"     • For YOU: Shani sits {h} from your natal Moon — no Sade Sati or Dhaiya right now.")
    return L


def render_text(r: dict) -> str:
    i = r["input"]
    L = ["=" * 70, "  🕉  TODAY'S SKY — Panchang & Planetary Alignment", "=" * 70]
    L.append(f"  For : {i['date']} {i['time']}  @ {i['lat']}, {i['lon']} ({i['timezone']})")
    L.append(f"  Ayanamsa: {i['ayanamsa'].title()}")
    L.append("-" * 70)
    L += render_block(r, personal=("sade_sati" in r))
    L.append("=" * 70)
    L.append("  Cultural / educational use only. The sky is a shared backdrop, not a")
    L.append("  verdict on any one person, and has no demonstrated predictive power.")
    L.append("=" * 70)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(
        description="Today's Sky — the Hindu Panchang + how the planets are aligned now.")
    ap.add_argument("--date", default=_date.today().isoformat(),
                    help="Day to read YYYY-MM-DD (default: today)")
    ap.add_argument("--time", default="12:00:00",
                    help="Clock time the live sky is sampled at, HH:MM[:SS] (default noon)")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got '{args.date}'", file=sys.stderr)
        sys.exit(1)

    try:
        result = compute_sky(args.date, args.time, args.lat, args.lon, args.tz, args.ayanamsa)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
matching.py — Kundli matching (Guna Milan / Ashtakoot) and dosha detection.

Two modes:
  --mode milan : 36-point Ashtakoot compatibility between two charts (boy/girl),
                 plus each person's Manglik (Mangal Dosha) status.
  --mode dosha : single-chart dosha scan — Manglik and Kaal Sarpa.

IMPORTANT — tradition variance: Ashtakoot koota tables (especially Vashya, Yoni,
Gana, Bhakoot) differ between regional schools (BV Raman, KP, South Indian).
This module uses one widely-used standard and documents it. Scores may differ by
a few points from other software — that is inherent to the system, not a bug.
By construction the maximum total is exactly 36.

For cultural/educational/entertainment use only. Not a basis for real decisions.

Usage:
  python3 matching.py --mode milan \\
    --boy-date 1990-08-15 --boy-time 14:30:00 --boy-lat 28.61 --boy-lon 77.21 --boy-tz Asia/Kolkata \\
    --girl-date 1992-03-10 --girl-time 09:15:00 --girl-lat 19.07 --girl-lon 72.88 --girl-tz Asia/Kolkata

  python3 matching.py --mode dosha \\
    --date 1990-08-15 --time 14:30:00 --lat 28.61 --lon 77.21 --tz Asia/Kolkata
"""

from __future__ import annotations

import argparse
import json
import sys

import core

# --------------------------------------------------------------------------- #
# Nakshatra attribute tables (index 0..26, aligned to core.NAKSHATRAS)
# --------------------------------------------------------------------------- #
# Yoni (animal) per nakshatra.
YONI = [
    "Horse", "Elephant", "Sheep", "Serpent", "Serpent", "Dog", "Cat", "Sheep",
    "Cat", "Rat", "Rat", "Cow", "Buffalo", "Tiger", "Buffalo", "Tiger", "Deer",
    "Deer", "Dog", "Monkey", "Mongoose", "Monkey", "Lion", "Horse", "Lion",
    "Cow", "Elephant",
]
# Arch-enemy yoni pairs (score 0). Same yoni = 4; otherwise neutral = 2.
# NOTE: simplified — the full classical Yoni matrix has 4/3/2/1/0 gradations;
# here we encode same=4, sworn-enemy=0, else=2, and document the simplification.
YONI_ENEMIES = {
    frozenset(["Cow", "Tiger"]), frozenset(["Elephant", "Lion"]),
    frozenset(["Horse", "Buffalo"]), frozenset(["Dog", "Deer"]),
    frozenset(["Cat", "Rat"]), frozenset(["Serpent", "Mongoose"]),
    frozenset(["Sheep", "Monkey"]),
}

# Gana per nakshatra: 0=Deva, 1=Manushya, 2=Rakshasa.
GANA = [0, 1, 2, 1, 0, 1, 0, 0, 2, 2, 1, 1, 0, 2, 0, 2, 0, 2, 2, 1, 1, 0, 2, 2, 1, 1, 0]

# Nadi per nakshatra: 0=Adi, 1=Madhya, 2=Antya.
NADI = [0, 1, 2, 2, 1, 0, 0, 1, 2, 2, 1, 0, 0, 1, 2, 2, 1, 0, 0, 1, 2, 2, 1, 0, 0, 1, 2]

# Varna by Moon sign (1..12): 4=Brahmin,3=Kshatriya,2=Vaishya,1=Shudra.
VARNA = {4: 4, 8: 4, 12: 4, 1: 3, 5: 3, 9: 3, 2: 2, 6: 2, 10: 2, 3: 1, 7: 1, 11: 1}

# Vashya group by Moon sign (1..12). Documented full-sign convention.
VASHYA = {1: "Chatush", 2: "Chatush", 3: "Nara", 4: "Jala", 5: "Vana", 6: "Nara",
          7: "Nara", 8: "Keeta", 9: "Nara", 10: "Jala", 11: "Nara", 12: "Jala"}
VASHYA_SCORE = {  # [boy][girl] out of 2
    "Nara":   {"Nara": 2, "Chatush": 1, "Jala": 1, "Vana": 0, "Keeta": 1},
    "Chatush": {"Nara": 1, "Chatush": 2, "Jala": 1, "Vana": 0, "Keeta": 1},
    "Jala":   {"Nara": 1, "Chatush": 1, "Jala": 2, "Vana": 1, "Keeta": 0.5},
    "Vana":   {"Nara": 0, "Chatush": 0.5, "Jala": 1, "Vana": 2, "Keeta": 1},
    "Keeta":  {"Nara": 1, "Chatush": 1, "Jala": 0.5, "Vana": 1, "Keeta": 2},
}
# Gana score [boy_gana][girl_gana] out of 6 (BV Raman convention).
GANA_SCORE = [[6, 6, 1], [5, 6, 0], [1, 0, 6]]
GANA_NAME = ["Deva", "Manushya", "Rakshasa"]
NADI_NAME = ["Adi", "Madhya", "Antya"]

MANGLIK_HOUSES = {1, 2, 4, 7, 8, 12}


# --------------------------------------------------------------------------- #
# Chart helper
# --------------------------------------------------------------------------- #
def build_chart(date, time, lat, lon, tz, ayanamsa, node) -> dict:
    """Compute the minimal chart data needed for matching/doshas (topocentric)."""
    core.init_engine(ayanamsa, node=node, topocentric=True, lat=lat, lon=lon)
    y, m, d = (int(x) for x in date.split("-"))
    parts = time.split(":")
    hh = int(parts[0]); mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, tz)

    asc = core.ascendant(jd, lat, lon)
    planets = core.all_planet_positions(jd)
    for name, info in planets.items():
        info["house"] = core.house_of(info["sign_num"], asc["sign_num"])

    moon = planets["Moon"]
    nak_index = core.NAKSHATRAS.index(moon["nakshatra"])
    return {
        "ascendant": asc,
        "planets": planets,
        "moon_sign": moon["sign_num"],
        "moon_nakshatra_index": nak_index,
        "moon_nakshatra": moon["nakshatra"],
    }


# --------------------------------------------------------------------------- #
# Ashtakoot kootas
# --------------------------------------------------------------------------- #
def k_varna(boy, girl):
    score = 1 if VARNA[boy["moon_sign"]] >= VARNA[girl["moon_sign"]] else 0
    return score, 1, "boy's varna >= girl's" if score else "boy's varna < girl's"


def k_vashya(boy, girl):
    s = VASHYA_SCORE[VASHYA[boy["moon_sign"]]][VASHYA[girl["moon_sign"]]]
    return s, 2, f"{VASHYA[boy['moon_sign']]} / {VASHYA[girl['moon_sign']]}"


def k_tara(boy, girl):
    def good(a, b):
        count = (b - a) % 27 + 1
        tara = count % 9 or 9
        return tara in (2, 4, 6, 8, 9)
    s = (1.5 if good(boy["moon_nakshatra_index"], girl["moon_nakshatra_index"]) else 0) + \
        (1.5 if good(girl["moon_nakshatra_index"], boy["moon_nakshatra_index"]) else 0)
    return s, 3, "Tara (both directions)"


def k_yoni(boy, girl):
    yb, yg = YONI[boy["moon_nakshatra_index"]], YONI[girl["moon_nakshatra_index"]]
    if yb == yg:
        s = 4
    elif frozenset([yb, yg]) in YONI_ENEMIES:
        s = 0
    else:
        s = 2  # simplified neutral (see module docstring)
    return s, 4, f"{yb} / {yg}"


def k_graha_maitri(boy, girl):
    lb = core.SIGN_LORD[boy["moon_sign"]]
    lg = core.SIGN_LORD[girl["moon_sign"]]
    if lb == lg:
        return 5, 5, f"same lord ({lb})"
    r1 = core.natural_relation(lb, lg)
    r2 = core.natural_relation(lg, lb)
    pair = {r1, r2}
    if pair == {"friend"}:
        s = 5
    elif pair == {"friend", "neutral"}:
        s = 4
    elif pair == {"neutral"}:
        s = 3
    elif pair == {"friend", "enemy"}:
        s = 1
    elif pair == {"neutral", "enemy"}:
        s = 0.5
    else:
        s = 0
    return s, 5, f"{lb} vs {lg} ({r1}/{r2})"


def k_gana(boy, girl):
    gb, gg = GANA[boy["moon_nakshatra_index"]], GANA[girl["moon_nakshatra_index"]]
    return GANA_SCORE[gb][gg], 6, f"{GANA_NAME[gb]} / {GANA_NAME[gg]}"


def k_bhakoot(boy, girl):
    a, b = boy["moon_sign"], girl["moon_sign"]
    n = (b - a) % 12 + 1
    m = (a - b) % 12 + 1
    bad = {frozenset([2, 12]), frozenset([5, 9]), frozenset([6, 8])}
    s = 0 if frozenset([n, m]) in bad else 7
    return s, 7, f"rashi positions {n}/{m}" + (" (dosha)" if s == 0 else "")


def k_nadi(boy, girl):
    nb, ng = NADI[boy["moon_nakshatra_index"]], NADI[girl["moon_nakshatra_index"]]
    s = 0 if nb == ng else 8
    note = f"{NADI_NAME[nb]} / {NADI_NAME[ng]}" + (" (Nadi dosha)" if s == 0 else "")
    return s, 8, note


KOOTAS = [
    ("Varna", k_varna), ("Vashya", k_vashya), ("Tara", k_tara), ("Yoni", k_yoni),
    ("Graha Maitri", k_graha_maitri), ("Gana", k_gana), ("Bhakoot", k_bhakoot),
    ("Nadi", k_nadi),
]


def guna_milan(boy, girl) -> dict:
    rows = []
    total = 0.0
    for name, fn in KOOTAS:
        got, mx, note = fn(boy, girl)
        total += got
        rows.append({"koota": name, "score": got, "max": mx, "note": note})
    verdict = ("Excellent" if total >= 32 else "Very good" if total >= 26 else
               "Good" if total >= 18 else "Below threshold (<18)")
    return {"kootas": rows, "total": round(total, 1), "max": 36, "verdict": verdict}


# --------------------------------------------------------------------------- #
# Doshas
# --------------------------------------------------------------------------- #
def manglik(chart) -> dict:
    """Mangal Dosha checked from all three classical reference points — the
    Lagna, the Moon, and Venus — not just the Lagna. Mars in the 1/2/4/7/8/12
    from ANY of these flags the dosha (the widely-used strict convention)."""
    mars_sign = chart["planets"]["Mars"]["sign_num"]
    mars_house = chart["planets"]["Mars"]["house"]   # from Lagna
    from_moon = core.house_of(mars_sign, chart["planets"]["Moon"]["sign_num"])
    from_venus = core.house_of(mars_sign, chart["planets"]["Venus"]["sign_num"])
    flags = {
        "lagna": mars_house in MANGLIK_HOUSES,
        "moon": from_moon in MANGLIK_HOUSES,
        "venus": from_venus in MANGLIK_HOUSES,
    }
    is_m = any(flags.values())
    triggered = [k for k, v in flags.items() if v]
    return {
        "manglik": is_m,
        "mars_house_from_lagna": mars_house,
        "mars_house_from_moon": from_moon,
        "mars_house_from_venus": from_venus,
        "triggered_from": triggered,
        "note": (f"Mars is in house {mars_house} from Lagna, {from_moon} from the Moon, "
                 f"{from_venus} from Venus. "
                 + (f"→ Manglik (Mangal Dosha), triggered from: {', '.join(triggered)}."
                    if is_m else "→ not Manglik from any of the three references.")),
    }


def kaal_sarpa(chart) -> dict:
    rahu = chart["planets"]["Rahu"]["longitude"]
    seven = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    ds = [(chart["planets"][p]["longitude"] - rahu) % 360 for p in seven]
    side_a = all(0 < d < 180 for d in ds)
    side_b = all(180 < d < 360 for d in ds)
    full = side_a or side_b
    return {
        "kaal_sarpa": full,
        "note": ("All seven planets are hemmed within the Rahu–Ketu axis → Kaal Sarpa Dosha."
                 if full else
                 "Planets fall on both sides of the Rahu–Ketu axis → no full Kaal Sarpa Dosha."),
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_milan(result, boy, girl) -> str:
    g = result["milan"]
    lines = ["=" * 64, "  GUNA MILAN — Ashtakoot Compatibility (36 points)", "=" * 64]
    lines.append(f"  Boy : Moon {core.SIGNS[boy['moon_sign']-1]} / {boy['moon_nakshatra']}")
    lines.append(f"  Girl: Moon {core.SIGNS[girl['moon_sign']-1]} / {girl['moon_nakshatra']}")
    lines.append("-" * 64)
    lines.append(f"  {'Koota':<14}{'Score':>7}{'Max':>5}   Detail")
    lines.append("  " + "-" * 60)
    for r in g["kootas"]:
        lines.append(f"  {r['koota']:<14}{r['score']:>7}{r['max']:>5}   {r['note']}")
    lines.append("  " + "-" * 60)
    lines.append(f"  {'TOTAL':<14}{g['total']:>7}{g['max']:>5}   {g['verdict']}")
    lines.append("-" * 64)
    lines.append(f"  Boy Manglik : {result['boy_manglik']['note']}")
    lines.append(f"  Girl Manglik: {result['girl_manglik']['note']}")
    lines.append("=" * 64)
    lines.append("  Koota tables follow one standard; regional variants exist. "
                 "Cultural/educational use only.")
    lines.append("=" * 64)
    return "\n".join(lines)


def render_dosha(result) -> str:
    lines = ["=" * 60, "  DOSHA SCAN", "=" * 60]
    lines.append(f"  Manglik (Mangal Dosha): {'YES' if result['manglik']['manglik'] else 'no'}")
    lines.append(f"      {result['manglik']['note']}")
    lines.append(f"  Kaal Sarpa Dosha      : {'YES' if result['kaal_sarpa']['kaal_sarpa'] else 'no'}")
    lines.append(f"      {result['kaal_sarpa']['note']}")
    lines.append("=" * 60)
    lines.append("  Cultural/educational use only. Not predictive.")
    lines.append("=" * 60)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Kundli matching (Guna Milan) and dosha scan.")
    ap.add_argument("--mode", required=True, choices=["milan", "dosha"])
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--json", action="store_true")
    # single-chart (dosha mode)
    ap.add_argument("--date"); ap.add_argument("--time")
    ap.add_argument("--lat", type=float); ap.add_argument("--lon", type=float)
    ap.add_argument("--tz")
    # two-chart (milan mode)
    for who in ("boy", "girl"):
        ap.add_argument(f"--{who}-date"); ap.add_argument(f"--{who}-time")
        ap.add_argument(f"--{who}-lat", type=float); ap.add_argument(f"--{who}-lon", type=float)
        ap.add_argument(f"--{who}-tz")
    args = ap.parse_args()

    try:
        if args.mode == "dosha":
            if not all([args.date, args.time, args.lat is not None, args.lon is not None, args.tz]):
                raise ValueError("dosha mode needs --date --time --lat --lon --tz")
            chart = build_chart(args.date, args.time, args.lat, args.lon, args.tz,
                                args.ayanamsa, args.node)
            result = {"manglik": manglik(chart), "kaal_sarpa": kaal_sarpa(chart)}
            print(json.dumps(result, indent=2) if args.json else render_dosha(result))
        else:
            need = [args.boy_date, args.boy_time, args.boy_lat, args.boy_lon, args.boy_tz,
                    args.girl_date, args.girl_time, args.girl_lat, args.girl_lon, args.girl_tz]
            if any(x is None for x in need):
                raise ValueError("milan mode needs full --boy-* and --girl-* birth details")
            boy = build_chart(args.boy_date, args.boy_time, args.boy_lat, args.boy_lon,
                              args.boy_tz, args.ayanamsa, args.node)
            girl = build_chart(args.girl_date, args.girl_time, args.girl_lat, args.girl_lon,
                               args.girl_tz, args.ayanamsa, args.node)
            result = {
                "milan": guna_milan(boy, girl),
                "boy_manglik": manglik(boy),
                "girl_manglik": manglik(girl),
            }
            print(json.dumps(result, indent=2) if args.json else render_milan(result, boy, girl))
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
mantra.py — goal-specific mantra guidance for the seeker.

A seeker asks "which mantra should I chant for wealth / success / marriage /
health…". For each goal this gives two layers, each with its reason:

  1. The **deity mantra** for that goal — universally safe for anyone (Lakshmi
     for wealth, Ganesha for success, Saraswati for learning, Mahamrityunjaya for
     health, Hanuman/Durga for protection, …).
  2. The **chart-personalised planetary mantra** — the beej mantra of the planet
     that rules that goal's houses in THIS chart (and the relevant karaka),
     marked "strengthen" if it is a functional benefic or "harmonise/pacify" if a
     functional malefic — plus its weekday and the classical japa count.

It also folds in the running **Mahadasha** lord, whose mantra supports the whole
period.

Usage:
    python mantra.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--goal wealth] [--on 2026-06-04] [--json]

--goal one of: wealth success career marriage health education children
       protection peace spirituality all   (default: all)

Disclaimer: traditional/cultural practice only. Mantra japa is a devotional act;
this is not medical, financial, or psychological advice, and has no demonstrated
external effect. Chant with faith, not as a transaction.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime

import core
import astro_claude as ac
import remedies as rem
import dasha as dasha_mod

# Classical full-japa (anushthana) counts per planet; 108/day is the daily mala.
JAPA = {"Sun": 7000, "Moon": 11000, "Mars": 10000, "Mercury": 9000,
        "Jupiter": 19000, "Venus": 16000, "Saturn": 23000, "Rahu": 18000, "Ketu": 17000}

GAYATRI = ("Om Bhur Bhuvah Svah | Tat Savitur Varenyam | Bhargo Devasya Dheemahi | "
           "Dhiyo Yo Nah Prachodayat")
MAHAMRITYUNJAYA = ("Om Tryambakam Yajamahe Sugandhim Pushtivardhanam | "
                   "Urvarukamiva Bandhanan Mrityor Mukshiya Maamritat")

GOALS = {
    "wealth": {"label": "Wealth & prosperity", "houses": [2, 11], "karakas": ["Jupiter", "Venus"],
               "deity": [("Goddess Lakshmi", "Om Shreem Mahalakshmyai Namah"),
                         ("Kubera (lord of treasure)", "Om Shreem Hreem Kleem Shreem Kuberaya Namah")]},
    "success": {"label": "Success & removing obstacles", "houses": [10, 11], "karakas": ["Jupiter", "Sun"],
                "deity": [("Ganesha (remover of obstacles)", "Om Gam Ganapataye Namah"),
                          ("Vishnu", "Om Namo Bhagavate Vasudevaya")]},
    "career": {"label": "Career, status & authority", "houses": [10], "karakas": ["Sun", "Saturn", "Mercury"],
               "deity": [("Surya", "Om Suryaya Namah"),
                         ("Ganesha", "Om Gam Ganapataye Namah")]},
    "marriage": {"label": "Marriage & a good spouse", "houses": [7], "karakas": ["Venus", "Jupiter"],
                 "deity": [("Shukra / for a worthy partner", "Om Shukraya Namah"),
                           ("Goddess Katyayani (for marriage)",
                            "Om Katyayani Mahamaye Mahayoginyadhishwari | "
                            "Nandagopasutam Devi Patim Me Kuru Te Namah")]},
    "health": {"label": "Health, healing & longevity", "houses": [1], "karakas": ["Sun", "Moon"],
               "pacify_houses": True,
               "deity": [("Mahamrityunjaya (Shiva — healing)", MAHAMRITYUNJAYA),
                         ("Dhanvantari (divine physician)",
                          "Om Namo Bhagavate Maha Sudarshana Vasudevaya Dhanvantaraye | "
                          "Amrita Kalasha Hastaaya ... Sarva Roga Nivaranaya Trailokya Nathaya Namah")]},
    "education": {"label": "Education, wisdom & exams", "houses": [4, 5], "karakas": ["Mercury", "Jupiter"],
                  "deity": [("Goddess Saraswati", "Om Aim Saraswatyai Namah"),
                            ("Gayatri (clarity of intellect)", GAYATRI)]},
    "children": {"label": "Children & progeny", "houses": [5], "karakas": ["Jupiter"],
                 "deity": [("Santan Gopal (Krishna)",
                            "Om Devakisuta Govinda Vasudeva Jagatpate | "
                            "Dehi Me Tanayam Krishna Twamaham Sharanam Gatah")]},
    "protection": {"label": "Protection, courage & freedom from enemies/fear",
                   "houses": [6], "karakas": ["Mars", "Saturn"], "pacify_houses": True,
                   "deity": [("Hanuman (courage & protection)", "Om Hanumate Namah  (and the Hanuman Chalisa)"),
                             ("Goddess Durga", "Om Dum Durgayai Namah")]},
    "peace": {"label": "Peace of mind & emotional calm", "houses": [], "karakas": ["Moon"],
              "deity": [("Shiva", "Om Namah Shivaya"),
                        ("Chandra (the calm mind)", "Om Som Somaya Namah")]},
    "spirituality": {"label": "Spiritual growth & liberation", "houses": [9, 12],
                     "karakas": ["Jupiter", "Ketu"],
                     "deity": [("Gayatri", GAYATRI),
                               ("Guru / Dattatreya", "Om Gurave Namah"),
                               ("Shiva", "Om Namah Shivaya")]},
}


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def _current_maha(args, asc_sign):
    class A: pass
    da = A()
    for k in ("date", "time", "lat", "lon", "tz", "ayanamsa"):
        setattr(da, k, getattr(args, k))
    da.node = getattr(args, "node", "mean"); da.ephemeris = getattr(args, "ephemeris", "moshier")
    da.geocentric = getattr(args, "geocentric", False); da.levels = 1
    tl = dasha_mod.compute_dasha(da)
    for md in tl["mahadashas"]:
        if md["start"] <= args.on < md["end"]:
            return md["lord"]
    return tl["mahadashas"][0]["lord"]


def compute(args) -> dict:
    core.init_engine(args.ayanamsa, node=getattr(args, "node", "mean"),
                     topocentric=not getattr(args, "geocentric", False),
                     lat=args.lat, lon=args.lon, ephemeris=getattr(args, "ephemeris", "moshier"))
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)
    asc = core.ascendant(jd, args.lat, args.lon)
    asc_sign = asc["sign_num"]
    pos = core.all_planet_positions(jd)
    houses = {n: core.house_of(pos[n]["sign_num"], asc_sign) for n in core.PLANET_ORDER}
    funcs = {p: ac.functional_nature(p, asc_sign, houses[p]) for p in core.PLANET_ORDER}
    lagna_lord = core.SIGN_LORD[asc_sign]
    maha = _current_maha(args, asc_sign)

    def planet_block(planet, force_pacify=False):
        f = funcs[planet]
        if planet in ("Rahu", "Ketu") or f["nature"] == "malefic" or force_pacify:
            mode = "harmonise / pacify"
        else:
            mode = "strengthen"
        return {"planet": planet, "hindi": core.PLANET_HINDI[planet],
                "beej": rem.REMEDIES[planet]["mantra"], "day": rem.REMEDIES[planet]["day"],
                "japa_total": JAPA[planet], "mode": mode,
                "nature": f["nature"], "rules": f["rules"]}

    goals_out = {}
    selected = list(GOALS) if args.goal == "all" else [args.goal]
    for g in selected:
        spec = GOALS[g]
        # House lords for this goal + the karakas, de-duplicated, in chart order.
        planets, seen = [], set()
        pacify_houses = spec.get("pacify_houses", False)
        for h in spec["houses"]:
            lord = core.SIGN_LORD[((asc_sign - 1) + (h - 1)) % 12 + 1]
            if lord not in seen:
                planets.append(planet_block(lord, force_pacify=pacify_houses)); seen.add(lord)
        for k in spec["karakas"]:
            if k not in seen:
                planets.append(planet_block(k)); seen.add(k)
        # Health/protection/peace also lean on the Lagna lord (vitality/self).
        if g in ("health", "protection", "peace") and lagna_lord not in seen:
            planets.append(planet_block(lagna_lord)); seen.add(lagna_lord)
        goals_out[g] = {"label": spec["label"], "deity_mantras": spec["deity"],
                        "planetary": planets}

    return {
        "input": {"date": args.date, "time": args.time, "lat": args.lat,
                  "lon": args.lon, "timezone": args.tz, "ayanamsa": args.ayanamsa},
        "on": args.on, "lagna_sign": asc["sign"], "lagna_lord": lagna_lord,
        "mahadasha_lord": maha, "mahadasha_mantra": rem.REMEDIES[maha]["mantra"],
        "goals": goals_out,
    }


def render_text(r: dict) -> str:
    L = []
    A = L.append
    A("=" * 70)
    A("  MANTRA GUIDANCE")
    A("=" * 70)
    A(f"  Lagna: {core.sign_hi(r['lagna_sign'])}   |   Running Mahadasha: "
      f"{core.planet_hi(r['mahadasha_lord'])}")
    A(f"  Through this whole period, {core.planet_hi(r['mahadasha_lord'])}'s mantra steadies your life:")
    A(f"     {r['mahadasha_mantra']}")
    A("  ⚠ Devotional/cultural practice only — chant with faith, not as a transaction.")
    for g, blk in r["goals"].items():
        A("-" * 70)
        A(f"  FOR {blk['label'].upper()}")
        A("    Deity mantra(s) — safe for anyone:")
        for name, mant in blk["deity_mantras"]:
            A(f"      • {name}: {mant}")
        A("    Your chart's planetary mantra(s) for this goal:")
        for p in blk["planetary"]:
            A(f"      • {core.planet_hi(p['planet'])} [{p['mode']}] — {p['beej']}")
            A(f"          ({p['day']}s, 108×/day; full japa ~{p['japa_total']:,}. "
              f"It is a functional {p['nature']} here.)")
    A("=" * 70)
    A("  Japa method: a mala of 108, daily, ideally at dawn facing the planet's")
    A("  direction; complete the full count over ~40 days for an anushthana.")
    A("  For cultural/educational use only. Not advice; no demonstrated effect.")
    A("=" * 70)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Goal-specific mantra guidance from the chart.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--goal", default="all", choices=list(GOALS) + ["all"])
    ap.add_argument("--on", default=date.today().isoformat())
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        datetime.strptime(args.on, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: --on must be YYYY-MM-DD, got '{args.on}'", file=sys.stderr)
        sys.exit(1)

    try:
        result = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

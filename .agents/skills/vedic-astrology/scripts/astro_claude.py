#!/usr/bin/env python3
"""
astro_claude.py — Astro Claude, for the seeker.

One guided reading that ties the whole engine together and speaks to the person
by name: their age and life stage now, career (Dasamsha) and whether they are
likely to live/work away from their birthplace (and what that brings), a
favourable window to join a new job or company, a decisive gemstone WEAR /
DON'T-WEAR list judged from *their* ascendant, and a Rudraksha recommendation.
Every claim is tagged with the astrological reason behind it, and planets are
named in Hindi as well.

Run the intake first (name, date, EXACT time, birthplace → lat/lon/tz, gender,
married?), then:

    python astro_claude.py --name "Asha" --gender female --married no \\
        --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata [--on 2026-06-04] \\
        [--away unknown] [--json]

Disclaimer: Astro Claude is for cultural, educational, and reflective use only.
It is NOT medical, financial, legal, or psychological advice, has no
scientifically demonstrated predictive power, and gemstone/ritual suggestions
record tradition only — never spend money on them on this basis.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime

import core
import dasha as dasha_mod
import sky as sky_mod

# House groupings.
TRIKONA = {1, 5, 9}
KENDRA = {1, 4, 7, 10}
DUSTHANA = {6, 8, 12}
CAREER_HOUSES = {2, 6, 10, 11}     # income, service/job, career, gains

# Gemstone per planet (the stone that strengthens it).
GEM = {
    "Sun": "Ruby (Manik)", "Moon": "Pearl (Moti)", "Mars": "Red Coral (Moonga)",
    "Mercury": "Emerald (Panna)", "Jupiter": "Yellow Sapphire (Pukhraj)",
    "Venus": "Diamond / White Sapphire (Heera)", "Saturn": "Blue Sapphire (Neelam)",
    "Rahu": "Hessonite (Gomed)", "Ketu": "Cat's Eye (Lehsunia)",
}
# Rudraksha mukhi that carries each planet's energy (traditions vary; common set).
RUDRAKSHA = {
    "Sun": "1-mukhi", "Moon": "2-mukhi", "Mars": "3-mukhi", "Mercury": "4-mukhi",
    "Jupiter": "5-mukhi", "Venus": "6-mukhi", "Saturn": "7-mukhi",
    "Rahu": "8-mukhi", "Ketu": "9-mukhi",
}

LIFE_STAGE = [
    (0, 12, "childhood — foundations, schooling, and the imprint of the home"),
    (12, 24, "youth — education, identity, early ambitions and first independence"),
    (24, 36, "establishment — career-building, marriage, and putting down roots"),
    (36, 48, "consolidation — peak responsibility in work and family, reputation"),
    (48, 60, "maturity — authority, mentoring, reaping what was sown, some turning inward"),
    (60, 200, "elder phase — wisdom, detachment, legacy, and the spiritual quarter of life"),
]


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def _age(dob: str, on: str) -> int:
    b = datetime.strptime(dob, "%Y-%m-%d").date()
    o = datetime.strptime(on, "%Y-%m-%d").date()
    return o.year - b.year - ((o.month, o.day) < (b.month, b.day))


def ruled_houses(planet: str, asc_sign: int) -> list[int]:
    signs = [s for s in range(1, 13) if core.SIGN_LORD[s] == planet]
    return sorted(core.house_of(s, asc_sign) for s in signs)


def functional_nature(planet: str, asc_sign: int, occupied_house: int) -> dict:
    """Functional benefic/malefic for THIS ascendant, from house lordship."""
    if planet in ("Rahu", "Ketu"):
        nat = "malefic" if occupied_house in DUSTHANA else "neutral"
        return {"nature": nat, "rules": [], "is_yogakaraka": False,
                "reason": f"shadow planet acting through House {occupied_house}"}
    rh = ruled_houses(planet, asc_sign)
    rules_trikona = any(h in TRIKONA for h in rh)          # for benefic test (incl. lagna)
    rules_trikona_5_9 = any(h in (5, 9) for h in rh)       # for yogakaraka (excl. lagna)
    rules_kendra = any(h in (4, 7, 10) for h in rh)        # angular other than lagna
    rules_dusthana = any(h in DUSTHANA for h in rh)
    # Yogakaraka = the SAME planet links a trikona (5th/9th) with a kendra (4/7/10).
    is_yk = rules_trikona_5_9 and rules_kendra
    if is_yk:
        nature = "yogakaraka"
    elif rh == [1] or (rules_trikona and not rules_dusthana):
        nature = "benefic"
    elif rules_dusthana and not rules_trikona:
        nature = "malefic"
    else:
        nature = "neutral"
    return {"nature": nature, "rules": rh, "is_yogakaraka": is_yk,
            "reason": "lord of House " + "/".join(map(str, rh))}


def find_active_dasha(timeline: dict, target: str) -> tuple[str, str, dict]:
    maha = antar = None
    md_node = None
    for md in timeline["mahadashas"]:
        if md["start"] <= target < md["end"]:
            maha = md["lord"]; md_node = md
            for ad in md.get("antardashas", []):
                if ad["start"] <= target < ad["end"]:
                    antar = ad["lord"]; break
            break
    # Guard a day-rounding gap at a maha/antar boundary: never return antar=None.
    if maha is not None and antar is None:
        ads = (md_node or {}).get("antardashas")
        antar = ads[0]["lord"] if ads else maha
    return maha, antar, md_node


def career_windows(timeline: dict, target: str, asc_sign: int,
                   funcs: dict, limit: int = 4) -> list[dict]:
    """Current/upcoming antardashas favourable for joining a job/company.

    Skips already-finished periods, labels the currently-running one 'current'
    and future ones 'upcoming', and de-duplicates by lord so a single favourable
    planet doesn't fill every slot.
    """
    out = []
    seen_lords = set()
    for md in timeline["mahadashas"]:
        if md["end"] < target:
            continue
        for ad in md.get("antardashas", []):
            if ad["end"] < target:           # already finished — not actionable
                continue
            lord = ad["lord"]
            if lord in seen_lords:
                continue
            reasons = []
            if lord in ("Jupiter", "Mercury", "Sun"):
                reasons.append(f"{core.planet_hi(lord)} is a natural significator of "
                               f"{'wisdom & growth' if lord=='Jupiter' else 'work & commerce' if lord=='Mercury' else 'authority & status'}")
            rh = funcs[lord]["rules"] if lord in funcs else []
            career_ruled = sorted(set(rh) & CAREER_HOUSES)
            if career_ruled:
                reasons.append("rules your House " + "/".join(map(str, career_ruled))
                               + " (career/income/gains)")
            if funcs.get(lord, {}).get("is_yogakaraka"):
                reasons.append("is your Yogakaraka (a prime success planet)")
            if reasons:
                status = "current" if ad["start"] <= target < ad["end"] else "upcoming"
                out.append({"lord": lord, "maha": md["lord"], "status": status,
                            "start": ad["start"], "end": ad["end"], "reasons": reasons})
                seen_lords.add(lord)
            if len(out) >= limit:
                return out
    return out


def away_signals(asc_sign: int, planets: dict) -> dict:
    """Indications of living/working away from the birthplace (4th = native roots)."""
    signals = []
    fourth_lord = core.SIGN_LORD[((asc_sign - 1) + 3) % 12 + 1]
    fl_house = planets[fourth_lord]["house"]
    strong_foreign = False
    if fl_house in (8, 9, 12):
        signals.append(f"the lord of your 4th house of home, {core.planet_hi(fourth_lord)}, "
                       f"sits in House {fl_house} ({'distant lands/abroad' if fl_house in (9,12) else 'upheaval & change of place'})")
        if fl_house in (9, 12):
            strong_foreign = True
    # Rahu/Ketu in the 4th (roots) or 12th (foreign) — counted once each.
    for node in ("Rahu", "Ketu"):
        nh = planets[node]["house"]
        if nh in (4, 12):
            signals.append(f"{node} occupies House {nh} "
                           f"({'unsettling the home/native roots' if nh == 4 else 'a classic pull toward foreign/distant settlement'})")
            if nh == 12:
                strong_foreign = True
    # Non-node planets in the 12th (foreign residence/gains), without double-counting nodes.
    twelfth_occ = [p for p in core.PLANET_ORDER
                   if planets[p]["house"] == 12 and p not in ("Rahu", "Ketu")]
    if twelfth_occ:
        signals.append("planets in your 12th house of distant lands/foreign settlement: "
                       + ", ".join(core.planet_hi(p) for p in twelfth_occ))
    # Moon in 6th/8th (12th is already covered by the twelfth-house signal above,
    # so excluding it here avoids counting one placement twice).
    if planets["Moon"]["house"] in (6, 8):
        signals.append(f"the Moon (Chandra, your mind & sense of belonging) is in House "
                       f"{planets['Moon']['house']} — comfort is found away from the familiar")
    likely = strong_foreign or len(signals) >= 2
    return {"likely": likely, "fourth_lord": fourth_lord,
            "fourth_lord_house": fl_house, "signals": signals}


def gemstone_guidance(asc_sign: int, funcs: dict, planets: dict, maha: str) -> dict:
    wear, avoid = [], []
    for p in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
        f = funcs[p]
        entry = {"planet": p, "gem": GEM[p], "rules": f["rules"], "nature": f["nature"]}
        if f["nature"] in ("yogakaraka", "benefic"):
            why = "your Yogakaraka — its gem is the single most auspicious to wear" \
                if f["nature"] == "yogakaraka" else \
                f"a functional benefic ({f['reason']}) — its gem supports luck & strength"
            entry["why"] = why
            wear.append(entry)
        elif f["nature"] == "malefic":
            entry["why"] = (f"a functional malefic ({f['reason']}) — strengthening it with a "
                            f"gem can amplify its harmful side; tradition says do NOT wear it")
            avoid.append(entry)
    # Rahu/Ketu gems are almost never worn casually.
    for node in ("Rahu", "Ketu"):
        avoid.append({"planet": node, "gem": GEM[node], "rules": [],
                      "nature": "node",
                      "why": "a shadow planet — its gem (gomed/lehsunia) is intense and "
                             "must be tested first; not for casual wear"})
    return {"wear": wear, "avoid": avoid}


def rudraksha_guidance(funcs: dict, maha: str, sade_sati: bool, asc_sign: int) -> dict:
    """Rudraksha is generally safe for all (Shiva's blessing) — tune the mukhi."""
    recs = [{"bead": "5-mukhi", "for": "Jupiter / general well-being",
             "why": "universally safe; calms the mind and supports overall fortune — "
                    "anyone may wear it"}]
    # Strengthen the running dasha lord if it is benefic; pacify if malefic.
    if maha in RUDRAKSHA:
        nat = funcs.get(maha, {}).get("nature", "neutral")
        verb = "strengthen" if nat in ("benefic", "yogakaraka") else "harmonise"
        recs.append({"bead": RUDRAKSHA[maha], "for": core.planet_hi(maha),
                     "why": f"you are in {core.planet_hi(maha)} Mahadasha; this bead helps "
                            f"{verb} that planet through the whole period"})
    if sade_sati:
        recs.append({"bead": "7-mukhi", "for": "Saturn (Shani)",
                     "why": "you are under Sade Sati — 7-mukhi is the classic bead to steady "
                            "Shani's pressure and bring patience"})
    return {"can_wear": True, "recommendations": recs}


def compute(args) -> dict:
    core.init_engine(
        args.ayanamsa, node=getattr(args, "node", "mean"),
        topocentric=not getattr(args, "geocentric", False),
        lat=args.lat, lon=args.lon, ephemeris=getattr(args, "ephemeris", "moshier"),
    )
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)

    asc = core.ascendant(jd, args.lat, args.lon)
    asc_sign = asc["sign_num"]
    pos = core.all_planet_positions(jd)
    planets = {}
    for n, p in pos.items():
        planets[n] = {"sign": p["sign"], "sign_num": p["sign_num"],
                      "house": core.house_of(p["sign_num"], asc_sign),
                      "dignity": core.dignity(n, p["sign_num"]),
                      "deg": p["degree_in_sign"]}

    # Atmakaraka (Jaimini soul planet) = the graha at the highest degree within
    # its sign among the seven (Sun..Saturn). It signifies the soul's chief
    # lesson and life purpose.
    atmakaraka = max(("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"),
                     key=lambda p: planets[p]["deg"])

    funcs = {p: functional_nature(p, asc_sign, planets[p]["house"]) for p in core.PLANET_ORDER}

    # Dasha timeline + current period.
    class _A: pass
    da = _A()
    for k in ("date", "time", "lat", "lon", "tz", "ayanamsa"):
        setattr(da, k, getattr(args, k))
    da.node = getattr(args, "node", "mean")
    da.ephemeris = getattr(args, "ephemeris", "moshier")
    da.geocentric = getattr(args, "geocentric", False)
    da.levels = 2
    timeline = dasha_mod.compute_dasha(da)
    maha, antar, _ = find_active_dasha(timeline, args.on)

    # Sade Sati (Saturn transit vs natal Moon) at --on.
    ty, tm, td = (int(x) for x in args.on.split("-"))
    jd_tr = core.to_julian_ut(ty, tm, td, 12, 0, 0, args.tz)
    tr = core.all_planet_positions(jd_tr)
    sat_house_from_moon = core.house_of(tr["Saturn"]["sign_num"], planets["Moon"]["sign_num"])
    sade_sati = sat_house_from_moon in (12, 1, 2)

    age = _age(args.date, args.on)
    stage = next(s for lo, hi, s in LIFE_STAGE if lo <= age < hi)

    # The reading OPENS with today's Panchang + sky alignment, personalised to
    # this chart (each transiting graha as a house from the natal Moon/Lagna, and
    # the Saturn-from-Moon Sade Sati phase). Sampled at noon of --on. Computed
    # last so its engine re-init does not disturb the natal/transit calc above.
    today_sky = sky_mod.compute_sky(
        args.on, "12:00:00", args.lat, args.lon, args.tz, args.ayanamsa,
        natal={"moon_sign_num": planets["Moon"]["sign_num"], "asc_sign_num": asc_sign},
    )

    return {
        "today_sky": today_sky,
        "profile": {"name": args.name, "gender": args.gender, "married": args.married,
                    "age": age, "as_of": args.on, "birth": f"{args.date} {args.time}",
                    "away_from_home": args.away},
        "lagna": {"sign": asc["sign"], "sign_hi": core.SIGN_HINDI[asc["sign"]],
                  "nakshatra": asc["nakshatra"]},
        "moon_sign": pos["Moon"]["sign"],
        "atmakaraka": {"planet": atmakaraka, "house": planets[atmakaraka]["house"],
                       "sign": planets[atmakaraka]["sign"]},
        "life_stage": stage,
        "planets": planets,
        "functional": funcs,
        "dasha": {"maha": maha, "antar": antar},
        "sade_sati": {"active": sade_sati, "saturn_house_from_moon": sat_house_from_moon},
        "career_windows": career_windows(timeline, args.on, asc_sign, funcs),
        "away_analysis": away_signals(asc_sign, planets),
        "gemstones": gemstone_guidance(asc_sign, funcs, planets, maha),
        "rudraksha": rudraksha_guidance(funcs, maha, sade_sati, asc_sign),
    }


def render_text(r: dict) -> str:
    p = r["profile"]
    L = []
    A = L.append
    A("=" * 70)
    A("  🕉  ASTRO CLAUDE — for the seeker")
    A("=" * 70)
    name = p["name"]
    A(f"  Namaste, {name}.")
    A(f"  You are {p['age']} years old (as of {p['as_of']}), "
      f"{p['gender']}, {'married' if p['married']=='yes' else 'unmarried' if p['married']=='no' else 'marital status not given'}.")
    A(f"  Lagna (Ascendant): {core.sign_hi(r['lagna']['sign'])}, "
      f"nakshatra {r['lagna']['nakshatra']}.   Moon sign: {core.sign_hi(r['moon_sign'])}.")
    A("-" * 70)

    # Opening: today's Panchang + how the stars are aligned today — the reading
    # always STARTS here, then narrows to the seeker.
    A(f"  🌌 TODAY'S SKY — where the heavens stand on {p['as_of']}")
    A("")
    L += sky_mod.render_block(r["today_sky"], personal=True)
    A("-" * 70)

    # Life stage + dasha
    A(f"  WHERE YOU ARE IN LIFE")
    A(f"    At {p['age']}, you are in your {r['life_stage']}.")
    md, ad = r["dasha"]["maha"], r["dasha"]["antar"]
    A(f"    You are running {core.planet_hi(md)} Mahadasha → {core.planet_hi(ad)} Antardasha —")
    A(f"    this is the planetary 'season' colouring these years. (Run dasha_predict.py")
    A(f"    for the full life-area breakdown.)")
    ak = r["atmakaraka"]
    A(f"    Your Atmakaraka (soul planet) is {core.planet_hi(ak['planet'])} in House "
      f"{ak['house']} — the deepest lesson and purpose of this life centre on its")
    A(f"    significations; its house shows the arena where your soul does its work.")
    if r["sade_sati"]["active"]:
        A(f"    ⚠ You are currently under SADE SATI (Shani over your Moon sign) — a "
          f"demanding but maturing 7½-year phase.")
    A("")

    # Career + away from home
    A(f"  CAREER & PLACE OF WORK")
    aw = r["away_analysis"]
    if p["away_from_home"] == "yes" or aw["likely"]:
        verdict = ("Since you are working away from your birthplace, the chart agrees:"
                   if p["away_from_home"] == "yes"
                   else "Your chart strongly indicates settling/working away from your birthplace:")
        A(f"    {verdict}")
        for s in aw["signals"]:
            A(f"      • {s}")
        A(f"    Consequence: distance tends to *bring the growth* — career, income, and")
        A(f"    fortune ripen better away from your native soil — but at the cost of some")
        A(f"    separation from family and roots, and a recurring pull toward 'home'.")
        A(f"    The remedy is to stay emotionally connected (visits, the 4th-lord's day).")
    else:
        A(f"    Your chart does not strongly push you away from your birthplace — career")
        A(f"    can develop near your native place; relocation is a choice, not a compulsion.")
        if aw["signals"]:
            A(f"    (Mild signals present: " + "; ".join(aw["signals"]) + ".)")
    A("")

    # Good time to join a company
    A(f"  A GOOD TIME TO JOIN A JOB / COMPANY")
    if r["career_windows"]:
        A(f"    The favourable upcoming planetary windows (Antardashas) are:")
        for w in r["career_windows"]:
            tag = " [running now]" if w.get("status") == "current" else ""
            A(f"      • {w['start']} → {w['end']}  —  {core.planet_hi(w['lord'])} "
              f"(under {core.planet_hi(w['maha'])}){tag}")
            A(f"          why: {', '.join(w['reasons'])}.")
        A(f"    Within such a window, pick the actual day by muhurta — a benefic weekday")
        A(f"    (Guru/Budh/Shukra-vaar), an auspicious tithi, and avoiding Rahu Kaal.")
        A(f"    (Run panchang.py for the chosen day to confirm.)")
    else:
        A(f"    No standout career Antardasha in the near window — favour a strong transit")
        A(f"    of Guru (Jupiter) over your 10th/11th and a clean muhurta instead.")
    A("")

    # Gemstones
    A(f"  GEMSTONES — what to WEAR and what to AVOID (for your {r['lagna']['sign']} Lagna)")
    g = r["gemstones"]
    A(f"    ✅ Beneficial to wear:")
    if g["wear"]:
        for e in g["wear"]:
            A(f"       • {e['gem']}  ({core.planet_hi(e['planet'])}) — {e['why']}.")
    else:
        A(f"       • (No clearly benefic lord stands out — rely on Rudraksha & charity.)")
    A(f"    ⛔ Avoid / do NOT wear casually:")
    for e in g["avoid"]:
        A(f"       • {e['gem']}  ({core.planet_hi(e['planet'])}) — {e['why']}.")
    A(f"    Note: even a 'wear' gemstone should be energised and ideally tested first;")
    A(f"    Neelam, Gomed and Lehsunia are especially strong and must be trialled.")
    A("")

    # Rudraksha
    A(f"  RUDRAKSHA — can you wear it?")
    rud = r["rudraksha"]
    A(f"    YES — Rudraksha is Shiva's blessing and is considered safe for everyone")
    A(f"    (unlike gemstones, it does not 'backfire'). Suited beads for you:")
    for rec in rud["recommendations"]:
        A(f"      • {rec['bead']}  (for {rec['for']}) — {rec['why']}.")
    A("")

    A("=" * 70)
    A("  Astro Claude is for reflection and cultural interest ONLY — not medical,")
    A("  financial, legal, or psychological advice, and with no proven predictive")
    A("  power. Never spend money on gemstones or rituals on this basis. Free to use.")
    A("=" * 70)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Astro Claude — a guided seeker's reading.")
    ap.add_argument("--name", required=True, help="The seeker's name (used to address them)")
    ap.add_argument("--gender", default="unspecified",
                    choices=["male", "female", "other", "unspecified"])
    ap.add_argument("--married", default="unknown", choices=["yes", "no", "unknown"])
    ap.add_argument("--away", default="unknown", choices=["yes", "no", "unknown"],
                    help="Is the seeker currently working away from their birthplace?")
    ap.add_argument("--date", required=True, help="Birth date YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="Birth time HH:MM[:SS], 24h local")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--on", default=date.today().isoformat(),
                    help="Date to read for / compute age at (default: today)")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    for label, val in (("--on", args.on), ("--date", args.date)):
        try:
            datetime.strptime(val, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: {label} must be YYYY-MM-DD, got '{val}'", file=sys.stderr)
            sys.exit(1)

    try:
        result = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

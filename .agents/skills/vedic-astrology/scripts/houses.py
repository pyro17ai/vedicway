#!/usr/bin/env python3
"""
houses.py — Bhava (house) report.

The kundli lists planets; this reads the chart house by house — the way a
practitioner actually answers "what about my 7th house / my career / my health".
For each of the twelve bhavas it gives the sign on the house, its lord and where
that lord sits (and in what dignity), the planets sitting in the house — each
with a concise Graha-in-Bhava reading of what that planet does there — the
planets aspecting it (Vedic graha drishti), and the natural karaka: the four
classical ways a house gets its results.

Usage:
    python houses.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--house 7] [--ayanamsa lahiri] [--json]

--house  show just one bhava (1..12); omit for all twelve.

Disclaimer: cultural / educational use only. Not predictive of real outcomes.
"""

from __future__ import annotations

import argparse
import json
import sys

import core

BHAVA = {
    1: ("Tanu", "self, body, vitality, personality, overall life direction", "Sun"),
    2: ("Dhana", "wealth, savings, family, food, speech, accumulated assets", "Jupiter"),
    3: ("Sahaja", "courage, siblings, communication, skills, short journeys, effort", "Mars"),
    4: ("Sukha", "home, mother, property, vehicles, comforts, inner peace, education base", "Moon"),
    5: ("Putra", "children, intellect, romance, creativity, speculation, past-life merit", "Jupiter"),
    6: ("Ari", "enemies, debts, disease, litigation, service, daily work, competition", "Mars"),
    7: ("Yuvati", "spouse, marriage, partnerships, business, trade, the public", "Venus"),
    8: ("Randhra", "longevity, sudden events, inheritance, transformation, the occult, obstacles", "Saturn"),
    9: ("Dharma", "fortune, dharma, father, guru, higher learning, long travel, luck", "Jupiter"),
    10: ("Karma", "career, status, authority, public reputation, action in the world", "Sun"),
    11: ("Labha", "gains, income, friends, networks, elder siblings, fulfilment of desires", "Jupiter"),
    12: ("Vyaya", "loss, expenses, foreign lands, isolation, sleep, liberation (moksha)", "Saturn"),
}

KENDRA = {1, 4, 7, 10}
TRIKONA = {1, 5, 9}
DUSTHANA = {6, 8, 12}

# Graha-in-Bhava: a concise traditional one-line indication for each of the nine
# grahas in each of the twelve houses (index 0 = house 1). These are cultural
# significations (covered by the disclaimer), kept short and non-deterministic;
# dignity, aspects, and the house lord still tune the actual result.
GRAHA_IN_BHAVA = {
    "Sun": [
        "strong will and leadership; a prominent, self-directed personality",
        "authority over finances and family; commanding speech, pride in wealth",
        "courageous self-driven effort; bold communication, some sibling distance",
        "status through home/property; pride in the mother-line, a restless heart",
        "authoritative intellect; leadership in creativity, ego in romance/children",
        "overcomes enemies and rivals; strong in service, friction with father-figures",
        "ego dynamics in marriage; a dominant partner, prominence in public dealings",
        "interest in the occult and longevity; ups and downs to vitality, inheritance issues",
        "fortunate and dharmic; respects father/guru, leadership in beliefs and travel",
        "career prominence and authority; strong public standing, government/leadership",
        "gains through position and influence; powerful networks, ambitions fulfilled",
        "spiritual withdrawal and foreign ties; expense on status, a strained ego",
    ],
    "Moon": [
        "sensitive, adaptable and public-facing; charm with changeable moods",
        "an emotional bond to family and wealth; pleasant speech, fluctuating income",
        "imaginative courage; communicative and close to siblings, restless drive",
        "a happy home and strong mother-bond; emotional security, comfort in property",
        "creative and loving toward children; romantic, emotionally intelligent",
        "emotional sensitivity to conflict and health; worry-prone, service-minded",
        "a caring partner and public popularity; emotionally tied to marriage",
        "deep and intuitive but emotionally turbulent; drawn to mysteries, vulnerable",
        "devout and fortunate; beliefs guided by feeling, attached to mother/guru",
        "a public career and popularity; career shifts, status emotionally invested",
        "gains through the public and social circles; many friends, wishes fulfilled",
        "introspective with a secluded/foreign life; rich imagination, emotional retreat",
    ],
    "Mars": [
        "bold, energetic and athletic; leadership by force, impatient",
        "forceful speech and drive for wealth; spends on assets, family friction",
        "very courageous; strong efforts and siblings, competitive communication",
        "a restless home and drive for property; a technical mind, friction with mother",
        "passionate and competitive intellect; intense romance, risk in speculation",
        "defeats enemies and excels in competition/service; injuries, wins litigation",
        "a passionate but combative marriage (Manglik); drive in business, disputes",
        "surgical/occult interests; accident-prone, inheritance struggles, intensity",
        "zealous beliefs and fortune through effort; friction with father/guru, travel",
        "an ambitious career (engineering/military/sport); forceful public action",
        "gains through effort and competition; energetic networks, goals achieved",
        "hidden anger and action abroad; expense on disputes, drive turned inward",
    ],
    "Mercury": [
        "intelligent, witty and youthful; communicative and versatile",
        "clever speech earning through intellect/trade; articulate about family",
        "a skilled communicator (writing/media); dexterous, capable siblings",
        "an educated, intellectual home; trade/vehicles in property, a busy mind",
        "a sharp intellect; clever children, skill in speculation and creativity",
        "analytical in work and service; debates rivals, nervous/digestive sensitivity",
        "business partnerships; a youthful, clever spouse, a trade-minded marriage",
        "a research mind drawn to secrets/occult; investigative but anxious",
        "scholarly beliefs; clever in higher learning, publishing, philosophical wit",
        "a career in communication/commerce/writing; an adaptable public role",
        "gains through trade, intellect and networks; clever friends, goals met",
        "an imaginative, private intellect; foreign trade, research in seclusion",
    ],
    "Jupiter": [
        "wise, optimistic and respected; an ethical, fortunate personality",
        "wealth and refined truthful speech; family values, accumulated assets",
        "ethical effort and advisory communication; supportive siblings",
        "a happy, educated home; blessings of mother and property, contentment",
        "wise children and strong intellect; good fortune, teaching and creativity",
        "wins disputes ethically and heals through service (can soften the 6th's fight)",
        "a fortunate marriage; a wise, principled spouse, ethical partnerships",
        "interest in scripture and the occult; longevity, protection through crises",
        "highly fortunate and dharmic; guru/father blessings, wisdom, pilgrimage",
        "a respected career (teaching/law/advisory); ethical public standing",
        "large gains and influential good networks; noble aspirations fulfilled",
        "spiritual and charitable; moksha-inclined, foreign blessings, worthy expenses",
    ],
    "Venus": [
        "charming, attractive and artistic; pleasure-loving",
        "wealth through arts/luxury; sweet speech, refined family tastes",
        "artistic communication and creative effort; pleasant siblings",
        "a luxurious home with vehicles and comforts; a devoted mother, domestic ease",
        "romantic and artistic; pleasure in children/creativity, love and speculation",
        "relationship strains amid conflict/service; indulgence-related ailments",
        "a happy, passionate marriage; an attractive spouse, harmonious partnerships",
        "hidden desires; gains through partner/inheritance, sensual intensity",
        "refined beliefs; fortune through arts/women, pleasant long travel",
        "a career in arts/luxury/diplomacy; a charming public image",
        "gains through art, relationships and women; pleasant networks, desires met",
        "pleasures and foreign comforts; indulgent expenses, a private love-life",
    ],
    "Saturn": [
        "serious, disciplined and slow-maturing; hardworking and reserved",
        "delayed but well-earned wealth; measured speech, family responsibility",
        "persistent effort and disciplined communication; some sibling distance",
        "hard-won property and emotional reserve; duty to home, comfort comes late",
        "delayed children and cautious romance; a disciplined, methodical intellect",
        "defeats enemies through endurance; excels in service, chronic ailments",
        "a delayed but mature, dutiful marriage; committed, lasting partnerships",
        "longevity and interest in deep/occult matters; slow transformations",
        "tested beliefs and fortune after delay; duty to father/guru, late luck",
        "career built through long labor; authority earned slowly, lasting status",
        "steady late gains and older friends; ambitions fulfilled through patience",
        "renunciation and a solitary/foreign life; disciplined expenses, detachment",
    ],
    "Rahu": [
        "unconventional, ambitious and magnetic; restless and self-reinventing",
        "a hunger for wealth; unorthodox speech, foreign or fluctuating finances",
        "bold, daring effort (media/tech); courageous, unconventional communication",
        "a restless home and foreign property; unease, unconventional mother-ties",
        "an unconventional intellect and romance; speculative gains/risks, irregular children",
        "powerful against enemies; gains in competition/foreign service, odd illnesses",
        "an unconventional or foreign marriage; intense, sudden alliances",
        "occult obsession and sudden events; research, hidden gains and shocks",
        "unorthodox beliefs and foreign fortune; questioning of guru/father, far travel",
        "a sudden career rise; foreign/tech/political ambition, image-driven status",
        "large sudden gains and wide unusual networks; intense ambitions fulfilled",
        "foreign residence and spiritual extremes; hidden expenses, escapism",
    ],
    "Ketu": [
        "detached and introspective; intuitive yet self-doubting",
        "detachment from wealth/family; terse speech, irregular finances",
        "spiritual courage and intuition; fewer siblings, reticent communication",
        "emotional detachment from home/mother; restlessness, an inner search",
        "a spiritual intellect; detachment in romance, concerns about children",
        "dissolves enemies and debts; healing intuition, ailments that clear suddenly",
        "karmic detachment in marriage; unconventional, fated partnerships",
        "deep occult and research gifts; sudden upheavals, longevity mysteries",
        "mystical beliefs and detachment from dogma; past-life dharma, lone pilgrimage",
        "detachment from status; an intuitive/spiritual career, fluctuating reputation",
        "irregular gains and detachment from networks; sudden fulfilment then release",
        "strong moksha leanings and foreign seclusion; minimal attachments",
    ],
}


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def quality(h: int) -> str:
    if h in TRIKONA and h != 1:
        return "trikona (fortune)"
    if h == 1:
        return "kendra + trikona (lagna)"
    if h in KENDRA:
        return "kendra (pillar)"
    if h in DUSTHANA:
        return "dusthana (difficult)"
    if h in (3, 11):
        return "upachaya (growing)"
    return "neutral"


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
    positions = core.all_planet_positions(jd)

    # Annotate every planet with its house once.
    pl = {}
    for name, p in positions.items():
        pl[name] = {
            "sign_num": p["sign_num"],
            "house": core.house_of(p["sign_num"], asc_sign),
            "dignity": core.dignity(name, p["sign_num"]),
        }

    bhavas = []
    for h in range(1, 13):
        sign_num = ((asc_sign - 1) + (h - 1)) % 12 + 1
        lord = core.SIGN_LORD[sign_num]
        lord_house = pl[lord]["house"]
        occupants = [n for n in core.PLANET_ORDER if pl[n]["house"] == h]
        aspecting = [n for n in core.PLANET_ORDER
                     if n not in occupants and h in core.aspected_houses(pl[n]["house"], n)]
        name_s, signf, karaka = BHAVA[h]
        bhavas.append({
            "house": h,
            "name": name_s,
            "quality": quality(h),
            "sign": core.SIGNS[sign_num - 1],
            "sign_num": sign_num,
            "lord": lord,
            "lord_house": lord_house,
            "lord_dignity": pl[lord]["dignity"],
            "occupants": occupants,
            "occupant_dignities": {n: pl[n]["dignity"] for n in occupants},
            "occupant_readings": {n: GRAHA_IN_BHAVA[n][h - 1] for n in occupants},
            "aspected_by": aspecting,
            "karaka": karaka,
            "karaka_house": pl[karaka]["house"] if karaka in pl else None,
            "significations": signf,
        })

    return {
        "input": {"date": args.date, "time": args.time, "lat": args.lat,
                  "lon": args.lon, "timezone": args.tz, "ayanamsa": args.ayanamsa},
        "lagna_sign": asc["sign"],
        "bhavas": bhavas,
    }


def render_text(result: dict, only: int | None) -> str:
    L = []
    A = L.append
    A("=" * 70)
    A("  BHAVA (HOUSE) REPORT")
    A("=" * 70)
    A(f"  Lagna: {result['lagna_sign']}")
    for b in result["bhavas"]:
        if only and b["house"] != only:
            continue
        A("-" * 70)
        A(f"  HOUSE {b['house']} — {b['name']} Bhava   [{b['quality']}]   sign: {b['sign']}")
        A(f"    Significations : {b['significations']}")
        A(f"    House lord     : {b['lord']} ({b['lord_dignity']}), placed in House {b['lord_house']}")
        if b["occupants"]:
            occ = ", ".join(f"{n} ({b['occupant_dignities'][n]})" for n in b["occupants"])
            A(f"    Occupied by    : {occ}")
            for n in b["occupants"]:
                A(f"      → {n}: {b['occupant_readings'][n]}")
        else:
            A(f"    Occupied by    : — (empty; read via the lord and aspects)")
        A(f"    Aspected by    : {', '.join(b['aspected_by']) if b['aspected_by'] else '—'}")
        A(f"    Natural karaka : {b['karaka']} (placed in House {b['karaka_house']})")
    A("=" * 70)
    A("  A bhava is judged by four things: its lord's placement & strength, the")
    A("  planets in it, the planets aspecting it, and its natural karaka. A house")
    A("  lord in a kendra/trikona strengthens the house; in a dusthana (6/8/12),")
    A("  it strains it. For cultural/educational use only.")
    A("=" * 70)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Bhava (house-by-house) report.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--house", type=int, choices=range(1, 13), metavar="1..12",
                    help="Show only this house (default: all 12)")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        result = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result, args.house))


if __name__ == "__main__":
    main()

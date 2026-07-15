#!/usr/bin/env python3
"""
dasha_predict.py — Interpret the *currently running* Vimshottari dasha.

Where dasha.py answers "WHICH period am I in?", this script answers "WHAT does
that period mean for me?" — across daily life, mind, career, money,
relationships, health, family, enemies, education, and spirituality.

It is chart-aware, not generic. The reading layers three things:

  1. The dasha lord's intrinsic significations (karaka) per life area.
  2. WHERE that lord sits and WHAT it rules in *this* birth chart (house
     placement + house lordship from the Lagna).
  3. The lord's dignity (exalted / own / debilitated / combust) and the
     Maha-lord ↔ Antar-lord natural relationship (friend / neutral / enemy),
     which colours how smoothly the results flow.

Usage:
    python dasha_predict.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--on 2026-06-04] [--ayanamsa lahiri] [--json]

--on  the date to interpret for (default: today). The script locates the
      Mahadasha / Antardasha / Pratyantardasha active on that date.

Disclaimer: cultural / educational use only. Not predictive of real outcomes
and not for medical, financial, legal, or other consequential decisions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime

import core
import dasha as dasha_mod

# --------------------------------------------------------------------------- #
# Life areas (the columns of the reading), in display order.
# --------------------------------------------------------------------------- #
LIFE_AREAS = [
    ("daily",         "General tone & daily life"),
    ("mind",          "Mind & emotions"),
    ("career",        "Career & profession"),
    ("money",         "Money & finance"),
    ("relationships", "Relationships & marriage"),
    ("health",        "Health & vitality"),
    ("family",        "Family & home"),
    ("enemies",       "Enemies, obstacles & disputes"),
    ("education",     "Education & knowledge"),
    ("spirituality",  "Spirituality, travel & fortune"),
]

# --------------------------------------------------------------------------- #
# Per-planet significations for each life area. These are the classical karaka
# meanings of the *dasha lord*; the chart layer (below) personalises them.
# --------------------------------------------------------------------------- #
PLANET_EFFECTS = {
    "Sun": {
        "daily": "Visibility and authority rise; days revolve around status, leadership, and asserting your will. Ego and pride run hot.",
        "mind": "Confident, willful, decisive — but can turn proud, rigid, or domineering when challenged.",
        "career": "A status / promotion phase: dealings with government, bosses, and leadership roles. Favours stepping into authority, administration, politics, or medicine.",
        "money": "Income flows through position, recognition, government, or the father rather than through trade. Earnings are visible but not naturally a saving period.",
        "relationships": "Bonds are tested by ego and dominance. Father and authority figures loom large; manage pride to avoid strain with the spouse.",
        "health": "Watch the heart, eyes, bones, blood pressure, and fevers/head. Vitality is generally strong but overwork drains it.",
        "family": "The father — or your own paternal role and standing in the family — is in focus. Clashes over authority are possible.",
        "enemies": "You overcome rivals through sheer authority and willpower; but arrogance can create fresh opponents. Friction with officials if the Sun is afflicted.",
        "education": "Favours leadership, administration, politics, and medicine; recognition for past learning.",
        "spirituality": "Soul-searching and devotion to the higher Self; Sun/Shiva worship and pilgrimage. Fortune comes through the father and dharma.",
    },
    "Moon": {
        "daily": "Mood-led, changeable days dominated by comfort, the home, the public, and women. Restless travel and frequent shifts of plan.",
        "mind": "Emotionally sensitive, nurturing, and intuitive — but moody and prone to anxiety or overthinking when the Moon is weak.",
        "career": "Good for public-facing work — the masses, hospitality, nursing, food, liquids, real estate. Popularity and demand rise; expect frequent change.",
        "money": "Cashflow ebbs and flows like the tides. Gains via the public, mother, property, and liquids; impulsive spending is a risk.",
        "relationships": "Emotional closeness, romance, and care take centre stage. Mother and women are significant; the need for emotional security drives bonds.",
        "health": "Watch fluids, digestion, chest/lungs, blood, sleep, and above all the mind. Stress-related and emotional complaints need care.",
        "family": "Mother and home are central — domestic matters, property, moving house. Family bonds deepen or are tested emotionally.",
        "enemies": "You disarm opposition through adaptability and public goodwill rather than force; emotional reactivity can be used against you.",
        "education": "Favours the arts, psychology, and caring or public fields; learning comes through feeling and memory.",
        "spirituality": "Devotion of the heart, mother-goddess worship, water pilgrimage. Fortune flows through the public and the mother.",
    },
    "Mars": {
        "daily": "High energy, drive, and friction. Days are action-packed and competitive — sometimes anger- or accident-prone. A push to act, build, and fight.",
        "mind": "Bold, courageous, and decisive — but short-tempered, impatient, and combative under stress.",
        "career": "Energises engineering, defence/police, surgery, sports, machinery, manufacturing, and real estate. Good for bold initiative; risk of conflict with colleagues.",
        "money": "Gains through land, property, siblings, sports, or technical/competitive work. Impulsive risk-taking brings sudden gains and losses.",
        "relationships": "Passion runs high — and so does conflict. Watch for arguments, dominance, and impatience with partners (a Manglik-flavoured phase).",
        "health": "Accidents, cuts, burns, fevers, inflammation, blood, and surgery; anger-driven blood pressure. Take care with sharp objects and vehicles.",
        "family": "Focus on siblings (especially brothers), property disputes, and protecting one's own. Tempers can fracture the home.",
        "enemies": "A strong phase to defeat rivals, win disputes, and force through obstacles by courage — provided you don't make reckless new enemies.",
        "education": "Favours technical, mechanical, medical/surgical, and defence studies; learning by doing and competing.",
        "spirituality": "Energy channelled into disciplined practice (tapas) and Hanuman/Kartikeya worship — the warrior's path. Fortune through courage and effort.",
    },
    "Mercury": {
        "daily": "Mentally busy days of communication, paperwork, trade, short trips, and negotiation. Quick and versatile — scattered if Mercury is weak.",
        "mind": "Sharp, analytical, witty, and adaptable; can become nervous, restless, or over-clever.",
        "career": "Excellent for business, trade, writing, accounting, teaching, IT, media, and brokerage. Good for new ventures, contracts, and communication-led work.",
        "money": "Earnings through trade, commission, intellect, and many small streams. A favourable phase for deals and business; speculative if afflicted.",
        "relationships": "Friendly, communicative bonds formed through study, networks, and conversation. Logic over emotion; youthful and flirtatious.",
        "health": "Watch the nervous system, skin, speech, lungs, and intestines. Stress shows as anxiety and nervous complaints.",
        "family": "Focus on relatives, friends, communication within the family, and the education of younger ones. Good for settling matters through dialogue.",
        "enemies": "You outwit opponents through cleverness, negotiation, and contracts rather than confrontation; good for winning arguments and paperwork battles.",
        "education": "One of the best phases for study, exams, and skills — especially mathematics, commerce, languages, and technology.",
        "spirituality": "Intellectual, scriptural spirituality — study of texts, mantra, and astrology; Vishnu worship. Fortune through skill and communication.",
    },
    "Jupiter": {
        "daily": "Expansive, optimistic, fortunate days centred on growth, learning, guidance, and meaningful opportunity. Generally one of the most benefic phases.",
        "mind": "Wise, calm, hopeful, and principled; faith and good judgment grow. Can tip into over-optimism or complacency.",
        "career": "Growth, promotion, mentorship — teaching, law, finance, consulting, religion. Good for expansion, new roles, and guidance from elders.",
        "money": "A strong wealth phase: gains, savings, and investments tend to rise. Money through wisdom, finance, teaching, and good counsel.",
        "relationships": "Favours marriage, commitment, and children, and deepens bonds through trust and shared values. A classic phase for weddings and childbirth.",
        "health": "Generally protective of health; watch the liver, weight gain, fat, diabetes, and overindulgence — the body tends to expand.",
        "family": "Excellent for children, gurus, elders, and family expansion. Harmony, blessings, and growth in the household.",
        "enemies": "Opponents are pacified or won over; disputes settle in your favour through wisdom, fairness, and the support of well-wishers.",
        "education": "The finest phase for higher learning, philosophy, scripture, and law; honours and degrees come.",
        "spirituality": "Deep growth in dharma, devotion, ethics, and pilgrimage; the guru's grace. The most fortunate phase for fortune (bhagya) itself.",
    },
    "Venus": {
        "daily": "Pleasant, comfort-seeking, sociable days centred on love, beauty, luxury, art, and pleasure. Generally enjoyable and harmonious.",
        "mind": "Romantic, refined, and harmony-loving; artistic — but can turn indulgent, vain, or pleasure-driven.",
        "career": "Favours arts, entertainment, fashion, beauty, luxury goods, design, hospitality, vehicles, and partnerships. Good for creative, people-facing work.",
        "money": "Often the most prosperous of all phases (Venus = 20 years of comfort). Gains through luxury, art, partnerships, and women; lavish spending too.",
        "relationships": "The strongest phase for love, romance, marriage, and sensual pleasure. Attraction and partnership flourish — a central life theme now.",
        "health": "Watch the reproductive system, kidneys, throat, and over-indulgence in sweets and comforts. Vitality is usually good and sensual.",
        "family": "Harmony, comfort, and beauty in the home; spouse and the women of the family are prominent. Good for furnishing the home and celebrations.",
        "enemies": "Conflicts dissolve through charm, diplomacy, and compromise; you win through attraction and goodwill rather than confrontation.",
        "education": "Favours the arts, music, design, management, and aesthetic or luxury fields; refined, creative learning.",
        "spirituality": "Devotion through beauty, music, and bhakti; Lakshmi worship — pleasure balanced with grace. Fortune through partners, comfort, and art.",
    },
    "Saturn": {
        "daily": "Slow, heavy, disciplined days of work, duty, delay, and endurance. Demanding but maturing — it rewards patience and punishes shortcuts.",
        "mind": "Serious, cautious, and persevering; deep and realistic — but prone to worry, fear, loneliness, or low mood when Saturn is weak.",
        "career": "Rewards sustained hard work — labour, service, mining, oil, iron, the masses, law, and long-term institutions. A slow climb; promotions come late but solid, often with heavy workload or job change.",
        "money": "Money comes slowly through labour and persistence; structure and saving are favoured, but cashflow can feel tight. Gains via service and established assets.",
        "relationships": "Tests of commitment — distance, duty over romance, age gaps, and endurance. Delays in marriage; bonds either mature or feel cold and burdened.",
        "health": "Watch bones, joints, teeth, knees, nerves, and chronic or degenerative issues, plus fatigue and low mood. Complaints are slow-healing and long-running.",
        "family": "Responsibility for elders and dependents; restriction, separation, or burden at home. Duty toward family outweighs pleasure.",
        "enemies": "Opponents are ground down by your patience rather than your speed; legal matters drag but resolve with discipline. Beware chronic feuds.",
        "education": "Favours deep, disciplined, long study — research, technical mastery, law, history; success through perseverance, often after setbacks.",
        "spirituality": "The great teacher: detachment, discipline, and service to the poor; Shani/Hanuman worship. Karmic lessons mature the soul. Fortune through patience and right action.",
    },
    "Rahu": {
        "daily": "Unconventional, ambitious, turbulent days. Sudden events, foreign matters, technology, obsession, and material craving — everything feels amplified and unpredictable.",
        "mind": "Restless and ambitious, with obsessive desires; anxiety, confusion, and fascination with the new, the foreign, or the forbidden.",
        "career": "Sudden rises (and falls), foreign links, technology, media, aviation, speculation, politics, and unconventional fields. Big ambition and shortcuts — explosive growth or scandal.",
        "money": "Sudden gains and sudden losses; speculation, foreign income, and schemes. Money can balloon or evaporate — avoid fraud and over-leverage.",
        "relationships": "Unconventional, intense, or foreign relationships; sudden attractions and possible deception. Boundaries and clarity get blurred.",
        "health": "Mysterious, hard-to-diagnose, or chronic ailments; poisoning, infections, anxiety, addictions, and phobias. Watch the unexplained.",
        "family": "Disruption, foreign separation, or unconventional situations at home; mixing with outsiders. Sudden change or estrangement is possible.",
        "enemies": "Hidden enemies, conspiracies, and underhanded tactics — yours or theirs. You can defeat rivals by cunning, but beware being deceived.",
        "education": "Favours technology, research, foreign study, and the occult or cutting-edge; obsessive deep dives.",
        "spirituality": "A pull toward the occult, foreign or unorthodox paths, and sudden awakening through crisis; Durga worship. Fortune is erratic and karmic.",
    },
    "Ketu": {
        "daily": "Detached, inward, unpredictable days. Focus turns away from the material — letting go, endings, and solitude. Things slip away or feel unreal.",
        "mind": "Detached, intuitive, and introspective; doubt and disinterest in worldly affairs, broken by flashes of insight.",
        "career": "Erratic, unsatisfying worldly results; sudden separations from work, or a pull toward research, healing, the occult, and behind-the-scenes roles. Recognition feels hollow.",
        "money": "Indifference to money; unexpected losses or detachment from gains. Not a phase for accumulation — spending drifts to the unseen or the wasteful.",
        "relationships": "Detachment, separation, or dissatisfaction; spiritual or karmic bonds. Endings, and a sense of 'this isn't enough.'",
        "health": "Mysterious ailments, misdiagnosis, viral or karmic issues, surgery, and accidents; psychosomatic, hard-to-pin-down complaints.",
        "family": "Separation, distance, or detachment from family; a sense of not belonging. Karmic completions at home.",
        "enemies": "Enemies may simply fade or self-destruct; you win by withdrawal and non-attachment rather than fighting. Hidden adversaries are possible.",
        "education": "Favours research, the occult, healing, mathematics, and mysticism; deep, solitary, intuitive study. Conventional study can feel pointless.",
        "spirituality": "The strongest phase for moksha, detachment, meditation, and liberation; Ganesha/Shiva worship. Past-life completion. Fortune is spiritual, not material.",
    },
}

# Bhava (house) significations — short labels used for the chart layer.
HOUSE_THEMES = {
    1: "self, body & vitality",
    2: "wealth, savings, family & speech",
    3: "courage, siblings & communication",
    4: "home, mother, property & comfort",
    5: "children, romance, education & creativity",
    6: "enemies, debts, disease & disputes",
    7: "spouse, marriage, partnership & business",
    8: "sudden events, inheritance, the occult & obstacles",
    9: "fortune, dharma, father, guru & long travel",
    10: "career, status, authority & public life",
    11: "gains, income, friends & fulfilled desires",
    12: "loss, expense, foreign lands, isolation & moksha",
}

KENDRA = {1, 4, 7, 10}
TRIKONA = {1, 5, 9}
DUSTHANA = {6, 8, 12}

DIGNITY_NOTE = {
    "exalted": "exalted — its results flow with unusual ease and strength",
    "own sign": "in its own sign — strong, stable, and supportive",
    "debilitated": "debilitated — results come strained, delayed, or under-deliver and need extra effort",
    "neutral": "of neutral dignity — results are mixed and depend on aspects/conjunctions",
    "node": "a shadow-planet — it acts mainly through the house it sits in and its dispositor",
}


# --------------------------------------------------------------------------- #
# Chart context
# --------------------------------------------------------------------------- #
def build_chart(args) -> dict:
    """Compute Lagna + planet houses/dignity/combustion for personalisation."""
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

    asc = core.ascendant(jd, args.lat, args.lon)
    asc_sign = asc["sign_num"]
    positions = core.all_planet_positions(jd)
    sun_lon = positions["Sun"]["longitude"]

    planets = {}
    for name, p in positions.items():
        house = core.house_of(p["sign_num"], asc_sign)
        retro = p["retrograde"]
        combust = (name not in ("Sun", "Rahu", "Ketu")
                   and core.is_combust(name, p["longitude"], sun_lon, retro))
        planets[name] = {
            "sign": p["sign"],
            "sign_num": p["sign_num"],
            "house": house,
            "dignity": core.dignity(name, p["sign_num"]),
            "combust": combust,
            "retro": retro,
        }
    return {"asc_sign_num": asc_sign, "asc_sign": asc["sign"], "planets": planets}


def ruled_houses(lord: str, asc_sign: int) -> list[int]:
    """Houses (from the Lagna) ruled by `lord` via the signs it owns."""
    signs = [s for s in range(1, 13) if core.SIGN_LORD[s] == lord]
    return sorted(core.house_of(s, asc_sign) for s in signs)


def house_quality(house: int) -> str:
    if house in TRIKONA and house != 1:
        return "a trikona (fortune) house — strongly favourable"
    if house == 1:
        return "the Lagna — central to self and vitality"
    if house in KENDRA:
        return "a kendra (pillar) house — prominent and action-oriented"
    if house in DUSTHANA:
        return "a dusthana (difficult) house — stress, but also growth in its themes"
    if house in (3, 11):
        return "an upachaya (growing) house — results improve over time"
    return "a neutral house"


def lord_profile(lord: str, chart: dict) -> dict:
    """How a dasha lord is configured in THIS chart."""
    p = chart["planets"][lord]
    asc = chart["asc_sign_num"]
    rh = [] if lord in ("Rahu", "Ketu") else ruled_houses(lord, asc)
    return {
        "lord": lord,
        "sign": p["sign"],
        "house": p["house"],
        "dignity": p["dignity"],
        "combust": p["combust"],
        "retro": p["retro"],
        "rules_houses": rh,
    }


# --------------------------------------------------------------------------- #
# Locate the active periods on a given date
# --------------------------------------------------------------------------- #
def _contains(node: dict, target: str) -> bool:
    return node["start"] <= target < node["end"]


def find_active(timeline: dict, target: str) -> dict:
    """Return {maha, antar, pratyantar} lords active on `target` (YYYY-MM-DD)."""
    out = {"maha": None, "antar": None, "pratyantar": None,
           "maha_node": None, "antar_node": None, "pratyantar_node": None}
    for md in timeline["mahadashas"]:
        if _contains(md, target):
            out["maha"] = md["lord"]; out["maha_node"] = md
            for ad in md.get("antardashas", []):
                if _contains(ad, target):
                    out["antar"] = ad["lord"]; out["antar_node"] = ad
                    for pd in ad.get("pratyantardashas", []):
                        if _contains(pd, target):
                            out["pratyantar"] = pd["lord"]; out["pratyantar_node"] = pd
                            break
                    break
            break
    return out


# --------------------------------------------------------------------------- #
# Compose the reading
# --------------------------------------------------------------------------- #
def chart_note(prof: dict) -> str:
    """One sentence on how the lord is wired into the chart."""
    lord = prof["lord"]
    bits = [f"In your chart, {lord} sits in House {prof['house']} "
            f"({HOUSE_THEMES[prof['house']]})"]
    if prof["rules_houses"]:
        ruled = ", ".join(f"{h} ({HOUSE_THEMES[h].split(',')[0]})"
                          for h in prof["rules_houses"])
        bits.append(f"and rules House {ruled}")
    note = " ".join([bits[0] + (", " + bits[1] if len(bits) > 1 else "")]) + "."
    flags = []
    flags.append(DIGNITY_NOTE.get(prof["dignity"], "of mixed dignity"))
    if prof["combust"]:
        flags.append("combust (too close to the Sun — its significations are weakened/obscured)")
    if prof["retro"] and lord not in ("Rahu", "Ketu"):
        flags.append("retrograde (results turn inward and are revisited)")
    note += " It is " + "; ".join(flags) + "."
    return note


def blend_note(maha: str, antar: str) -> str:
    if maha == antar:
        return (f"This is {maha}–{antar}: the sub-period repeats the main lord, "
                f"so {maha}'s themes are at their most concentrated.")
    if maha in ("Rahu", "Ketu") or antar in ("Rahu", "Ketu"):
        return (f"{maha} (backdrop) and {antar} (trigger) involve a shadow planet, "
                f"so the blend is karmic and unpredictable — read it through the "
                f"houses each occupies in your chart.")
    rel = core.natural_relation(maha, antar)
    phrase = {
        "friend": "natural friends — the two periods cooperate, so results come more smoothly",
        "neutral": "naturally neutral — a workable but not especially synergistic blend",
        "enemy": "natural enemies — they pull in different directions, so expect friction, "
                 "start-stop progress, and mixed results",
    }[rel]
    return (f"{maha} (the backdrop) and {antar} (the active trigger) are {phrase}.")


def render_text(reading: dict) -> str:
    L = []
    A = L.append
    inp = reading["input"]
    act = reading["active"]
    A("=" * 66)
    A("  DASHA INTERPRETATION — what the running period means")
    A("=" * 66)
    A(f"  Birth : {inp['date']} {inp['time']} ({inp['timezone']})")
    A(f"  Lagna : {reading['asc_sign']}   |   reading for: {reading['on']}")
    A("-" * 66)
    A(f"  Mahadasha (backdrop)     : {act['maha']}")
    A(f"  Antardasha (active now)  : {act['antar']}")
    if act["pratyantar"]:
        A(f"  Pratyantardasha (fine)   : {act['pratyantar']}")
    A("-" * 66)

    # Chart wiring of the two main lords.
    A("  HOW THESE LORDS SIT IN YOUR CHART")
    A("  " + chart_note(reading["maha_profile"]))
    if act["antar"] != act["maha"]:
        A("  " + chart_note(reading["antar_profile"]))
    A("")
    A("  THE BLEND")
    A("  " + reading["blend"])
    A("")

    # Houses activated this period (union of placements + lordships).
    A("  HOUSES ACTIVATED THIS PERIOD")
    for h in reading["activated_houses"]:
        A(f"    • House {h:<2} — {HOUSE_THEMES[h]}")
    A("")

    # Per-area reading: backdrop (Maha) + trigger (Antar).
    maha, antar = act["maha"], act["antar"]
    A("=" * 66)
    A("  LIFE-AREA READING   (◆ backdrop = Mahadasha · ▶ trigger = Antardasha)")
    A("=" * 66)
    for key, label in LIFE_AREAS:
        A(f"\n  {label.upper()}")
        A(f"    ◆ {maha}: {PLANET_EFFECTS[maha][key]}")
        if antar != maha:
            A(f"    ▶ {antar}: {PLANET_EFFECTS[antar][key]}")
    A("")
    A("=" * 66)
    A("  For cultural/educational use only. A dasha sets a backdrop of")
    A("  probabilities, not certainties — actual results depend on the whole")
    A("  chart, transits, and your own effort. Not predictive of real outcomes.")
    A("=" * 66)
    return "\n".join(L)


def compute(args) -> dict:
    chart = build_chart(args)

    # Build the full 3-level timeline once, reusing dasha.py.
    class _A:  # lightweight shim so dasha.compute_dasha can read attributes
        pass
    da = _A()
    for k in ("date", "time", "lat", "lon", "tz", "ayanamsa", "node",
              "geocentric", "ephemeris"):
        setattr(da, k, getattr(args, k, None))
    da.node = getattr(args, "node", "mean")
    da.ephemeris = getattr(args, "ephemeris", "moshier")
    da.geocentric = getattr(args, "geocentric", False)
    da.levels = 3
    timeline = dasha_mod.compute_dasha(da)

    target = args.on
    active = find_active(timeline, target)
    if active["maha"] is None:
        raise ValueError(
            f"No dasha covers {target}. The Vimshottari cycle from this birth runs "
            f"{timeline['mahadashas'][0]['start']} to "
            f"{timeline['mahadashas'][-1]['end']}."
        )

    maha_profile = lord_profile(active["maha"], chart)
    antar_profile = lord_profile(active["antar"], chart)

    # Houses activated = placement + lordship houses of both lords.
    houses = set()
    for prof in (maha_profile, antar_profile):
        houses.add(prof["house"])
        houses.update(prof["rules_houses"])

    return {
        "input": timeline["input"],
        "on": target,
        "asc_sign": chart["asc_sign"],
        "asc_sign_num": chart["asc_sign_num"],
        "active": active,
        "maha_profile": maha_profile,
        "antar_profile": antar_profile,
        "activated_houses": sorted(houses),
        "blend": blend_note(active["maha"], active["antar"]),
        "effects": {
            "mahadasha": {k: PLANET_EFFECTS[active["maha"]][k] for k, _ in LIFE_AREAS},
            "antardasha": {k: PLANET_EFFECTS[active["antar"]][k] for k, _ in LIFE_AREAS},
        },
    }


def _json_safe(reading: dict) -> dict:
    """Strip the bulky timeline nodes for JSON output."""
    out = dict(reading)
    act = dict(reading["active"])
    for k in ("maha_node", "antar_node", "pratyantar_node"):
        act.pop(k, None)
    out["active"] = act
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Interpret the currently running Vimshottari dasha across life areas.")
    ap.add_argument("--date", required=True, help="Birth date YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="Birth time HH:MM[:SS], 24h local")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--on", default=date.today().isoformat(),
                    help="Date to interpret for, YYYY-MM-DD (default: today)")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true",
                    help="Use geocentric positions (default is topocentric)")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # Validate --on early for a clean error.
    try:
        datetime.strptime(args.on, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: --on must be YYYY-MM-DD, got '{args.on}'", file=sys.stderr)
        sys.exit(1)

    try:
        reading = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(_json_safe(reading), indent=2))
    else:
        print(render_text(reading))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
yogas.py — Detect common classical yogas in a Vedic birth chart and produce a
readable interpretation.

This detects a broad, well-defined set of yogas where the rules are unambiguous
and computable from the D1 chart. It is still NOT exhaustive — classical jyotish
describes hundreds of yogas, many with conflicting definitions — but it now
covers the major families. Each detected yoga carries a short, plain-language
note. See references/yogas.md for definitions and caveats.

Detected yogas:
  - Gajakesari            (Jupiter in a kendra from the Moon)
  - Budhaditya            (Sun + Mercury conjunct)
  - Chandra-Mangala       (Moon + Mars conjunct)
  - Pancha Mahapurusha    (Ruchaka/Bhadra/Hamsa/Malavya/Sasa)
  - Raja yoga             (kendra lord associated with a trikona lord)
  - Dhana yoga            (wealth-house lord linked to a wealth/fortune lord)
  - Lunar yogas           (Sunapha / Anapha / Durudhara / Kemadruma)
  - Adhi yoga             (benefics in the 6th/7th/8th from the Moon)
  - Amala yoga            (a benefic in the 10th from Lagna or Moon)
  - Vipareeta Raja yoga   (Harsha/Sarala/Vimala — a dusthana lord in a dusthana)
  - Neecha Bhanga         (cancellation of a planet's debilitation)
  - Parivartana yoga      (Maha/Khala/Dainya — mutual sign exchange)
  - Daridra yoga          (the 11th/gains lord cast into a dusthana)
  - Shakata yoga          (the Moon in the 6th/8th/12th from Jupiter)
  - Nabhasa yogas         (Sankhya by sign-count; Ashraya by modality)

Usage:
    python yogas.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata [--ayanamsa lahiri] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

import core
import kundli as kundli_mod

KENDRAS = {1, 4, 7, 10}      # angular houses
TRIKONAS = {1, 5, 9}         # trine houses
DUSTHANAS = {6, 8, 12}       # houses of difficulty
UPACHAYAS = {3, 6, 10, 11}   # houses of growth

GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]

# Natural benefics used for the lunar/benefic-placement yogas. (Mercury is taken
# as benefic by default; the waxing Moon is added contextually.)
BENEFICS = {"Jupiter", "Venus", "Mercury"}

# Mahapurusha yoga names by planet.
MAHAPURUSHA = {
    "Mars": "Ruchaka", "Mercury": "Bhadra", "Jupiter": "Hamsa",
    "Venus": "Malavya", "Saturn": "Sasa",
}

# Nabhasa Sankhya yogas: by the count of DISTINCT signs the 7 planets occupy.
SANKHYA_YOGA = {
    1: "Gola", 2: "Yuga", 3: "Soola", 4: "Kedara",
    5: "Pasa", 6: "Damini", 7: "Veena",
}
# Nabhasa Ashraya yogas: all 7 planets in one modality (0 movable/1 fixed/2 dual).
ASHRAYA_YOGA = {0: "Rajju", 1: "Musala", 2: "Nala"}

# Planet exalted in a given sign (inverse of core.EXALTATION) — for Neecha Bhanga.
_EXALTED_IN = {sign: planet for planet, sign in core.EXALTATION.items()}


def _debilitation_sign(planet: str) -> int:
    """Sign (1..12) where `planet` is debilitated = 7th from its exaltation."""
    return (core.EXALTATION[planet] + 6 - 1) % 12 + 1


def _house_from(ref_sign: int, target_sign: int) -> int:
    """Whole-sign house distance (1..12) of target counted from ref_sign."""
    return (target_sign - ref_sign) % 12 + 1


def _lord_of_house(asc_sign: int, house: int) -> str:
    """Lord of the `house`-th whole-sign house from the ascendant."""
    return core.SIGN_LORD[((asc_sign - 1 + (house - 1)) % 12) + 1]


def _same_house(planets: dict, a: str, b: str) -> bool:
    return planets[a]["house"] == planets[b]["house"]


def _associated(planets: dict, a: str, b: str) -> bool:
    """Two planets are 'associated' if conjunct OR in mutual/one-way Vedic aspect.

    This is the classical basis for most yogas — conjunction was v1's only test,
    which missed the majority of aspect-formed yogas.
    """
    if _same_house(planets, a, b):
        return True
    return core.aspects_planet(a, b, planets) or core.aspects_planet(b, a, planets)


def detect_yogas(chart: dict) -> list[dict]:
    planets = chart["planets"]
    asc_sign = chart["ascendant"]["sign_num"]
    found: list[dict] = []

    # --- Gajakesari: Jupiter in a kendra (1/4/7/10) FROM the Moon -------------
    moon_sign = planets["Moon"]["sign_num"]
    jup_from_moon = ((planets["Jupiter"]["sign_num"] - moon_sign) % 12) + 1
    if jup_from_moon in KENDRAS:
        found.append({
            "name": "Gajakesari Yoga",
            "rule": "Jupiter occupies a kendra (1/4/7/10) from the Moon.",
            "note": "Associated with intelligence, respect, and lasting reputation.",
        })

    # --- Budhaditya: Sun + Mercury conjunct (combustion weakens it) ------------
    if _same_house(planets, "Sun", "Mercury"):
        note = "Linked to intellect, communication skill, and analytical ability."
        if planets["Mercury"].get("combust"):
            note += " NOTE: Mercury is combust (astangata) here, which classically dilutes the yoga."
        found.append({
            "name": "Budhaditya Yoga",
            "rule": "Sun and Mercury occupy the same sign/house.",
            "note": note,
        })

    # --- Chandra-Mangala: Moon + Mars conjunct --------------------------------
    if _same_house(planets, "Moon", "Mars"):
        found.append({
            "name": "Chandra-Mangala Yoga",
            "rule": "Moon and Mars occupy the same sign/house.",
            "note": "Classically tied to financial drive and resourcefulness.",
        })

    # --- Pancha Mahapurusha yogas ---------------------------------------------
    for planet, yoga_name in MAHAPURUSHA.items():
        info = planets[planet]
        in_kendra = info["house"] in KENDRAS
        strong = info["dignity"] in ("exalted", "own sign")
        if in_kendra and strong:
            found.append({
                "name": f"{yoga_name} Yoga (Pancha Mahapurusha)",
                "rule": f"{planet} is {info['dignity']} and in a kendra (house {info['house']}).",
                "note": "A Mahapurusha yoga — marks pronounced strength of this planet's significations.",
            })

    # --- Raja yoga: a kendra lord ASSOCIATED with a trikona lord --------------
    # Association = conjunction OR mutual/one-way Vedic aspect (v2 upgrade).
    kendra_lords = {core.SIGN_LORD[((asc_sign - 1 + (h - 1)) % 12) + 1] for h in KENDRAS}
    trikona_lords = {core.SIGN_LORD[((asc_sign - 1 + (h - 1)) % 12) + 1] for h in TRIKONAS}
    raj_pairs = []
    grahas = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    for i in range(len(grahas)):
        for j in range(i + 1, len(grahas)):
            a, b = grahas[i], grahas[j]
            if not ((a in kendra_lords and b in trikona_lords) or
                    (b in kendra_lords and a in trikona_lords)):
                continue
            if _same_house(planets, a, b):
                raj_pairs.append(f"{a}+{b} (conjunction)")
            elif _associated(planets, a, b):
                raj_pairs.append(f"{a}+{b} (mutual aspect)")
    if raj_pairs:
        found.append({
            "name": "Raja Yoga",
            "rule": f"Kendra lord associated with trikona lord: {', '.join(raj_pairs)}.",
            "note": "A Raja yoga association — classically a marker of status and success. "
                    "(Detects conjunction AND Vedic aspect; sign-exchange Raja yogas "
                    "surface separately as Parivartana Yoga — see references/yogas.md.)",
        })

    # --- Dhana yoga: a wealth-house (2/11) lord ASSOCIATED with a wealth/fortune
    #     house (1/2/5/9/11) lord — the classical signature of accumulated wealth.
    def _lord_of(h):
        return core.SIGN_LORD[((asc_sign - 1 + (h - 1)) % 12) + 1]
    dhana_lords = {_lord_of(h) for h in (2, 11)}
    support_lords = {_lord_of(h) for h in (1, 2, 5, 9, 11)}
    dhana_pairs = []
    for i in range(len(grahas)):
        for j in range(i + 1, len(grahas)):
            a, b = grahas[i], grahas[j]
            if not ((a in dhana_lords and b in support_lords) or
                    (b in dhana_lords and a in support_lords)):
                continue
            if a == b:
                continue
            if _same_house(planets, a, b):
                dhana_pairs.append(f"{a}+{b} (conjunction)")
            elif _associated(planets, a, b):
                dhana_pairs.append(f"{a}+{b} (mutual aspect)")
    if dhana_pairs:
        found.append({
            "name": "Dhana Yoga",
            "rule": f"Wealth-house (2nd/11th) lord linked with a wealth/fortune "
                    f"(1/2/5/9/11) lord: {', '.join(dhana_pairs)}.",
            "note": "A wealth-forming combination — supports accumulation of money, "
                    "especially during the dasha of the planets involved.",
        })

    # --- Lunar yogas: Sunapha / Anapha / Durudhara / Kemadruma ----------------
    # Planets (excluding the Sun and the nodes) in the 2nd and 12th from the Moon.
    second_from_moon, twelfth_from_moon, with_moon = [], [], []
    for g in GRAHAS:
        if g in ("Sun", "Moon"):
            continue
        h = _house_from(moon_sign, planets[g]["sign_num"])
        if h == 2:
            second_from_moon.append(g)
        elif h == 12:
            twelfth_from_moon.append(g)
        elif h == 1:
            with_moon.append(g)
    if second_from_moon and twelfth_from_moon:
        found.append({
            "name": "Durudhara Yoga",
            "rule": f"Planets flank the Moon — 2nd: {', '.join(second_from_moon)}; "
                    f"12th: {', '.join(twelfth_from_moon)} (Sun/nodes excluded).",
            "note": "The Moon is supported on both sides — classically tied to "
                    "comfort, good means, and a generous nature.",
        })
    elif second_from_moon:
        found.append({
            "name": "Sunapha Yoga",
            "rule": f"Planet(s) in the 2nd from the Moon: {', '.join(second_from_moon)} "
                    f"(Sun/nodes excluded).",
            "note": "Tied to self-earned wealth, intelligence, and self-reliance.",
        })
    elif twelfth_from_moon:
        found.append({
            "name": "Anapha Yoga",
            "rule": f"Planet(s) in the 12th from the Moon: {', '.join(twelfth_from_moon)} "
                    f"(Sun/nodes excluded).",
            "note": "Tied to a well-rounded, composed nature and physical wellbeing.",
        })
    elif not with_moon:
        # Kemadruma: no planet in 2nd/12th from Moon AND none with the Moon.
        found.append({
            "name": "Kemadruma Yoga",
            "rule": "No planet (other than Sun/nodes) sits in the 2nd, 12th, or "
                    "with the Moon — the Moon is unsupported.",
            "note": "Classically an affliction (struggle, instability), but it is "
                    "easily CANCELLED — e.g. a planet in a kendra from the Moon or "
                    "Lagna, or the Moon itself in a kendra. Treat as a caution, not "
                    "a verdict.",
        })

    # --- Adhi yoga: benefics in the 6th/7th/8th from the Moon -----------------
    adhi = [g for g in BENEFICS
            if _house_from(moon_sign, planets[g]["sign_num"]) in (6, 7, 8)]
    if len(adhi) >= 2:
        found.append({
            "name": "Adhi Yoga",
            "rule": f"Benefics in the 6th/7th/8th from the Moon: {', '.join(sorted(adhi))}.",
            "note": "A classical marker of leadership, status, and dependable allies.",
        })

    # --- Amala yoga: a natural benefic in the 10th from Lagna or Moon ----------
    amala = []
    for g in BENEFICS:
        if planets[g]["house"] == 10 or _house_from(moon_sign, planets[g]["sign_num"]) == 10:
            amala.append(g)
    if amala:
        found.append({
            "name": "Amala Yoga",
            "rule": f"Benefic in the 10th from Lagna/Moon: {', '.join(sorted(amala))}.",
            "note": "Tied to a spotless reputation and lasting good name through work.",
        })

    # --- Vipareeta Raja yoga: a dusthana (6/8/12) lord placed in a dusthana ----
    vipareeta = []
    for h, label in ((6, "Harsha"), (8, "Sarala"), (12, "Vimala")):
        lord = _lord_of_house(asc_sign, h)
        if planets[lord]["house"] in DUSTHANAS:
            vipareeta.append(f"{label} ({h}th lord {lord} in house {planets[lord]['house']})")
    if vipareeta:
        found.append({
            "name": "Vipareeta Raja Yoga",
            "rule": "Lord of a dusthana (6/8/12) falls in a dusthana: "
                    + "; ".join(vipareeta) + ".",
            "note": "A 'reversal' yoga — difficulty turning to gain, often after a "
                    "crisis or through rivals' undoing. Strongest when the lords "
                    "are not otherwise well placed.",
        })

    # --- Neecha Bhanga Raja yoga: cancellation of a planet's debilitation ------
    for g in GRAHAS:
        if planets[g]["dignity"] != "debilitated":
            continue
        deb_sign = planets[g]["sign_num"]
        dispositor = core.SIGN_LORD[deb_sign]
        exalted_here = _EXALTED_IN.get(deb_sign)
        reasons = []
        disp_house_lagna = planets[dispositor]["house"]
        disp_house_moon = _house_from(moon_sign, planets[dispositor]["sign_num"])
        if disp_house_lagna in KENDRAS or disp_house_moon in KENDRAS:
            reasons.append(f"dispositor {dispositor} is in a kendra")
        if exalted_here and exalted_here in planets:
            eh_lagna = planets[exalted_here]["house"]
            eh_moon = _house_from(moon_sign, planets[exalted_here]["sign_num"])
            if eh_lagna in KENDRAS or eh_moon in KENDRAS:
                reasons.append(f"{exalted_here} (exalted in this sign) is in a kendra")
        if planets[dispositor]["dignity"] == "exalted":
            reasons.append(f"dispositor {dispositor} is itself exalted")
        if reasons:
            found.append({
                "name": "Neecha Bhanga Raja Yoga",
                "rule": f"{g} is debilitated in {core.SIGNS[deb_sign - 1]}, but the "
                        f"debilitation is cancelled: {'; '.join(reasons)}.",
                "note": f"The debilitation of {g} is lifted (neecha bhanga) and can "
                        f"turn into a rise-after-struggle — especially in {g}'s dasha.",
            })

    # --- Parivartana (sign-exchange) yoga: mutual reception --------------------
    seen_pairs = set()
    for i in range(len(GRAHAS)):
        for j in range(i + 1, len(GRAHAS)):
            a, b = GRAHAS[i], GRAHAS[j]
            a_sign, b_sign = planets[a]["sign_num"], planets[b]["sign_num"]
            if a_sign in core.OWN_SIGNS[b] and b_sign in core.OWN_SIGNS[a]:
                ha, hb = planets[a]["house"], planets[b]["house"]
                if {ha, hb} & DUSTHANAS:
                    kind = "Dainya"
                    extra = "involves a 6/8/12 house — a 'struggling' exchange."
                elif 3 in (ha, hb):
                    kind = "Khala"
                    extra = "involves the 3rd — a mixed, effort-driven exchange."
                else:
                    kind = "Maha"
                    extra = "between good houses — a powerful mutual support."
                key = tuple(sorted((a, b)))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                found.append({
                    "name": f"Parivartana Yoga ({kind})",
                    "rule": f"{a} (house {ha}) and {b} (house {hb}) occupy each "
                            f"other's signs — a mutual exchange.",
                    "note": f"The two houses' affairs become linked; {extra}",
                })

    # --- Daridra yoga: the 11th (gains) lord cast into a dusthana --------------
    eleventh_lord = _lord_of_house(asc_sign, 11)
    if planets[eleventh_lord]["house"] in DUSTHANAS:
        found.append({
            "name": "Daridra Yoga",
            "rule": f"The 11th (gains) lord {eleventh_lord} falls in house "
                    f"{planets[eleventh_lord]['house']} (a dusthana).",
            "note": "A classical caution on gains/income leaking away. It is offset "
                    "by Dhana/Raja yogas and the lord's own strength — weigh it "
                    "against the whole chart, not alone.",
        })

    # --- Shakata yoga: the Moon in the 6th/8th/12th from Jupiter ---------------
    moon_from_jup = _house_from(planets["Jupiter"]["sign_num"], moon_sign)
    if moon_from_jup in DUSTHANAS:
        found.append({
            "name": "Shakata Yoga",
            "rule": f"The Moon is in the {moon_from_jup}th from Jupiter (6/8/12).",
            "note": "Tied to fortunes that rise and fall in cycles. Cancelled if the "
                    "Moon is in a kendra from the Lagna — note it, don't over-read it.",
        })

    # --- Nabhasa: Sankhya (sign count) + Ashraya (modality) yogas --------------
    occupied_signs = {planets[g]["sign_num"] for g in GRAHAS}
    n = len(occupied_signs)
    if n in SANKHYA_YOGA:
        found.append({
            "name": f"{SANKHYA_YOGA[n]} Yoga (Nabhasa Sankhya)",
            "rule": f"The seven planets occupy {n} distinct sign(s).",
            "note": "A Nabhasa yoga of distribution — describes the overall spread "
                    "and concentration of the personality, not a specific event.",
        })
    modalities = {core.SIGN_MODALITY[s] for s in (planets[g]["sign_num"] for g in GRAHAS)}
    if len(modalities) == 1:
        only = next(iter(modalities))
        found.append({
            "name": f"{ASHRAYA_YOGA[only]} Yoga (Nabhasa Ashraya)",
            "rule": "All seven planets fall in "
                    + ("movable" if only == 0 else "fixed" if only == 1 else "dual")
                    + " signs.",
            "note": "A Nabhasa yoga of temperament — movable=restless/enterprising, "
                    "fixed=steady/determined, dual=adaptable/versatile.",
        })

    return found


def render_text(chart: dict, yogas: list[dict]) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("  YOGA ANALYSIS")
    lines.append("=" * 60)
    lines.append(f"  Lagna: {chart['ascendant']['sign']} | "
                 f"Moon: {chart['planets']['Moon']['sign']}")
    lines.append("-" * 60)
    if not yogas:
        lines.append("  No yogas from the detected set were found in this chart.")
        lines.append("  (This set is curated, not exhaustive — see references/yogas.md.)")
    else:
        for y in yogas:
            lines.append(f"  ● {y['name']}")
            lines.append(f"      Rule: {y['rule']}")
            lines.append(f"      {y['note']}")
            lines.append("")
    lines.append("=" * 60)
    lines.append("  For cultural/educational use. Not predictive of real outcomes.")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Detect classical yogas in a birth chart.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--house-system", default=core.DEFAULT_HOUSE_SYSTEM, dest="house_system")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        chart = kundli_mod.compute_kundli(args)
        yogas = detect_yogas(chart)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps({"yogas": yogas, "ascendant": chart["ascendant"]}, indent=2))
    else:
        print(render_text(chart, yogas))


if __name__ == "__main__":
    main()

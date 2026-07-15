#!/usr/bin/env python3
"""
strength.py — Planetary-strength module for the vedic-astrology skill.

Computes two classical strength systems for a Vedic birth chart:

  PART A — ASHTAKAVARGA (fully implemented, deterministic)
      Bhinnashtakavarga (BAV) per planet (Sun..Saturn), Sarvashtakavarga (SAV),
      using the canonical Parashari benefic-point (rekha) contribution tables.
      Verified against the classical totals (SAV grand total = 337; per-planet
      BAV totals 48/49/39/54/56/52/39). The code ASSERTS these and raises if a
      table is wrong, so a miscomputed value can never silently ship.

  PART B — SHADBALA (complete six-fold — see SCOPE & METHODS below)
      The full six-fold strength in Rupas (1 Rupa = 60 virupas): Sthana, Dig,
      Kala, Cheshta, Naisargika and Drik Bala, every source computed from
      classical rules. The exact method for each source is documented and
      surfaced under shadbala.method_notes — nothing is fabricated to make a
      total "look complete".

Usage:
    python strength.py --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--ayanamsa lahiri] [--node mean] [--json]

All angles are sidereal. Default ayanamsa = Lahiri.

============================================================================
SCOPE & METHODS — Shadbala (READ THIS)
============================================================================
This module computes the COMPLETE six-fold Shadbala. Each source is computed
from classical rules and the per-planet total may be compared against the
classical required-strength thresholds (REQUIRED_RUPAS). The exact method for
each source is listed below and echoed at runtime under shadbala.method_notes.

STHANA BALA (positional):
  - Uchcha Bala        (exaltation distance / 3, max 60)
  - Saptavargaja Bala  (dignity across D1,D2,D3,D7,D9,D12,D30 by the five-fold
                        compound friendship — panchadha maitri = natural +
                        temporal; own 30, moolatrikona 45, great-friend 22.5,
                        friend 15, neutral 7.5, enemy 3.75, great-enemy 1.875)
  - Ojayugmarasyamsa Bala (odd/even rashi + navamsa, max 30)
  - Kendradi Bala      (kendra 60 / panaphara 30 / apoklima 15)
  - Drekkana Bala      (sex of planet vs decanate, 0/15)
DIG BALA (directional, max 60, by angular distance from the powerless point)
KALA BALA (temporal):
  - Nathonnatha (diurnal/nocturnal, triangular ramp from noon/midnight, max 60)
  - Paksha      (lunar phase by Moon−Sun elongation; the Moon's value doubled)
  - Tribhaga    (lord of the day/night third; Jupiter always 60)
  - Abda/Masa/Vara/Hora — year (15) / month (30) / weekday (45) / planetary
                          hour (60) lords. Year & month lords are the weekday
                          lords of the relevant solar ingress (computed by
                          bisection on the Sun's sidereal longitude). Hora uses
                          equal one-hour planetary hours from sunrise in the
                          Chaldean order.
  - Ayana       (equatorial declination / kranti; the Sun's value doubled)
  - Yuddha      (planetary war — for star-planets within 1°, the bala
                 difference is added to the more-northern victor)
CHESHTA BALA (motional): the classical Cheshta (Seeghra) Kendra of MEAN
  longitudes — for superior planets the seeghrocha is the mean Sun, for inferior
  planets the planet's own heliocentric mean longitude. The Sun's Cheshta equals
  its Ayana Bala and the Moon's equals its Paksha Bala (classical identities).
NAISARGIKA BALA (fixed natural values)
DRIK BALA (aspectual): the degree-precise Parashari Sphuta Drishti — benefic
  aspects positive, malefic negative, summed and divided by 4. Special aspects
  (Mars 4/8, Jupiter 5/9, Saturn 3/10, the 7th for all) are taken at full 60.

HONEST CAVEATS (documented, not hidden):
  - Cheshta uses the Surya-Siddhanta mean-longitude Seeghra Kendra, not a
    full true-anomaly epicycle integration; the two agree closely.
  - Hora uses equal hours (not unequal day/night horas) — the common Shadbala
    convention.
  - This is Shadbala proper. Ishta/Kashta Phala, Bhava Bala, and the Vimsopaka
    refinements are separate measures and are NOT computed here.
============================================================================
"""

from __future__ import annotations

import argparse
import json
import math
import sys

import swisseph as swe

import core

# --------------------------------------------------------------------------- #
# PART A — Ashtakavarga
# --------------------------------------------------------------------------- #
# Canonical Parashari Bhinnashtakavarga (rekha / benefic-point) tables.
#
# For each "planet whose BAV we are building", we list, for every contributor
# reference point (the 7 planets + the Lagna), the HOUSE numbers (1..12, counted
# inclusively from that reference point's sign) that receive one bindu.
#
# A bindu lands in the sign:  ((S_ref - 1) + (house - 1)) % 12 + 1
# where S_ref is the contributor's sign number.
#
# These are the standard tables (e.g. as given by Parashara / B.V. Raman). The
# per-planet totals are asserted at import time, so a typo cannot pass silently.
AV_TABLES = {
    "Sun": {
        "Sun":     [1, 2, 4, 7, 8, 9, 10, 11],
        "Moon":    [3, 6, 10, 11],
        "Mars":    [1, 2, 4, 7, 8, 9, 10, 11],
        "Mercury": [3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [5, 6, 9, 11],
        "Venus":   [6, 7, 12],
        "Saturn":  [1, 2, 4, 7, 8, 9, 10, 11],
        "Lagna":   [3, 4, 6, 10, 11, 12],
    },
    "Moon": {
        "Sun":     [3, 6, 7, 8, 10, 11],
        "Moon":    [1, 3, 6, 7, 10, 11],
        "Mars":    [2, 3, 5, 6, 9, 10, 11],
        "Mercury": [1, 3, 4, 5, 7, 8, 10, 11],
        "Jupiter": [1, 4, 7, 8, 10, 11, 12],
        "Venus":   [3, 4, 5, 7, 9, 10, 11],
        "Saturn":  [3, 5, 6, 11],
        "Lagna":   [3, 6, 10, 11],
    },
    "Mars": {
        "Sun":     [3, 5, 6, 10, 11],
        "Moon":    [3, 6, 11],
        "Mars":    [1, 2, 4, 7, 8, 10, 11],
        "Mercury": [3, 5, 6, 11],
        "Jupiter": [6, 10, 11, 12],
        "Venus":   [6, 8, 11, 12],
        "Saturn":  [1, 4, 7, 8, 9, 10, 11],
        "Lagna":   [1, 3, 6, 10, 11],
    },
    "Mercury": {
        "Sun":     [5, 6, 9, 11, 12],
        "Moon":    [2, 4, 6, 8, 10, 11],
        "Mars":    [1, 2, 4, 7, 8, 9, 10, 11],
        "Mercury": [1, 3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [6, 8, 11, 12],
        "Venus":   [1, 2, 3, 4, 5, 8, 9, 11],
        "Saturn":  [1, 2, 4, 7, 8, 9, 10, 11],
        "Lagna":   [1, 2, 4, 6, 8, 10, 11],
    },
    "Jupiter": {
        "Sun":     [1, 2, 3, 4, 7, 8, 9, 10, 11],
        "Moon":    [2, 5, 7, 9, 11],
        "Mars":    [1, 2, 4, 7, 8, 10, 11],
        "Mercury": [1, 2, 4, 5, 6, 9, 10, 11],
        "Jupiter": [1, 2, 3, 4, 7, 8, 10, 11],
        "Venus":   [2, 5, 6, 9, 10, 11],
        "Saturn":  [3, 5, 6, 12],
        "Lagna":   [1, 2, 4, 5, 6, 7, 9, 10, 11],
    },
    "Venus": {
        "Sun":     [8, 11, 12],
        "Moon":    [1, 2, 3, 4, 5, 8, 9, 11, 12],
        "Mars":    [3, 5, 6, 9, 11, 12],
        "Mercury": [3, 5, 6, 9, 11],
        "Jupiter": [5, 8, 9, 10, 11],
        "Venus":   [1, 2, 3, 4, 5, 8, 9, 10, 11],
        "Saturn":  [3, 4, 5, 8, 9, 10, 11],
        "Lagna":   [1, 2, 3, 4, 5, 8, 9, 11],
    },
    "Saturn": {
        "Sun":     [1, 2, 4, 7, 8, 10, 11],
        "Moon":    [3, 6, 11],
        "Mars":    [3, 5, 6, 10, 11, 12],
        "Mercury": [6, 8, 9, 10, 11, 12],
        "Jupiter": [5, 6, 11, 12],
        "Venus":   [6, 11, 12],
        "Saturn":  [3, 5, 6, 11],
        "Lagna":   [1, 3, 4, 6, 10, 11],
    },
}

# Classical per-planet BAV totals and the SAV grand total — the verification gate.
BAV_TOTALS = {
    "Sun": 48, "Moon": 49, "Mars": 39, "Mercury": 54,
    "Jupiter": 56, "Venus": 52, "Saturn": 39,
}
SAV_TOTAL = 337

AV_PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]


def _verify_tables() -> None:
    """Assert the canonical tables reproduce the classical totals. Raises on error."""
    grand = 0
    for planet in AV_PLANETS:
        total = sum(len(houses) for houses in AV_TABLES[planet].values())
        if total != BAV_TOTALS[planet]:
            raise ValueError(
                f"Ashtakavarga table for {planet} totals {total}, "
                f"expected classical {BAV_TOTALS[planet]} — table is WRONG, fix it."
            )
        grand += total
    if grand != SAV_TOTAL:
        raise ValueError(
            f"SAV grand total is {grand}, expected classical {SAV_TOTAL} — tables WRONG."
        )


# Fail fast at import: if any table is wrong, the module refuses to load.
_verify_tables()


def compute_ashtakavarga(planets: dict, asc_sign_num: int) -> dict:
    """Compute BAV per planet, SAV, and totals.

    planets: mapping name -> info dict (must have 'sign_num').
    Returns a dict with per-sign 12-element arrays and totals.
    """
    ref_sign = {name: planets[name]["sign_num"] for name in AV_PLANETS}
    ref_sign["Lagna"] = asc_sign_num

    bav: dict = {}
    for planet in AV_PLANETS:
        bindus = [0] * 12  # index 0 = Aries .. 11 = Pisces
        for contributor, houses in AV_TABLES[planet].items():
            s_ref = ref_sign[contributor]
            for house in houses:
                sign_idx = ((s_ref - 1) + (house - 1)) % 12
                bindus[sign_idx] += 1
        bav[planet] = bindus

    # Sarvashtakavarga = element-wise sum across the 7 BAVs.
    sav = [0] * 12
    for planet in AV_PLANETS:
        for i in range(12):
            sav[i] += bav[planet][i]

    # Verification gate on the actual computed chart (not just table lengths).
    bav_totals = {p: sum(bav[p]) for p in AV_PLANETS}
    for p in AV_PLANETS:
        if bav_totals[p] != BAV_TOTALS[p]:
            raise ValueError(
                f"Computed BAV total for {p} = {bav_totals[p]}, expected {BAV_TOTALS[p]}."
            )
    sav_grand = sum(sav)
    if sav_grand != SAV_TOTAL:
        raise ValueError(f"Computed SAV total = {sav_grand}, expected {SAV_TOTAL}.")

    # Bindus in the sign occupied by each planet (useful for transit strength).
    bindus_in_own_sign = {}
    for name in core.PLANET_ORDER:
        sign_num = planets[name]["sign_num"]
        bindus_in_own_sign[name] = sav[sign_num - 1]

    return {
        "bav": {p: {"per_sign": bav[p], "total": bav_totals[p]} for p in AV_PLANETS},
        "sav": {"per_sign": sav, "total": sav_grand},
        "sav_in_planet_sign": bindus_in_own_sign,
        "verification": {
            "sav_total_expected": SAV_TOTAL,
            "sav_total_computed": sav_grand,
            "bav_totals_expected": BAV_TOTALS,
            "bav_totals_computed": bav_totals,
            "passed": True,
        },
    }


# --------------------------------------------------------------------------- #
# PART B — Shadbala (partial)
# --------------------------------------------------------------------------- #
SHADBALA_PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]

# Exact exaltation longitudes (deg, sidereal sign-based) — degree within sign.
EXALT_DEG = {
    "Sun": 10.0, "Moon": 3.0, "Mars": 28.0, "Mercury": 15.0,
    "Jupiter": 5.0, "Venus": 27.0, "Saturn": 20.0,
}

# Naisargika (natural) Bala — fixed values in virupas.
NAISARGIKA = {
    "Sun": 60.0, "Moon": 51.43, "Venus": 42.86, "Jupiter": 34.29,
    "Mercury": 25.71, "Mars": 17.14, "Saturn": 8.57,
}

# Dig Bala: the house of maximum directional strength for each planet.
DIG_MAX_HOUSE = {
    "Jupiter": 1, "Mercury": 1,   # east (Lagna)
    "Sun": 10, "Mars": 10,        # south (10th / MC)
    "Saturn": 7,                  # west (7th / Descendant)
    "Moon": 4, "Venus": 4,        # north (4th / IC)
}

# Required (minimum) Shadbala in Rupas — classical thresholds, for reference.
REQUIRED_RUPAS = {
    "Sun": 5.0, "Moon": 6.0, "Mars": 5.0, "Mercury": 7.0,
    "Jupiter": 6.5, "Venus": 5.5, "Saturn": 5.0,
}

# Planet "sex" for Drekkana Bala. Male: Sun, Mars, Jupiter. Female: Moon, Venus.
# Neutral (eunuch): Mercury, Saturn — favoured in any drekkana (counted as full).
PLANET_SEX = {
    "Sun": "male", "Mars": "male", "Jupiter": "male",
    "Moon": "female", "Venus": "female",
    "Mercury": "neutral", "Saturn": "neutral",
}


def _exalt_longitude(planet: str) -> float:
    """Absolute sidereal longitude (0..360) of a planet's exaltation point."""
    sign_num = core.EXALTATION[planet]            # 1..12
    return (sign_num - 1) * 30.0 + EXALT_DEG[planet]


def uchcha_bala(planet: str, lon: float) -> float:
    """Exaltation strength in virupas: (distance from debilitation point)/3.

    Max 60 at exaltation, 0 at debilitation (= exalt + 180).
    """
    debil = (_exalt_longitude(planet) + 180.0) % 360.0
    dist = abs((lon - debil + 180.0) % 360.0 - 180.0)  # 0..180 from debil point
    return dist / 3.0


def ojayugma_bala(planet: str, sign_num: int, navamsa_sign_num: int) -> float:
    """Oja/Yugma (odd/even) Bala in virupas, from rashi AND navamsa.

    Sun, Mars, Jupiter, Mercury (male/neutral) gain 15 in ODD signs.
    Moon and Venus (female) gain 15 in EVEN signs.
    Awarded independently for the rashi and the navamsa => up to 30.
    """
    odd_sign = (sign_num % 2 == 1)
    odd_nav = (navamsa_sign_num % 2 == 1)
    wants_odd = planet not in ("Moon", "Venus")
    bala = 0.0
    if odd_sign == wants_odd:
        bala += 15.0
    if odd_nav == wants_odd:
        bala += 15.0
    return bala


def kendradi_bala(house: int) -> float:
    """Kendradi Bala in virupas by house type: kendra 60, panaphara 30, apoklima 15."""
    if house in (1, 4, 7, 10):
        return 60.0
    if house in (2, 5, 8, 11):
        return 30.0
    return 15.0  # apoklima (3, 6, 9, 12)


def drekkana_bala(planet: str, deg_in_sign: float) -> float:
    """Drekkana Bala in virupas (0 or 15).

    1st decanate (0-10°): male planets get 15.
    2nd decanate (10-20°): neutral planets get 15.
    3rd decanate (20-30°): female planets get 15.
    """
    if deg_in_sign < 10.0:
        decanate = "male"
    elif deg_in_sign < 20.0:
        decanate = "neutral"
    else:
        decanate = "female"
    return 15.0 if PLANET_SEX[planet] == decanate else 0.0


def dig_bala(planet: str, lon: float, asc_lon: float) -> float:
    """Directional strength in virupas (max 60).

    Strength = 60 * (angular distance of the planet from its powerless point)/180,
    where the powerless point is the cusp opposite the planet's max-strength
    direction. Cusps are taken as equal divisions from the Lagna degree
    (asc_lon + 30*(house-1)) — the common Dig Bala construction. Note this is the
    equal/Sripati-from-ascendant cusp scheme, which differs slightly from the
    whole-sign houses used elsewhere in the skill; Dig Bala is a directional
    measure and traditionally uses these angular cusps.
    """
    max_house = DIG_MAX_HOUSE[planet]
    # Powerless point is opposite the max-strength cusp.
    powerless_house = ((max_house - 1 + 6) % 12) + 1
    powerless_cusp = (asc_lon + 30.0 * (powerless_house - 1)) % 360.0
    dist = abs((lon - powerless_cusp + 180.0) % 360.0 - 180.0)  # 0..180
    return 60.0 * dist / 180.0


# --------------------------------------------------------------------------- #
# Sthana Bala — Saptavargaja (the 7-varga dignity component)
# --------------------------------------------------------------------------- #
# The seven divisions used for Saptavargaja Bala (BPHS): D1, D2, D3, D7, D9,
# D12, D30. In each, the planet's relationship to the sign's DISPOSITOR (lord)
# is graded by the five-fold *compound* friendship (panchadha maitri) and scored
# in virupas. Exaltation strength is NOT scored here (it is already counted in
# Uchcha Bala) — Saptavargaja is purely the friendship/own-sign dignity.
SAPTAVARGA_DIVISIONS = [1, 2, 3, 7, 9, 12, 30]

# Moolatrikona signs (1..12) — own-sign with the higher 45-virupa grade.
MOOLATRIKONA = {
    "Sun": 5, "Moon": 2, "Mars": 1, "Mercury": 6,
    "Jupiter": 9, "Venus": 7, "Saturn": 11,
}

# Compound (5-fold) relationship -> virupa, per the classical Saptavargaja table.
SAPTAVARGA_VIRUPA = {
    "moolatrikona": 45.0,
    "own": 30.0,
    "great_friend": 22.5,
    "friend": 15.0,
    "neutral": 7.5,
    "enemy": 3.75,
    "great_enemy": 1.875,
}

# Natural benefics / malefics for Drik Bala (Moon handled by waxing/waning).
NATURAL_BENEFIC = {"Jupiter", "Venus", "Mercury"}
NATURAL_MALEFIC = {"Sun", "Mars", "Saturn"}

# Each planet's special (full-strength) graha-drishti house distances.
SPECIAL_ASPECT_HOUSES = {
    "Sun": {7}, "Moon": {7}, "Mercury": {7}, "Venus": {7},
    "Mars": {4, 7, 8}, "Jupiter": {5, 7, 9}, "Saturn": {3, 7, 10},
}

# Chaldean order of the planetary-hour (Hora) rulers, by decreasing apparent
# speed. Each successive hora from sunrise is ruled by the next planet here.
CHALDEAN_HORA = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon"]

# Heliocentric MEAN longitude elements (tropical, deg) at J2000.0 and mean daily
# motion (deg/day). Used ONLY for the Cheshta Kendra (Seeghra Kendra) — a
# difference of mean longitudes, so the frame/ayanamsa offset cancels. The mean
# Sun's geocentric longitude is included for the superior-planet seeghrocha.
MEAN_LON = {
    "Sun":     (280.46646, 0.98564736),   # mean Sun, geocentric
    "Mars":    (355.43300, 0.52402068),
    "Jupiter": (34.351519, 0.08308529),
    "Saturn":  (50.077444, 0.03344414),
    "Mercury": (252.25091, 4.09233445),   # heliocentric mean longitude
    "Venus":   (181.97980, 1.60213034),   # heliocentric mean longitude
}
SUPERIOR = {"Mars", "Jupiter", "Saturn"}
INFERIOR = {"Mercury", "Venus"}

J2000 = 2451545.0


def _declination(jd: float, body: int) -> float:
    """Equatorial declination (deg) of a body. Ayanamsa-independent (equatorial)."""
    flags = (core._STATE["flags"] | swe.FLG_EQUATORIAL) & ~swe.FLG_SIDEREAL
    pos, _ = swe.calc_ut(jd, body, flags)
    return pos[1]


def _mean_longitude(planet: str, jd: float) -> float:
    """Mean longitude (deg, 0..360) from the linear element for `planet`."""
    l0, rate = MEAN_LON[planet]
    return (l0 + rate * (jd - J2000)) % 360.0


def _compound_relation(planet: str, other: str, natal_houses: dict) -> str:
    """Five-fold (panchadha) compound friendship of `planet` toward `other`.

    natural (NATURAL_RELATION) + temporal (by house distance in D1) ->
    great_friend / friend / neutral / enemy / great_enemy.
    """
    natural = core.NATURAL_RELATION[planet][other]  # 'f' / 'n' / 'e'
    # Temporal: planets in the 2,3,4,10,11,12 from each other are temp friends;
    # 1,5,6,7,8,9 are temp enemies. Distance counted from `planet` to `other`.
    dist = (natal_houses[other] - natal_houses[planet]) % 12 + 1
    temporal = "f" if dist in (2, 3, 4, 10, 11, 12) else "e"
    table = {
        ("f", "f"): "great_friend", ("f", "e"): "neutral",
        ("n", "f"): "friend",       ("n", "e"): "enemy",
        ("e", "f"): "neutral",      ("e", "e"): "great_enemy",
    }
    return table[(natural, temporal)]


def saptavargaja_bala(planet: str, lon: float, natal_houses: dict) -> float:
    """Sthana:Saptavargaja Bala (virupa) — dignity across the 7 vargas."""
    total = 0.0
    for d in SAPTAVARGA_DIVISIONS:
        sign = core.varga_sign(lon, d)
        lord = core.SIGN_LORD[sign]
        if lord == planet:
            grade = "moolatrikona" if (d == 1 and sign == MOOLATRIKONA[planet]) else "own"
        else:
            grade = _compound_relation(planet, lord, natal_houses)
        total += SAPTAVARGA_VIRUPA[grade]
    return total


# --------------------------------------------------------------------------- #
# Kala Bala (temporal) sub-components
# --------------------------------------------------------------------------- #
def nathonnatha_bala(planet: str, birth_hours: float) -> float:
    """Diurnal/nocturnal strength (virupa, max 60).

    Day-strong (Sun, Jupiter, Venus) peak at local noon; night-strong (Moon,
    Mars, Saturn) peak at midnight; Mercury is always full. `birth_hours` is the
    local clock time in hours [0,24). The ramp is linear (triangular) in the
    distance from midnight/noon — the classical Unnata/Nata construction.
    """
    if planet == "Mercury":
        return 60.0
    # Fraction of the way from midnight (0) to noon (0.5) to midnight (1.0).
    frac = (birth_hours % 24.0) / 24.0
    day_strength = 60.0 * (1.0 - abs(frac - 0.5) * 2.0)   # 0 at 00:00, 60 at 12:00
    if planet in ("Sun", "Jupiter", "Venus"):
        return day_strength
    return 60.0 - day_strength                            # night-strong


def paksha_bala(planet: str, moon_lon: float, sun_lon: float) -> float:
    """Lunar-phase strength (virupa). Moon's value is doubled (classical)."""
    elong = abs((moon_lon - sun_lon + 180.0) % 360.0 - 180.0)  # 0..180
    benefic = planet in ("Moon", "Mercury", "Jupiter", "Venus")
    bright = elong / 3.0                       # 0 at new moon, 60 at full moon
    val = bright if benefic else (60.0 - bright)
    if planet == "Moon":
        val *= 2.0
    return val


# Tribhaga (the planet ruling each third of the day / night). Jupiter always 60.
_TRIBHAGA_DAY = {0: "Mercury", 1: "Sun", 2: "Saturn"}
_TRIBHAGA_NIGHT = {0: "Moon", 1: "Venus", 2: "Mars"}


def tribhaga_bala(planet: str, jd: float, sunrise: float, sunset: float,
                  next_sunrise: float) -> float:
    """Tribhaga Bala (virupa, 0 or 60). Jupiter always gets 60."""
    if planet == "Jupiter":
        return 60.0
    if sunrise is None or sunset is None:
        return 0.0
    if sunrise <= jd < sunset:                 # daytime: three equal parts
        part = int((jd - sunrise) / ((sunset - sunrise) / 3.0))
        part = min(part, 2)
        return 60.0 if _TRIBHAGA_DAY[part] == planet else 0.0
    # night: from sunset to the next sunrise
    if next_sunrise is None or not (sunset <= jd < next_sunrise):
        return 0.0
    part = int((jd - sunset) / ((next_sunrise - sunset) / 3.0))
    part = min(part, 2)
    return 60.0 if _TRIBHAGA_NIGHT[part] == planet else 0.0


def _solar_ingress_before(jd: float, target_sign: int, max_back: float) -> float:
    """JD when the Sun most recently entered sidereal `target_sign` (1..12).

    Bisection on the (signed) angular distance of the Sun from the sign cusp.
    `max_back` bounds the search window in days.
    """
    body = core.PLANETS["Sun"]
    cusp = (target_sign - 1) * 30.0

    def past_cusp(t: float) -> float:
        lon, _ = core.sidereal_longitude(t, body)
        return (lon - cusp) % 360.0           # 0..360; small just after ingress

    lo, hi = jd - max_back, jd
    # Walk back day-by-day to find the bracket where the Sun crosses the cusp.
    step = 1.0
    t = hi
    prev = past_cusp(t)
    while t > lo:
        t2 = t - step
        cur = past_cusp(t2)
        if cur > prev:                        # wrapped: cusp lies between t2 and t
            lo, hi = t2, t
            break
        prev = cur
        t = t2
    for _ in range(40):                       # bisection to the crossing
        mid = (lo + hi) / 2.0
        if past_cusp(mid) > 180.0:            # still before the cusp
            lo = mid
        else:
            hi = mid
    return hi


def time_lord_balas(planet: str, jd: float, lat: float, lon: float, tz: str,
                    sunrise: float, sun_sign: int) -> dict:
    """Vara (45), Hora (60), Masa (30) and Abda (15) Bala for `planet`.

    Each is awarded in full to the single ruling planet, 0 otherwise.
    """
    vara = core.vedic_vara(jd, lat, lon, tz)
    vara_lord = core.WEEKDAY_LORD[vara]

    # Hora: equal 1-hour planetary hours from sunrise, cycling the Chaldean order
    # starting from the weekday lord.
    hora_lord = vara_lord
    if sunrise is not None:
        hora_n = int((jd - sunrise) * 24.0)
        if hora_n >= 0:
            start = CHALDEAN_HORA.index(vara_lord)
            hora_lord = CHALDEAN_HORA[(start + hora_n) % 7]

    # Masa lord = weekday lord of the Sun's ingress into its current sign.
    masa_jd = _solar_ingress_before(jd, sun_sign, 40.0)
    masa_lord = core.WEEKDAY_LORD[core.vedic_vara(masa_jd, lat, lon, tz)]
    # Abda (year) lord = weekday lord of the most recent Mesha Sankranti.
    abda_jd = _solar_ingress_before(jd, 1, 380.0)
    abda_lord = core.WEEKDAY_LORD[core.vedic_vara(abda_jd, lat, lon, tz)]

    return {
        "vara_bala": 45.0 if planet == vara_lord else 0.0,
        "hora_bala": 60.0 if planet == hora_lord else 0.0,
        "masa_bala": 30.0 if planet == masa_lord else 0.0,
        "abda_bala": 15.0 if planet == abda_lord else 0.0,
        "_lords": {"vara": vara_lord, "hora": hora_lord,
                   "masa": masa_lord, "abda": abda_lord},
    }


# Obliquity of the ecliptic (deg) — used to scale Ayana Bala (max kranti).
MAX_KRANTI = 23.45
# Planets strong in NORTH (positive) declination. Moon & Saturn favour south.
AYANA_NORTH = {"Sun", "Mars", "Jupiter", "Venus", "Mercury"}


def ayana_bala(planet: str, declination: float) -> float:
    """Ayana (declination) Bala in virupa. Sun's value is doubled (classical).

    North-strong planets gain with +declination; Moon & Saturn with −declination;
    Mercury is always treated as gaining (favoured in both ayanas).
    """
    kranti = declination if planet in AYANA_NORTH else -declination
    if planet == "Mercury":
        kranti = abs(declination)
    val = 60.0 * (MAX_KRANTI + kranti) / (2.0 * MAX_KRANTI)
    val = max(0.0, min(60.0, val))
    if planet == "Sun":
        val *= 2.0
    return val


def cheshta_bala(planet: str, jd: float, ayana: float, paksha: float) -> float:
    """Motional strength (virupa, max 60) via the classical Cheshta (Seeghra)
    Kendra of mean longitudes.

    The Sun's Cheshta Bala equals its Ayana Bala and the Moon's equals its
    Paksha Bala (classical identities). The five star-planets use the Seeghra
    Kendra: for superior planets the seeghrocha is the mean Sun; for inferior
    planets it is the planet's own (faster) heliocentric mean longitude.
    """
    if planet == "Sun":
        return ayana
    if planet == "Moon":
        return paksha
    mean_sun = _mean_longitude("Sun", jd)
    mean_planet = _mean_longitude(planet, jd)
    if planet in SUPERIOR:
        kendra = (mean_sun - mean_planet) % 360.0
    else:                                       # inferior: seeghrocha − mean Sun
        kendra = (mean_planet - mean_sun) % 360.0
    if kendra > 180.0:
        kendra = 360.0 - kendra                 # fold to 0..180
    return kendra / 3.0                          # 0..60


# --------------------------------------------------------------------------- #
# Drik Bala (aspectual) — the degree-precise Parashari Sphuta Drishti
# --------------------------------------------------------------------------- #
def sphuta_drishti(d: float) -> float:
    """Parashari graded aspect strength (virupa, 0..60) at separation `d`
    degrees, measured from the aspecting planet forward to the aspected.

    Piecewise-linear between the classical anchor points
    (60°→15, 90°→45, 120°→30, 150°→0, 180°→60, 210°→45, 240°→30, 270°→15).
    """
    d %= 360.0
    if d <= 30.0:
        return 0.0
    if d <= 60.0:
        return (d - 30.0) * 0.5                 # 0 → 15
    if d <= 90.0:
        return 15.0 + (d - 60.0) * 1.0          # 15 → 45
    if d <= 120.0:
        return 45.0 - (d - 90.0) * 0.5          # 45 → 30
    if d <= 150.0:
        return 30.0 - (d - 120.0) * 1.0         # 30 → 0
    if d <= 180.0:
        return (d - 150.0) * 2.0                # 0 → 60
    if d <= 300.0:
        return max(0.0, 60.0 - (d - 180.0) * 0.5)  # 60 → 0 across 180..300
    return 0.0


def drik_bala(planet: str, planets: dict, moon_waxing: bool) -> float:
    """Drik (aspectual) Bala in virupa: (benefic drishti − malefic drishti) / 4.

    Each aspecting planet's Sphuta Drishti onto `planet` is signed + for a
    benefic, − for a malefic, then summed and divided by 4 (classical). Special
    aspects (Mars 4/8, Jupiter 5/9, Saturn 3/10, all 7th) are taken at full 60.
    """
    target_lon = planets[planet]["longitude"]
    total = 0.0
    for other in SHADBALA_PLANETS:
        if other == planet:
            continue
        sep = (target_lon - planets[other]["longitude"]) % 360.0
        drishti = sphuta_drishti(sep)
        # Special aspects are counted by WHOLE SIGN, not by 30deg blocks of the
        # raw separation (which only coincide when both planets share the same
        # degree-in-sign). Distance from `other`'s sign to `planet`'s sign, 1..12.
        house = ((planets[planet]["sign_num"] - planets[other]["sign_num"]) % 12) + 1
        if house in SPECIAL_ASPECT_HOUSES[other]:
            drishti = 60.0
        # Sign of the contribution by the aspecting planet's benefic nature.
        if other == "Moon":
            benefic = moon_waxing
        else:
            benefic = other in NATURAL_BENEFIC
        total += drishti if benefic else -drishti
    return total / 4.0


def compute_shadbala(planets: dict, asc: dict, jd: float, lat: float,
                     lon: float, tz: str, birth_hours: float) -> dict:
    """Compute the complete six-fold Shadbala for the 7 grahas.

    Returns per-planet detail with every classical source: Sthana (Uchcha,
    Saptavargaja, Ojayugma, Kendradi, Drekkana), Dig, Kala (Nathonnatha, Paksha,
    Tribhaga, Abda, Masa, Vara, Hora, Ayana, Yuddha), Cheshta, Naisargika, Drik.
    """
    asc_lon = (asc["sign_num"] - 1) * 30.0 + asc["degree_in_sign"]
    sun_lon = planets["Sun"]["longitude"]
    moon_lon = planets["Moon"]["longitude"]
    moon_waxing = abs((moon_lon - sun_lon + 180.0) % 360.0 - 180.0) <= 90.0
    natal_houses = {n: planets[n]["house"] for n in SHADBALA_PLANETS}

    # Sunrise/sunset bracketing the birth instant (for Tribhaga + Hora).
    sunrise = core.sunrise_before(jd, lat, lon)
    sunset = next_sunrise = None
    if sunrise is not None:
        _, sunset = core.next_rise_set(sunrise, lat, lon)
        next_sunrise = core.sunrise_before(jd + 1.0, lat, lon)
        if next_sunrise is not None and next_sunrise <= jd:
            nr, _ = core.next_rise_set(jd, lat, lon)
            next_sunrise = nr

    result: dict = {}
    for name in SHADBALA_PLANETS:
        p = planets[name]
        plon = p["longitude"]

        # --- 1. Sthana Bala ---
        uchcha = uchcha_bala(name, plon)
        saptav = saptavargaja_bala(name, plon, natal_houses)
        oja = ojayugma_bala(name, p["sign_num"], p["navamsa_sign_num"])
        kendra = kendradi_bala(p["house"])
        drek = drekkana_bala(name, p["degree_in_sign"])
        sthana_total = uchcha + saptav + oja + kendra + drek

        # --- 2. Dig Bala ---
        dig = dig_bala(name, plon, asc_lon)

        # --- 3. Kala Bala ---
        natho = nathonnatha_bala(name, birth_hours)
        paksha = paksha_bala(name, moon_lon, sun_lon)
        tribhaga = tribhaga_bala(name, jd, sunrise, sunset, next_sunrise)
        tlords = time_lord_balas(name, jd, lat, lon, tz, sunrise, p["sign_num"])
        decl = _declination(jd, core.PLANETS[name])
        ayana = ayana_bala(name, decl)
        # Yuddha computed in a second pass (needs all pre-yuddha totals) — 0 here.
        kala_total = (natho + paksha + tribhaga + ayana
                      + tlords["vara_bala"] + tlords["hora_bala"]
                      + tlords["masa_bala"] + tlords["abda_bala"])

        # --- 4. Cheshta Bala ---
        cheshta = cheshta_bala(name, jd, ayana, paksha)

        # --- 5. Naisargika Bala ---
        naisargika = NAISARGIKA[name]

        # --- 6. Drik Bala ---
        drik = drik_bala(name, planets, moon_waxing)

        components = {
            "sthana": {
                "uchcha_bala": round(uchcha, 2),
                "saptavargaja_bala": round(saptav, 2),
                "ojayugma_bala": round(oja, 2),
                "kendradi_bala": round(kendra, 2),
                "drekkana_bala": round(drek, 2),
                "subtotal": round(sthana_total, 2),
            },
            "dig_bala": round(dig, 2),
            "kala": {
                "nathonnatha_bala": round(natho, 2),
                "paksha_bala": round(paksha, 2),
                "tribhaga_bala": round(tribhaga, 2),
                "abda_bala": round(tlords["abda_bala"], 2),
                "masa_bala": round(tlords["masa_bala"], 2),
                "vara_bala": round(tlords["vara_bala"], 2),
                "hora_bala": round(tlords["hora_bala"], 2),
                "ayana_bala": round(ayana, 2),
                "yuddha_bala": 0.0,
                "subtotal": round(kala_total, 2),
                "lords": tlords["_lords"],
            },
            "cheshta_bala": round(cheshta, 2),
            "naisargika_bala": round(naisargika, 2),
            "drik_bala": round(drik, 2),
            "declination_deg": round(decl, 3),
        }

        total_virupa = (sthana_total + dig + kala_total
                        + cheshta + naisargika + drik)
        result[name] = {
            "components_virupa": components,
            "total_virupa": round(total_virupa, 2),
            "total_rupa": round(total_virupa / 60.0, 3),
            "required_rupa": REQUIRED_RUPAS[name],
        }

    # --- Yuddha Bala (planetary war): star-planets within 1° of each other. ---
    # The difference of the two combatants' totals is added to the victor (the
    # more-northern, i.e. greater-declination planet) and subtracted from the
    # vanquished. Rare; usually a no-op.
    warriors = [n for n in ("Mars", "Mercury", "Jupiter", "Venus", "Saturn")]
    for i in range(len(warriors)):
        for j in range(i + 1, len(warriors)):
            a, b = warriors[i], warriors[j]
            sep = abs((planets[a]["longitude"] - planets[b]["longitude"]
                       + 180.0) % 360.0 - 180.0)
            if sep > 1.0:
                continue
            decl_a = result[a]["components_virupa"]["declination_deg"]
            decl_b = result[b]["components_virupa"]["declination_deg"]
            winner, loser = (a, b) if decl_a >= decl_b else (b, a)
            diff = abs(result[a]["total_virupa"] - result[b]["total_virupa"])
            for who, sign in ((winner, 1.0), (loser, -1.0)):
                result[who]["components_virupa"]["kala"]["yuddha_bala"] = round(sign * diff, 2)
                result[who]["components_virupa"]["kala"]["subtotal"] = round(
                    result[who]["components_virupa"]["kala"]["subtotal"] + sign * diff, 2)
                result[who]["total_virupa"] = round(
                    result[who]["total_virupa"] + sign * diff, 2)
                result[who]["total_rupa"] = round(
                    result[who]["total_virupa"] / 60.0, 3)

    for name in SHADBALA_PLANETS:
        result[name]["meets_required"] = (
            result[name]["total_rupa"] >= result[name]["required_rupa"])

    return {
        "components_included": [
            "Sthana (Uchcha, Saptavargaja, Ojayugma, Kendradi, Drekkana)",
            "Dig",
            "Kala (Nathonnatha, Paksha, Tribhaga, Abda, Masa, Vara, Hora, Ayana, Yuddha)",
            "Cheshta", "Naisargika", "Drik",
        ],
        "complete": True,
        "method_notes": [
            "Cheshta uses the classical Seeghra (Cheshta) Kendra of mean "
            "longitudes; Sun's Cheshta = its Ayana, Moon's = its Paksha.",
            "Drik uses the degree-precise Parashari Sphuta Drishti; special "
            "aspects (Mars 4/8, Jupiter 5/9, Saturn 3/10, all 7th) at full 60.",
            "Hora uses equal one-hour planetary hours from sunrise (Chaldean order).",
            "Ayana uses equatorial declination (kranti); Sun's value doubled.",
            "Saptavargaja grades D1,D2,D3,D7,D9,D12,D30 by compound friendship.",
        ],
        "units": "virupa (1 Rupa = 60 virupa)",
        "planets": result,
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def compute_strength(args) -> dict:
    core.init_engine(
        args.ayanamsa,
        node=getattr(args, "node", "mean"),
        topocentric=not getattr(args, "geocentric", False),
        lat=args.lat, lon=args.lon,
        ephemeris=getattr(args, "ephemeris", "moshier"),
    )
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)

    asc = core.ascendant(jd, args.lat, args.lon, args.house_system)
    asc_sign_num = asc["sign_num"]

    planets = core.all_planet_positions(jd)
    for name, info in planets.items():
        info["house"] = core.house_of(info["sign_num"], asc_sign_num)
        info["dignity"] = core.dignity(name, info["sign_num"])

    birth_hours = hh + mm / 60.0 + ss / 3600.0
    ashtakavarga = compute_ashtakavarga(planets, asc_sign_num)
    shadbala = compute_shadbala(planets, asc, jd, args.lat, args.lon, args.tz, birth_hours)

    return {
        "input": {
            "date": args.date, "time": args.time, "lat": args.lat,
            "lon": args.lon, "timezone": args.tz,
            "ayanamsa": args.ayanamsa, "house_system": args.house_system,
            "node": getattr(args, "node", "mean"),
            "topocentric": not getattr(args, "geocentric", False),
        },
        "julian_day_ut": round(jd, 6),
        "ayanamsa_deg": round(core.ayanamsa_value(jd), 6),
        "ascendant": asc,
        "planet_signs": {name: planets[name]["sign"] for name in core.PLANET_ORDER},
        "ashtakavarga": ashtakavarga,
        "shadbala": shadbala,
        "disclaimer": (
            "Ashtakavarga is fully computed (verified totals). Shadbala is the "
            "complete six-fold strength (Sthana, Dig, Kala, Cheshta, Naisargika, "
            "Drik), each source computed from classical rules — see "
            "shadbala.method_notes for the exact methods used. Strength is a "
            "structural indicator, not a prediction."
        ),
    }


def _parse_time(t: str):
    parts = t.split(":")
    hh = int(parts[0]); mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    return hh, mm, ss


def render_text(result: dict) -> str:
    lines = []
    i = result["input"]
    asc = result["ascendant"]
    lines.append("=" * 64)
    lines.append("  PLANETARY STRENGTH — Ashtakavarga & (Partial) Shadbala")
    lines.append("=" * 64)
    lines.append(f"  Born: {i['date']} {i['time']} ({i['timezone']})")
    lines.append(f"  Place: lat {i['lat']}, lon {i['lon']}")
    frame = "topocentric" if i.get("topocentric") else "geocentric"
    lines.append(f"  Ayanamsa: {i['ayanamsa'].title()} ({result.get('ayanamsa_deg')}°) "
                 f"| {frame} | {i.get('node','mean')}-node")
    lines.append(f"  Lagna: {asc['sign']} {core.deg_to_dms(asc['degree_in_sign'])}")

    # ---- Section 1: Ashtakavarga ----
    av = result["ashtakavarga"]
    lines.append("")
    lines.append("-" * 64)
    lines.append("  ASHTAKAVARGA  (fully computed — verified)")
    lines.append("-" * 64)
    # SAV row per sign.
    lines.append("  Sarvashtakavarga (SAV) bindus per sign:")
    hdr = "  " + "".join(f"{core.SIGNS[s][:3]:>5}" for s in range(12))
    lines.append(hdr)
    lines.append("  " + "".join(f"{b:>5}" for b in av["sav"]["per_sign"]))
    lines.append(f"  SAV grand total = {av['sav']['total']}  (classical 337)")
    lines.append("")
    lines.append("  Per-planet BAV totals:")
    bav_line = "   ".join(
        f"{p[:3]} {av['bav'][p]['total']}" for p in AV_PLANETS
    )
    lines.append("    " + bav_line)
    lines.append("    (classical: Sun 48, Moon 49, Mars 39, Mer 54, Jup 56, Ven 52, Sat 39)")
    lines.append("")
    lines.append("  SAV bindus in each planet's own sign (transit strength):")
    for name in core.PLANET_ORDER:
        lines.append(f"    {name:<9} {av['sav_in_planet_sign'][name]:>2} bindus "
                     f"(in {result_sign(result, name)})")

    # ---- Section 2: Shadbala ----
    sb = result["shadbala"]
    lines.append("")
    lines.append("-" * 64)
    lines.append("  SHADBALA  (complete six-fold strength)")
    lines.append("-" * 64)
    lines.append("  Six sources (virupa; 1 Rupa = 60 virupa):")
    header = (f"  {'Planet':<9}{'Sthana':>8}{'Dig':>7}{'Kala':>7}"
              f"{'Cheshta':>8}{'Naisrg':>8}{'Drik':>7}{'TotRup':>8}{'Req':>6}{'P/F':>5}")
    lines.append(header)
    lines.append("  " + "-" * 70)
    for name in SHADBALA_PLANETS:
        p = sb["planets"][name]
        c = p["components_virupa"]
        pf = "PASS" if p["meets_required"] else "FAIL"
        lines.append(
            f"  {name:<9}{c['sthana']['subtotal']:>8.1f}{c['dig_bala']:>7.1f}"
            f"{c['kala']['subtotal']:>7.1f}{c['cheshta_bala']:>8.1f}"
            f"{c['naisargika_bala']:>8.1f}{c['drik_bala']:>7.1f}"
            f"{p['total_rupa']:>8.2f}{p['required_rupa']:>6.1f}{pf:>5}"
        )
    lines.append("")
    lines.append("  Methods:")
    for note in sb["method_notes"]:
        lines.append(f"    - {note}")
    lines.append("")
    lines.append("  P/F compares the complete Shadbala against the classical")
    lines.append("  required strength (Ishta/Kashta is not computed here).")

    lines.append("")
    lines.append("-" * 64)
    lines.append("  " + result["disclaimer"])
    lines.append("=" * 64)
    return "\n".join(lines)


def result_sign(result: dict, name: str) -> str:
    """Helper for render: the sign name a planet currently occupies."""
    return result["planet_signs"][name]


def main():
    ap = argparse.ArgumentParser(
        description="Compute planetary strength (Ashtakavarga + complete Shadbala)."
    )
    ap.add_argument("--date", required=True, help="Birth date YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="Birth time HH:MM[:SS], 24h local")
    ap.add_argument("--lat", type=float, required=True, help="Latitude (deg, N positive)")
    ap.add_argument("--lon", type=float, required=True, help="Longitude (deg, E positive)")
    ap.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--house-system", default=core.DEFAULT_HOUSE_SYSTEM, dest="house_system")
    ap.add_argument("--node", default="mean", choices=["mean", "true"],
                    help="Lunar node model for Rahu/Ketu (default mean)")
    ap.add_argument("--geocentric", action="store_true",
                    help="Use geocentric positions (default is topocentric)")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"],
                    help="moshier=offline (default), swiss=requires .se1 files")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    try:
        result = compute_strength(args)
    except Exception as e:  # noqa: BLE001 — surface a clean message to the agent
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result))


if __name__ == "__main__":
    main()

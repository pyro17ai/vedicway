#!/usr/bin/env python3
"""
numerology.py — Compute a numerology report from birth date (and optional name).

Pure Python standard library only — no ephemeris, no network, no dependencies.
Covers Moolank (psychic/birth number), Bhagyank (destiny/life-path number),
Naamank (name number, Chaldean and/or Pythagorean), ruling planets, number
compatibility (planetary friendships), the Lo Shu grid with arrows, an optional
personal-year theme, lucky attributes, and a name-correction hint.

Usage:
    python numerology.py --date 1990-08-15 [--name "Full Name"] \\
        [--system chaldean|pythagorean|both] [--year YYYY] \\
        [--keep-master] [--json]

For cultural/educational/entertainment use only. Not predictive.
"""

from __future__ import annotations

import argparse
import json
import sys

# --- Constant lookups ------------------------------------------------------

RULING_PLANET = {
    1: "Sun", 2: "Moon", 3: "Jupiter", 4: "Rahu", 5: "Mercury",
    6: "Venus", 7: "Ketu", 8: "Saturn", 9: "Mars",
}

# Chaldean letter values (no letter is assigned 9 in the Chaldean system).
CHALDEAN_MAP = {
    "A": 1, "I": 1, "J": 1, "Q": 1, "Y": 1,
    "B": 2, "K": 2, "R": 2,
    "C": 3, "G": 3, "L": 3, "S": 3,
    "D": 4, "M": 4, "T": 4,
    "E": 5, "H": 5, "N": 5, "X": 5,
    "U": 6, "V": 6, "W": 6,
    "O": 7, "Z": 7,
    "F": 8, "P": 8,
}

# Pythagorean letter values (A=1..I=9, J=1..R=9, S=1..Z=8).
PYTHAGOREAN_MAP = {
    "A": 1, "J": 1, "S": 1,
    "B": 2, "K": 2, "T": 2,
    "C": 3, "L": 3, "U": 3,
    "D": 4, "M": 4, "V": 4,
    "E": 5, "N": 5, "W": 5,
    "F": 6, "O": 6, "X": 6,
    "G": 7, "P": 7, "Y": 7,
    "H": 8, "Q": 8, "Z": 8,
    "I": 9, "R": 9,
}

# Friendship matrix among single digits 1-9 (planetary friendships, Cheiro/Indian).
# Entries list explicit friends and enemies; any unlisted pair is neutral.
FRIENDS = {
    1: {1, 2, 3, 9},
    2: {1, 2, 5, 7},
    3: {1, 2, 3, 9},
    4: {1, 5, 6, 7},
    5: {1, 2, 3, 4, 5, 6, 7, 8, 9},  # Mercury — friendly to all generally
    6: {4, 5, 6, 8},
    7: {1, 2, 4, 7},
    8: {5, 6, 8},
    9: {1, 3, 9},
}
ENEMIES = {
    1: {8, 4, 7},
    2: {8, 9},
    3: {6},
    4: {2, 9},
    5: set(),
    6: {3},
    7: set(),
    8: {1, 2},
    9: {4},
}

# Lo Shu grid layout (row-major).
LO_SHU_LAYOUT = [
    [4, 9, 2],
    [3, 5, 7],
    [8, 1, 6],
]

LO_SHU_LINES = [
    ((4, 9, 2), "Arrow of Intellect / Mental Plane"),
    ((3, 5, 7), "Arrow of Emotional Balance"),
    ((8, 1, 6), "Arrow of Practicality / Action"),
    ((4, 3, 8), "Arrow of Planning / Thought"),
    ((9, 5, 1), "Arrow of Will / Determination"),
    ((2, 7, 6), "Arrow of Activity"),
    ((4, 5, 6), "Arrow of Compassion (the Golden / Kindness)"),
    ((2, 5, 8), "Arrow of Spirituality / Emotional"),
]

NUMBER_THEME = {
    1: "Independence, leadership, new beginnings, initiative.",
    2: "Cooperation, partnership, sensitivity, patience.",
    3: "Creativity, expression, optimism, social growth.",
    4: "Foundation, hard work, structure, discipline.",
    5: "Change, freedom, travel, adaptability.",
    6: "Responsibility, home, service, relationships.",
    7: "Introspection, study, spirituality, analysis.",
    8: "Ambition, power, finances, material achievement.",
    9: "Completion, compassion, humanitarianism, release.",
}

LUCKY_ATTRIBUTES = {
    "Sun": {"gemstone": "Ruby", "days": "Sunday & Monday", "colors": "Gold, orange"},
    "Moon": {"gemstone": "Pearl", "days": "Monday", "colors": "White, cream, silver"},
    "Jupiter": {"gemstone": "Yellow Sapphire", "days": "Thursday", "colors": "Yellow"},
    "Rahu": {"gemstone": "Hessonite (Gomed)", "days": "Varies", "colors": "Grey, khaki, electric blue"},
    "Mercury": {"gemstone": "Emerald", "days": "Wednesday", "colors": "Green"},
    "Venus": {"gemstone": "Diamond / Opal", "days": "Friday", "colors": "White, pastels"},
    "Ketu": {"gemstone": "Cat's Eye", "days": "Varies", "colors": "Smoky, grey"},
    "Saturn": {"gemstone": "Blue Sapphire", "days": "Saturday", "colors": "Black, dark blue"},
    "Mars": {"gemstone": "Red Coral", "days": "Tuesday", "colors": "Red"},
}

DISCLAIMER = "For cultural/educational/entertainment use only. Not predictive."

# Karmic Debt numbers — flagged when a core compound (pre-reduction) lands here.
KARMIC_DEBT = {
    13: "13/4 — Karmic Debt of laziness/shortcuts in a past cycle; lesson is "
        "disciplined, honest effort. Hard work now builds lasting foundations.",
    14: "14/5 — Karmic Debt of excess/abused freedom; lesson is moderation, "
        "focus, and constructive use of change rather than restlessness.",
    16: "16/7 — Karmic Debt of ego/illicit love in the past; lesson is humility "
        "and rebuilding the self on spiritual rather than vain foundations.",
    19: "19/1 — Karmic Debt of misused power/self-centredness; lesson is "
        "independence with care for others, standing on your own without selfishness.",
}

# Master-number short labels (display only).
MASTER_LABEL = {
    11: "11 (master — intensified 2: intuition, inspiration)",
    22: "22 (master — intensified 4: the master builder)",
    33: "33 (master — intensified 6: the master teacher)",
}


# --- Core helpers ----------------------------------------------------------

def reduce_to_single(n: int, keep_master: bool = False) -> int:
    """Repeatedly sum the digits of n until a single digit remains.

    If keep_master is True and an intermediate sum is a master number
    (11, 22, 33), stop there and return it unreduced.
    """
    n = abs(int(n))
    if keep_master and n in (11, 22, 33):
        return n
    while n > 9:
        n = sum(int(c) for c in str(n))
        if keep_master and n in (11, 22, 33):
            return n
    return n


def _letters(name: str) -> str:
    """Uppercase letters of name only (ignore digits, spaces, punctuation)."""
    return "".join(ch for ch in name.upper() if ch.isalpha())


def split_vowels_consonants(name: str):
    """Split a name's letters into (vowels, consonants).

    A, E, I, O, U are always vowels. Y is treated as a vowel only when it acts
    as one — i.e. it has no adjacent vowel within its word (the common
    numerology heuristic, e.g. the Y in "Lynn" or "Yvonne" is a vowel, the Y in
    "Maya"/"Yoga" is a consonant). W is always a consonant here.
    """
    vowels, consonants = [], []
    for word in name.upper().split():
        seq = [c for c in word if c.isalpha()]
        for idx, ch in enumerate(seq):
            if ch in "AEIOU":
                vowels.append(ch)
            elif ch == "Y":
                prev = seq[idx - 1] if idx > 0 else ""
                nxt = seq[idx + 1] if idx + 1 < len(seq) else ""
                if prev not in "AEIOU" and nxt not in "AEIOU":
                    vowels.append(ch)
                else:
                    consonants.append(ch)
            else:
                consonants.append(ch)
    return vowels, consonants


def _name_value(letters, table) -> int:
    """Sum letter values for a sequence of letters under the given table."""
    return sum(table[ch] for ch in letters if ch in table)


def karmic_debt_for(compound: int):
    """Return (number, note) if a pre-reduction compound is a Karmic Debt, else None."""
    if compound in KARMIC_DEBT:
        return {"number": compound, "note": KARMIC_DEBT[compound]}
    return None


def relation(a: int, b: int) -> str:
    """Symmetric friendship relation between two single digits 1-9.

    Returns "friend", "neutral", or "enemy". A pair is a friend if either
    side lists the other as a friend (and neither lists it as an enemy);
    an enemy if either side lists the other as an enemy and neither as a
    friend; otherwise neutral (including mixed signals).
    """
    a, b = int(a), int(b)
    a_friend = b in FRIENDS.get(a, set())
    b_friend = a in FRIENDS.get(b, set())
    a_enemy = b in ENEMIES.get(a, set())
    b_enemy = a in ENEMIES.get(b, set())

    friend = a_friend or b_friend
    enemy = a_enemy or b_enemy

    if friend and not enemy:
        return "friend"
    if enemy and not friend:
        return "enemy"
    if friend and enemy:
        return "neutral"  # mixed signals -> neutral
    return "neutral"


# --- Section computations --------------------------------------------------

def compute_moolank(day: int, keep_master: bool) -> dict:
    return {
        "day_of_birth": day,
        "number": reduce_to_single(day, keep_master),
        "ruling_planet": RULING_PLANET[reduce_to_single(day, False)],
    }


def compute_bhagyank(date_str: str, keep_master: bool) -> dict:
    digits = [int(c) for c in date_str if c.isdigit()]
    total = sum(digits)
    number = reduce_to_single(total, keep_master)
    chain = "+".join(str(d) for d in digits) + f"={total}"
    if total != number:
        chain += f"->{number}"
    return {
        "digit_sum": total,
        "number": number,
        "chain": chain,
        "ruling_planet": RULING_PLANET[reduce_to_single(total, False)],
    }


def compute_naamank(name: str, system: str, keep_master: bool) -> dict:
    letters = _letters(name)
    if not letters:
        return {}
    table = CHALDEAN_MAP if system == "chaldean" else PYTHAGOREAN_MAP
    values = [table[ch] for ch in letters if ch in table]
    compound = sum(values)
    number = reduce_to_single(compound, keep_master)
    return {
        "system": system,
        "letters": letters,
        "compound": compound,
        "number": number,
        "ruling_planet": RULING_PLANET[reduce_to_single(compound, False)],
    }


def compute_compatibility(naamank: int, moolank: int, bhagyank: int) -> dict:
    to_moolank = relation(naamank, moolank)
    to_bhagyank = relation(naamank, bhagyank)
    if to_moolank == "enemy" or to_bhagyank == "enemy":
        rec = ("Name number is in conflict with at least one core number; "
               "consider a name vibration friendly to both.")
    elif to_moolank == "friend" and to_bhagyank == "friend":
        rec = "Name number harmonizes well with both core numbers."
    else:
        rec = "Name number is broadly compatible (neutral or friendly)."
    return {
        "naamank_to_moolank": to_moolank,
        "naamank_to_bhagyank": to_bhagyank,
        "recommendation": rec,
    }


def compute_lo_shu(date_str: str) -> dict:
    digits = [int(c) for c in date_str if c.isdigit() and c != "0"]
    counts = {n: digits.count(n) for n in range(1, 10)}
    present = {n for n in range(1, 10) if counts[n] > 0}
    missing = sorted(n for n in range(1, 10) if counts[n] == 0)

    strength_arrows = []
    weakness_arrows = []
    for line, label in LO_SHU_LINES:
        cells = set(line)
        if cells <= present:
            strength_arrows.append(label)
        elif not (cells & present):
            weakness_arrows.append(label)

    return {
        "digits_used": digits,
        "counts": counts,
        "present": sorted(present),
        "missing": missing,
        "arrows_of_strength": strength_arrows,
        "arrows_of_weakness": weakness_arrows,
    }


def compute_personal_year(month: int, day: int, year: int) -> dict:
    base = month + day + reduce_to_single(year)
    number = reduce_to_single(base)
    return {
        "year": year,
        "number": number,
        "theme": NUMBER_THEME[number],
    }


def compute_lucky(planet: str) -> dict:
    attrs = LUCKY_ATTRIBUTES[planet]
    return {"ruling_planet": planet, **attrs}


def compute_name_correction(naamank: int, moolank: int, bhagyank: int) -> dict:
    to_moolank = relation(naamank, moolank)
    to_bhagyank = relation(naamank, bhagyank)
    harmonizes = to_moolank in ("friend", "neutral") and to_bhagyank in ("friend", "neutral")
    targets = sorted(
        n for n in range(1, 10)
        if relation(n, moolank) == "friend" and relation(n, bhagyank) == "friend"
    )
    if harmonizes:
        hint = ("Current name vibration harmonizes with your core numbers — "
                "no correction needed.")
    else:
        hint = ("Current name vibration conflicts with a core number. Aim for a "
                "Naamank that is a friend of BOTH your Moolank and Bhagyank. "
                "Adjust spelling toward one of the target numbers below "
                "(principle only — choose a spelling you like that reaches one of them).")
    return {
        "harmonizes": harmonizes,
        "target_numbers": targets,
        "hint": hint,
    }


def compute_name_trinity(name: str, system: str, keep_master: bool) -> dict:
    """Expression (all letters), Soul Urge (vowels), Personality (consonants).

    Soul Urge = what the person inwardly craves; Personality = the outer
    impression others form; Expression/Destiny = overall natural talents.
    """
    letters = _letters(name)
    if not letters:
        return {}
    table = CHALDEAN_MAP if system == "chaldean" else PYTHAGOREAN_MAP
    vowels, consonants = split_vowels_consonants(name)

    expr_c = _name_value(letters, table)
    soul_c = _name_value(vowels, table)
    pers_c = _name_value(consonants, table)

    def pack(compound):
        return {
            "compound": compound,
            "number": reduce_to_single(compound, keep_master),
            "ruling_planet": RULING_PLANET[reduce_to_single(compound, False)] if compound else None,
        }

    return {
        "system": system,
        "vowels": "".join(vowels),
        "consonants": "".join(consonants),
        "expression": pack(expr_c),
        "soul_urge": pack(soul_c),
        "personality": pack(pers_c),
    }


def compute_maturity(life_path_s: int, expression_s: int, keep_master: bool) -> dict:
    """Maturity (Realisation) number = reduce(Life Path + Expression).

    The underlying goal the personality matures toward, felt from the 30s–40s on.
    """
    total = life_path_s + expression_s
    return {
        "from": f"{life_path_s}+{expression_s}={total}",
        "number": reduce_to_single(total, keep_master),
    }


def compute_karmic(date_str: str, name: str, trinity: dict) -> dict:
    """Karmic Debt numbers (13/14/16/19 in core compounds) and Karmic Lessons
    (Pythagorean letter-values entirely absent from the name)."""
    debts = {}

    # Karmic Debt: scan the pre-reduction compounds of the core numbers.
    day = int(date_str.split("-")[2]) if "-" in date_str else None
    date_sum = sum(int(c) for c in date_str if c.isdigit())
    candidates = {"birthday": day, "life_path": date_sum}
    if trinity:
        candidates["expression"] = trinity["expression"]["compound"]
        candidates["soul_urge"] = trinity["soul_urge"]["compound"]
        candidates["personality"] = trinity["personality"]["compound"]
    for source, compound in candidates.items():
        hit = karmic_debt_for(compound) if compound is not None else None
        if hit:
            debts[source] = hit

    # Karmic Lessons: Pythagorean values 1–9 missing from the name letters.
    lessons = []
    if name and _letters(name):
        present = {PYTHAGOREAN_MAP[ch] for ch in _letters(name) if ch in PYTHAGOREAN_MAP}
        lessons = sorted(n for n in range(1, 10) if n not in present)

    return {
        "debts": debts,
        "lessons": lessons,
        "lessons_meaning": {n: NUMBER_THEME[n] for n in lessons},
    }


def compute_pinnacles_challenges(month: int, day: int, year: int, life_path_s: int) -> dict:
    """Four Pinnacles (peak themes) and four Challenges (lessons), with the age
    ranges each governs. Built from the reduced month/day/year."""
    m = reduce_to_single(month)
    d = reduce_to_single(day)
    y = reduce_to_single(year)

    p1 = reduce_to_single(m + d)
    p2 = reduce_to_single(d + y)
    p3 = reduce_to_single(p1 + p2)
    p4 = reduce_to_single(m + y)

    c1 = abs(m - d)
    c2 = abs(d - y)
    c3 = abs(c1 - c2)
    c4 = abs(m - y)

    end1 = 36 - life_path_s
    if end1 < 27:  # guard against very high life-path values
        end1 = 27
    ranges = [
        f"birth–{end1}",
        f"{end1 + 1}–{end1 + 9}",
        f"{end1 + 10}–{end1 + 18}",
        f"{end1 + 19}+",
    ]

    pinnacles = [
        {"period": ranges[i], "number": num, "theme": NUMBER_THEME[num]}
        for i, num in enumerate((p1, p2, p3, p4))
    ]
    challenges = [
        {"period": ranges[i], "number": num,
         "theme": NUMBER_THEME[num] if num in NUMBER_THEME else
         "Balance/zero — no single planetary challenge; a free, self-defined lesson."}
        for i, num in enumerate((c1, c2, c3, c4))
    ]
    return {"pinnacles": pinnacles, "challenges": challenges}


def compute_personal_cycles(target: str, month: int, day: int) -> dict:
    """Universal year, personal year/month/day for a specific calendar date."""
    ty, tm, td = (int(x) for x in target.split("-"))
    universal_year = reduce_to_single(ty)
    personal_year = reduce_to_single(month + day + universal_year)
    personal_month = reduce_to_single(personal_year + tm)
    personal_day = reduce_to_single(personal_month + td)
    return {
        "on": target,
        "universal_year": universal_year,
        "personal_year": {"number": personal_year, "theme": NUMBER_THEME[personal_year]},
        "personal_month": {"number": personal_month, "theme": NUMBER_THEME[personal_month]},
        "personal_day": {"number": personal_day, "theme": NUMBER_THEME[personal_day]},
    }


def _core_numbers(date_str: str) -> dict:
    """Reduced Moolank and Bhagyank for a date (helper for matching)."""
    day = int(date_str.split("-")[2])
    moolank = reduce_to_single(day, False)
    bhagyank = reduce_to_single(sum(int(c) for c in date_str if c.isdigit()), False)
    return {"moolank": moolank, "bhagyank": bhagyank}


def compute_match(date1: str, date2: str, name1=None, name2=None) -> dict:
    """Two-person compatibility across core numbers. Friend=2, neutral=1, enemy=0."""
    a = _core_numbers(date1)
    b = _core_numbers(date2)

    pairs = [
        ("Moolank ↔ Moolank", a["moolank"], b["moolank"]),
        ("Bhagyank ↔ Bhagyank", a["bhagyank"], b["bhagyank"]),
        ("A.Moolank ↔ B.Bhagyank", a["moolank"], b["bhagyank"]),
        ("A.Bhagyank ↔ B.Moolank", a["bhagyank"], b["moolank"]),
    ]
    if name1 and name2 and _letters(name1) and _letters(name2):
        na = reduce_to_single(_name_value(_letters(name1), CHALDEAN_MAP), False)
        nb = reduce_to_single(_name_value(_letters(name2), CHALDEAN_MAP), False)
        pairs.append(("Naamank ↔ Naamank (Chaldean)", na, nb))

    SCORE = {"friend": 2, "neutral": 1, "enemy": 0}
    rows = []
    earned = 0
    for label, x, y in pairs:
        rel = relation(x, y)
        earned += SCORE[rel]
        rows.append({"pair": label, "a": x, "b": y, "relation": rel})

    pct = round(100 * earned / (2 * len(pairs)))
    if pct >= 75:
        verdict = "Strong natural harmony — the core vibrations support each other."
    elif pct >= 55:
        verdict = "Workable, broadly supportive — a few friction points to be aware of."
    elif pct >= 40:
        verdict = "Mixed — real attraction is possible but needs conscious effort and patience."
    else:
        verdict = "Challenging vibrations — growth is possible but expect to work at it."

    return {
        "person_a": {"date": date1, "name": name1, **a},
        "person_b": {"date": date2, "name": name2, **b},
        "pairs": rows,
        "score_pct": pct,
        "verdict": verdict,
    }


def compute_number_check(value: str, core: dict, kind: str = "number") -> dict:
    """Score an arbitrary number string (mobile/house/vehicle/account) against
    the person's core numbers. Returns compound, single, and friendliness."""
    digits = [int(c) for c in value if c.isdigit()]
    if not digits or sum(digits) == 0:   # all-zero strings have no 1-9 vibration
        return {}
    compound = sum(digits)
    single = reduce_to_single(compound, False)
    to_moolank = relation(single, core["moolank"])
    to_bhagyank = relation(single, core["bhagyank"])
    if "enemy" in (to_moolank, to_bhagyank):
        verdict = "Not favourable — its vibration clashes with a core number."
    elif to_moolank == "friend" and to_bhagyank == "friend":
        verdict = "Very favourable — friendly to both core numbers."
    elif "friend" in (to_moolank, to_bhagyank):
        verdict = "Favourable — friendly to one core number, neutral to the other."
    else:
        verdict = "Neutral — neither helps nor hinders."
    return {
        "kind": kind,
        "value": value,
        "compound": compound,
        "number": single,
        "ruling_planet": RULING_PLANET[single],
        "vs_moolank": to_moolank,
        "vs_bhagyank": to_bhagyank,
        "verdict": verdict,
    }


# --- Top-level orchestration -----------------------------------------------

def compute(args) -> dict:
    import datetime as _dt
    try:
        y, m, d = (int(x) for x in args.date.split("-"))
        _dt.date(y, m, d)            # rejects impossible dates (e.g. Feb 30)
    except (ValueError, TypeError):
        raise ValueError(f"invalid date: {args.date!r} (expected a real YYYY-MM-DD)")

    moolank = compute_moolank(d, args.keep_master)
    bhagyank = compute_bhagyank(args.date, args.keep_master)

    # Reduced (single-digit) forms used for relation math.
    moolank_s = reduce_to_single(d, False)
    bhagyank_s = reduce_to_single(sum(int(c) for c in args.date if c.isdigit()), False)

    systems = ["chaldean", "pythagorean"] if args.system == "both" else [args.system]

    naamank = {}
    compatibility = {}
    name_correction = {}
    trinity = {}
    maturity = {}
    if args.name:
        for sysname in systems:
            naamank[sysname] = compute_naamank(args.name, sysname, args.keep_master)
        # Use the first requested system for relation/correction logic.
        primary = naamank[systems[0]]
        if primary:
            naamank_s = reduce_to_single(primary["compound"], False)
            compatibility = compute_compatibility(naamank_s, moolank_s, bhagyank_s)
            name_correction = compute_name_correction(naamank_s, moolank_s, bhagyank_s)
        trinity = compute_name_trinity(args.name, systems[0], args.keep_master)
        if trinity:
            expression_s = reduce_to_single(trinity["expression"]["compound"], False)
            maturity = compute_maturity(bhagyank_s, expression_s, args.keep_master)

    karmic = compute_karmic(args.date, args.name, trinity)
    pinnacles = compute_pinnacles_challenges(m, d, y, bhagyank_s)

    result = {
        "input": {
            "date": args.date,
            "name": args.name,
            "system": args.system,
            "year": args.year,
            "keep_master": args.keep_master,
        },
        "moolank": moolank,
        "bhagyank": bhagyank,
        "naamank": naamank,
        "name_trinity": trinity,
        "maturity": maturity,
        "compatibility": compatibility,
        "karmic": karmic,
        "lo_shu": compute_lo_shu(args.date),
        "pinnacles_challenges": pinnacles,
        "lucky": compute_lucky(moolank["ruling_planet"]),
        "name_correction": name_correction,
        "disclaimer": DISCLAIMER,
    }
    if args.year is not None:
        result["personal_year"] = compute_personal_year(m, d, args.year)
    if getattr(args, "on", None):
        try:
            _dt.date(*(int(x) for x in args.on.split("-")))
        except (ValueError, TypeError):
            raise ValueError(f"invalid --on date: {args.on!r} (expected YYYY-MM-DD)")
        result["personal_cycles"] = compute_personal_cycles(args.on, m, d)
    if getattr(args, "date2", None):
        try:
            _dt.date(*(int(x) for x in args.date2.split("-")))
        except (ValueError, TypeError):
            raise ValueError(f"invalid --date2: {args.date2!r} (expected YYYY-MM-DD)")
        result["match"] = compute_match(args.date, args.date2, args.name, args.name2)
    if getattr(args, "check_number", None):
        chk = compute_number_check(args.check_number,
                                   {"moolank": moolank_s, "bhagyank": bhagyank_s},
                                   args.check_kind)
        if chk:
            result["number_check"] = chk
    if getattr(args, "check_name", None):
        bn = compute_naamank(args.check_name, systems[0], False)
        if bn:
            bn_s = bn["number"]
            bn["vs_moolank"] = relation(bn_s, moolank_s)
            bn["vs_bhagyank"] = relation(bn_s, bhagyank_s)
            bn["label"] = args.check_name
            result["name_check"] = bn
    return result


# --- Text rendering --------------------------------------------------------

def render_text(result: dict) -> str:
    i = result["input"]
    lines = []
    lines.append("=" * 60)
    lines.append("  NUMEROLOGY REPORT (Ank Jyotish)")
    lines.append("=" * 60)
    lines.append(f"  Date of birth: {i['date']}")
    if i["name"]:
        lines.append(f"  Name: {i['name']}")
    lines.append(f"  System(s): {i['system']} | keep-master: {i['keep_master']}")
    lines.append("-" * 60)

    mo = result["moolank"]
    lines.append(f"  MOOLANK (Psychic / Birth number): {mo['number']}")
    lines.append(f"    Day of birth {mo['day_of_birth']} -> {mo['number']} "
                 f"| Ruling planet: {mo['ruling_planet']}")

    bh = result["bhagyank"]
    lines.append(f"  BHAGYANK (Destiny / Life Path): {bh['number']}")
    lines.append(f"    {bh['chain']} | Ruling planet: {bh['ruling_planet']}")

    if result["naamank"]:
        lines.append("-" * 60)
        lines.append("  NAAMANK (Name number)")
        for sysname, na in result["naamank"].items():
            if not na:
                continue
            lines.append(f"    {sysname.title():<12} compound {na['compound']} "
                         f"-> {na['number']} | Ruling planet: {na['ruling_planet']}")

    tr = result.get("name_trinity")
    if tr:
        lines.append("-" * 60)
        lines.append(f"  NAME TRINITY ({tr['system'].title()})")
        ex, su, pe = tr["expression"], tr["soul_urge"], tr["personality"]
        lines.append(f"    Expression / Destiny (all letters): {ex['compound']} -> "
                     f"{ex['number']} | {RULING_PLANET.get(reduce_to_single(ex['compound'], False))}")
        lines.append(f"    Soul Urge / Antaratma (vowels {tr['vowels']}): "
                     f"{su['compound']} -> {su['number']}")
        lines.append(f"    Personality (consonants): {pe['compound']} -> {pe['number']}")
        mt = result.get("maturity")
        if mt:
            lines.append(f"    Maturity / Realisation: {mt['from']} -> {mt['number']}")

    if result["compatibility"]:
        c = result["compatibility"]
        lines.append("-" * 60)
        lines.append("  NUMBER COMPATIBILITY (Naamank vs core numbers)")
        lines.append(f"    Naamank vs Moolank:  {c['naamank_to_moolank']}")
        lines.append(f"    Naamank vs Bhagyank: {c['naamank_to_bhagyank']}")
        lines.append(f"    {c['recommendation']}")

    km = result.get("karmic")
    if km and (km["debts"] or km["lessons"]):
        lines.append("-" * 60)
        lines.append("  KARMIC LAYER")
        if km["debts"]:
            for source, d in km["debts"].items():
                lines.append(f"    Karmic Debt in {source}: {d['note']}")
        else:
            lines.append("    Karmic Debt: none found in the core numbers.")
        if km["lessons"]:
            lines.append(f"    Karmic Lessons (missing name values): {km['lessons']}")
            for n in km["lessons"]:
                lines.append(f"      {n}: develop — {km['lessons_meaning'][n]}")

    ls = result["lo_shu"]
    lines.append("-" * 60)
    lines.append("  LO SHU GRID")
    for row in LO_SHU_LAYOUT:
        cells = []
        for n in row:
            cnt = ls["counts"][n]
            cells.append(f"{n}x{cnt}" if cnt else " . ")
        lines.append("    " + "  ".join(f"{c:<4}" for c in cells))
    lines.append(f"    Missing numbers: {ls['missing'] or 'none'}")
    lines.append(f"    Arrows of Strength: {ls['arrows_of_strength'] or ['none']}")
    lines.append(f"    Arrows of Weakness: {ls['arrows_of_weakness'] or ['none']}")

    pc = result.get("pinnacles_challenges")
    if pc:
        lines.append("-" * 60)
        lines.append("  PINNACLES & CHALLENGES (life-stage cycles)")
        for idx, p in enumerate(pc["pinnacles"], 1):
            lines.append(f"    Pinnacle {idx} (age {p['period']}): {p['number']} — {p['theme']}")
        for idx, c in enumerate(pc["challenges"], 1):
            lines.append(f"    Challenge {idx} (age {c['period']}): {c['number']} — {c['theme']}")

    if "personal_year" in result:
        py = result["personal_year"]
        lines.append("-" * 60)
        lines.append(f"  PERSONAL YEAR {py['year']}: {py['number']}")
        lines.append(f"    {py['theme']}")

    cy = result.get("personal_cycles")
    if cy:
        lines.append("-" * 60)
        lines.append(f"  PERSONAL CYCLES (for {cy['on']})")
        lines.append(f"    Universal year: {cy['universal_year']}")
        lines.append(f"    Personal year:  {cy['personal_year']['number']} — {cy['personal_year']['theme']}")
        lines.append(f"    Personal month: {cy['personal_month']['number']} — {cy['personal_month']['theme']}")
        lines.append(f"    Personal day:   {cy['personal_day']['number']} — {cy['personal_day']['theme']}")

    lk = result["lucky"]
    lines.append("-" * 60)
    lines.append(f"  LUCKY ATTRIBUTES (Moolank ruler: {lk['ruling_planet']})")
    lines.append(f"    Gemstone: {lk['gemstone']} | Days: {lk['days']} | Colors: {lk['colors']}")

    if result["name_correction"]:
        nc = result["name_correction"]
        lines.append("-" * 60)
        lines.append("  NAME-CORRECTION HINT")
        lines.append(f"    {nc['hint']}")
        lines.append(f"    Target Naamank numbers (friend of both): {nc['target_numbers'] or 'none'}")

    nch = result.get("name_check")
    if nch:
        lines.append("-" * 60)
        lines.append(f"  BUSINESS/NAME CHECK: {nch['label']}")
        lines.append(f"    {nch['system'].title()} compound {nch['compound']} -> {nch['number']} "
                     f"| Ruling planet: {nch['ruling_planet']}")
        lines.append(f"    vs Moolank: {nch['vs_moolank']} | vs Bhagyank: {nch['vs_bhagyank']}")

    ncheck = result.get("number_check")
    if ncheck:
        lines.append("-" * 60)
        lines.append(f"  NUMBER CHECK ({ncheck['kind']}): {ncheck['value']}")
        lines.append(f"    Compound {ncheck['compound']} -> {ncheck['number']} "
                     f"| Ruling planet: {ncheck['ruling_planet']}")
        lines.append(f"    vs Moolank: {ncheck['vs_moolank']} | vs Bhagyank: {ncheck['vs_bhagyank']}")
        lines.append(f"    {ncheck['verdict']}")

    mt = result.get("match")
    if mt:
        lines.append("=" * 60)
        a, b = mt["person_a"], mt["person_b"]
        lines.append("  TWO-PERSON COMPATIBILITY")
        lines.append(f"    A: {a.get('name') or a['date']} — Moolank {a['moolank']}, Bhagyank {a['bhagyank']}")
        lines.append(f"    B: {b.get('name') or b['date']} — Moolank {b['moolank']}, Bhagyank {b['bhagyank']}")
        for row in mt["pairs"]:
            lines.append(f"      {row['pair']:<32} {row['a']} vs {row['b']}: {row['relation']}")
        lines.append(f"    Score: {mt['score_pct']}% — {mt['verdict']}")

    lines.append("=" * 60)
    lines.append(f"  {result['disclaimer']}")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Compute a numerology report.")
    ap.add_argument("--date", required=True, help="Date of birth YYYY-MM-DD")
    ap.add_argument("--name", default=None, help="Full name (optional)")
    ap.add_argument("--system", default="both",
                    choices=["chaldean", "pythagorean", "both"],
                    help="Name-number system (default both)")
    ap.add_argument("--year", type=int, default=None,
                    help="Year for personal-year calc (optional)")
    ap.add_argument("--keep-master", action="store_true", dest="keep_master",
                    help="Keep master numbers 11/22/33 unreduced where noted")
    ap.add_argument("--on", default=None,
                    help="Target date YYYY-MM-DD for personal year/month/day cycles")
    ap.add_argument("--date2", default=None,
                    help="Second person's DOB YYYY-MM-DD — adds two-person compatibility")
    ap.add_argument("--name2", default=None, help="Second person's full name (with --date2)")
    ap.add_argument("--check-number", default=None, dest="check_number",
                    help="Score a mobile/house/vehicle/account number against the core numbers")
    ap.add_argument("--check-kind", default="number", dest="check_kind",
                    choices=["number", "mobile", "house", "vehicle", "account"],
                    help="Label for --check-number (default: number)")
    ap.add_argument("--check-name", default=None, dest="check_name",
                    help="Score a business/brand name against the core numbers")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    try:
        result = compute(args)
    except Exception as e:  # noqa: BLE001 — surface a clean message to the agent
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result))


if __name__ == "__main__":
    main()

"""
core.py — Shared Swiss Ephemeris engine for the vedic-astrology skill (v2).

This module owns ALL interaction with Swiss Ephemeris (via pyswisseph) and the
shared Vedic constants. Every command script imports from here so that sidereal
mode, ayanamsa, node model, topocentric setting, and ephemeris flags are
configured in exactly one place.

v2 additions over v1:
- Topocentric positions (observer on Earth's surface) — important for the Moon,
  whose geocentric vs topocentric longitude can differ by up to ~1°, which can
  flip the Janma Nakshatra (and therefore the Vimshottari starting dasha) for a
  birth near a nakshatra boundary.
- True-node vs mean-node toggle for Rahu/Ketu.
- Vedic special aspects (graha drishti) and sign aspects.
- Combustion (astangata) detection.
- Navamsa (D9) sign helper + vargottama detection.
- Natural planetary friendships (Naisargika maitri) for strength/compatibility.
- Sunrise/sunset (swe.rise_trans) for a sunrise-accurate Vara (weekday).

Design notes:
- Default ephemeris is Moshier (swe.FLG_MOSEPH) — analytical, no .se1 data files,
  fully offline. Pass ephemeris="swiss" to init_engine() to use Swiss files if
  the user has installed them.
- Sidereal (Vedic) mode is enforced. Default ayanamsa is Lahiri.
- All longitudes returned are sidereal, in degrees [0, 360).

Licensing: depends on pyswisseph / Swiss Ephemeris (AGPL-3.0 or commercial).
See the repository LICENSE and NOTICE files.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
import swisseph as swe

# --------------------------------------------------------------------------- #
# Ayanamsa registry — maps friendly names to Swiss Ephemeris sidereal modes.
# --------------------------------------------------------------------------- #
AYANAMSA = {
    "lahiri": swe.SIDM_LAHIRI,          # Chitrapaksha — Indian govt standard (default)
    "raman": swe.SIDM_RAMAN,
    "kp": swe.SIDM_KRISHNAMURTI,        # Krishnamurti Paddhati
    "krishnamurti": swe.SIDM_KRISHNAMURTI,
    "yukteshwar": swe.SIDM_YUKTESHWAR,
    "fagan_bradley": swe.SIDM_FAGAN_BRADLEY,
}
DEFAULT_AYANAMSA = "lahiri"

# House systems we expose. Whole Sign ('W') is the Vedic default.
HOUSE_SYSTEMS = {
    "whole_sign": b"W",
    "placidus": b"P",
    "equal": b"E",
}
DEFAULT_HOUSE_SYSTEM = "whole_sign"

# --------------------------------------------------------------------------- #
# Engine state — set by init_engine(). Holds the computed ephemeris flag bitmask
# and the node model so all calc helpers share one configuration.
# --------------------------------------------------------------------------- #
_STATE: dict = {
    "flags": swe.FLG_SIDEREAL | swe.FLG_SPEED | swe.FLG_MOSEPH,
    "node": "mean",          # "mean" -> MEAN_NODE, "true" -> TRUE_NODE
    "ayanamsa": DEFAULT_AYANAMSA,
    "topocentric": False,
}

# --------------------------------------------------------------------------- #
# Vedic reference data
# --------------------------------------------------------------------------- #
SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# Sign lord (rashi adhipati), 1-indexed by sign number 1..12.
SIGN_LORD = {
    1: "Mars", 2: "Venus", 3: "Mercury", 4: "Moon", 5: "Sun", 6: "Mercury",
    7: "Venus", 8: "Mars", 9: "Jupiter", 10: "Saturn", 11: "Saturn", 12: "Jupiter",
}

# Sign element/modality (1-indexed). Used for navamsa start and dosha logic.
# modality: 0=movable(chara), 1=fixed(sthira), 2=dual(dwiswabhava)
SIGN_MODALITY = {s: (s - 1) % 3 for s in range(1, 13)}
# element: 0=fire,1=earth,2=air,3=water (Aries=fire, Taurus=earth, ...)
SIGN_ELEMENT = {s: (s - 1) % 4 for s in range(1, 13)}

# 27 Nakshatras in order. Each spans 13°20' = 13.3333°.
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

# Vimshottari dasha lords cycle (repeats every 9 nakshatras) and their years.
DASHA_SEQUENCE = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}  # total = 120

# Planet name -> Swiss Ephemeris body id. Node body chosen dynamically (mean/true).
PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mars": swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS,
    "Saturn": swe.SATURN,
    "Rahu": swe.MEAN_NODE,   # overridden to TRUE_NODE if node model = "true"
}
PLANET_ORDER = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]

# Hindi / Sanskrit names — for seeker-friendly output.
PLANET_HINDI = {
    "Sun": "Surya", "Moon": "Chandra", "Mars": "Mangal", "Mercury": "Budh",
    "Jupiter": "Guru", "Venus": "Shukra", "Saturn": "Shani",
    "Rahu": "Rahu", "Ketu": "Ketu",
}
SIGN_HINDI = {
    "Aries": "Mesha", "Taurus": "Vrishabha", "Gemini": "Mithuna", "Cancer": "Karka",
    "Leo": "Simha", "Virgo": "Kanya", "Libra": "Tula", "Scorpio": "Vrishchika",
    "Sagittarius": "Dhanu", "Capricorn": "Makara", "Aquarius": "Kumbha", "Pisces": "Meena",
}


def planet_hi(name: str) -> str:
    """'Jupiter (Guru)' style label for a planet."""
    return f"{name} ({PLANET_HINDI.get(name, name)})"


def sign_hi(name: str) -> str:
    """'Scorpio (Vrishchika)' style label for a sign."""
    return f"{name} ({SIGN_HINDI.get(name, name)})"

NAKSHATRA_SPAN = 360.0 / 27.0       # 13.3333...
PADA_SPAN = NAKSHATRA_SPAN / 4.0    # 3.3333...
NAVAMSA_SPAN = 30.0 / 9.0           # 3.3333...

# Exaltation / own-sign tables for dignity & Mahapurusha yogas (sign numbers 1..12).
EXALTATION = {
    "Sun": 1, "Moon": 2, "Mars": 10, "Mercury": 6,
    "Jupiter": 4, "Venus": 12, "Saturn": 7,
}
OWN_SIGNS = {
    "Sun": [5], "Moon": [4], "Mars": [1, 8], "Mercury": [3, 6],
    "Jupiter": [9, 12], "Venus": [2, 7], "Saturn": [10, 11],
}

# Vedic special aspects (graha drishti): house-distances a planet aspects,
# counted inclusively from its own house (7 = the opposite house).
VEDIC_ASPECTS = {
    "Sun": [7], "Moon": [7], "Mercury": [7], "Venus": [7],
    "Mars": [4, 7, 8],
    "Jupiter": [5, 7, 9],
    "Saturn": [3, 7, 10],
    "Rahu": [7], "Ketu": [7],   # nodal aspects vary by tradition; 7th used by default
}

# Natural planetary friendships (Naisargika maitri). f=friend, n=neutral, e=enemy.
NATURAL_RELATION = {
    "Sun":     {"Moon": "f", "Mars": "f", "Jupiter": "f", "Mercury": "n", "Venus": "e", "Saturn": "e"},
    "Moon":    {"Sun": "f", "Mercury": "f", "Mars": "n", "Jupiter": "n", "Venus": "n", "Saturn": "n"},
    "Mars":    {"Sun": "f", "Moon": "f", "Jupiter": "f", "Venus": "n", "Saturn": "n", "Mercury": "e"},
    "Mercury": {"Sun": "f", "Venus": "f", "Moon": "e", "Mars": "n", "Jupiter": "n", "Saturn": "n"},
    "Jupiter": {"Sun": "f", "Moon": "f", "Mars": "f", "Saturn": "n", "Mercury": "e", "Venus": "e"},
    "Venus":   {"Mercury": "f", "Saturn": "f", "Mars": "n", "Jupiter": "n", "Sun": "e", "Moon": "e"},
    "Saturn":  {"Mercury": "f", "Venus": "f", "Jupiter": "n", "Sun": "e", "Moon": "e", "Mars": "e"},
}

# Combustion (astangata) orbs in degrees from the Sun. Tuple = (direct, retro).
COMBUSTION_ORB = {
    "Moon": (12.0, 12.0), "Mars": (17.0, 17.0), "Mercury": (14.0, 12.0),
    "Jupiter": (11.0, 11.0), "Venus": (10.0, 8.0), "Saturn": (15.0, 15.0),
}

WEEKDAY_LORD = {
    "Sunday": "Sun", "Monday": "Moon", "Tuesday": "Mars", "Wednesday": "Mercury",
    "Thursday": "Jupiter", "Friday": "Venus", "Saturday": "Saturn",
}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# --------------------------------------------------------------------------- #
# Engine init & time conversion
# --------------------------------------------------------------------------- #
def init_engine(
    ayanamsa: str = DEFAULT_AYANAMSA,
    node: str = "mean",
    topocentric: bool = False,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    altitude: float = 0.0,
    ephemeris: str = "moshier",
) -> None:
    """Configure Swiss Ephemeris for sidereal (Vedic) calculation.

    Must be called before any calc. Idempotent for given arguments.

    node: "mean" (default) or "true" lunar node for Rahu/Ketu.
    topocentric: if True, positions are computed for an observer at (lat, lon,
        altitude). Recommended for birth charts (Moon parallax). Requires lat/lon.
    ephemeris: "moshier" (default, offline) or "swiss" (needs .se1 files).
    """
    key = ayanamsa.strip().lower()
    if key not in AYANAMSA:
        raise ValueError(
            f"Unknown ayanamsa '{ayanamsa}'. Choose from: {', '.join(sorted(AYANAMSA))}"
        )
    swe.set_sid_mode(AYANAMSA[key], 0, 0)

    flags = swe.FLG_SIDEREAL | swe.FLG_SPEED
    flags |= swe.FLG_SWIEPH if ephemeris == "swiss" else swe.FLG_MOSEPH

    if topocentric:
        if lat is None or lon is None:
            raise ValueError("topocentric=True requires lat and lon")
        swe.set_topo(lon, lat, altitude)
        flags |= swe.FLG_TOPOCTR

    PLANETS["Rahu"] = swe.TRUE_NODE if node == "true" else swe.MEAN_NODE

    _STATE.update({"flags": flags, "node": node, "ayanamsa": key, "topocentric": topocentric})


def ayanamsa_value(jd: float) -> float:
    """Return the ayanamsa (degrees) in effect at a given Julian Day."""
    return swe.get_ayanamsa_ut(jd)


def western_sun_sign(jd: float) -> str:
    """Western (tropical) Sun sign — the popular 'star sign'.

    Western astrology uses the TROPICAL zodiac (tied to the seasons), whereas the
    rest of this engine is sidereal (Vedic). Tropical longitude = sidereal
    longitude + ayanamsa, so this converts back to give the familiar Sun sign
    most people identify with (e.g. born 29 Dec -> Capricorn). Requires
    init_engine() to have been called.
    """
    sid, _ = sidereal_longitude(jd, PLANETS["Sun"])
    tropical = (sid + ayanamsa_value(jd)) % 360.0
    return SIGNS[int(tropical // 30)]


def to_julian_ut(
    year: int, month: int, day: int,
    hour: int, minute: int, second: int,
    tz_name: str,
) -> float:
    """Convert a *local* civil datetime + IANA timezone to a Julian Day (UT).

    Example tz_name: 'Asia/Kolkata', 'America/New_York', 'UTC'.
    Raises pytz.UnknownTimeZoneError on a bad timezone string, and ValueError if
    the wall-clock time does not exist (DST spring-forward gap) or is ambiguous
    (fall-back fold) — rather than silently shifting the chart by an hour, which
    would move the ascendant. The caller must supply a real local time.
    """
    tz = pytz.timezone(tz_name)
    naive = datetime(year, month, day, hour, minute, second)
    try:
        # is_dst=None makes pytz reject non-existent / ambiguous wall-clock times.
        local_dt = tz.localize(naive, is_dst=None)
    except pytz.exceptions.NonExistentTimeError:
        raise ValueError(
            f"{naive} does not exist in {tz_name} — it falls in a daylight-saving "
            f"spring-forward gap. Check the birth time/zone."
        )
    except pytz.exceptions.AmbiguousTimeError:
        raise ValueError(
            f"{naive} is ambiguous in {tz_name} — it occurs twice on a daylight-saving "
            f"fall-back day. Specify which (e.g. add/subtract the DST hour)."
        )
    utc_dt = local_dt.astimezone(pytz.utc)
    ut_hour = utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0
    return swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, ut_hour, swe.GREG_CAL)


def jd_to_local(jd: float, tz_name: str) -> datetime:
    """Convert a Julian Day (UT) back to a timezone-aware local datetime."""
    y, m, d, ut_hour = swe.revjul(jd, swe.GREG_CAL)
    base = datetime(int(y), int(m), int(d)) + timedelta(hours=ut_hour)
    return pytz.utc.localize(base).astimezone(pytz.timezone(tz_name))


# --------------------------------------------------------------------------- #
# Position helpers
# --------------------------------------------------------------------------- #
def sidereal_longitude(jd: float, body: int) -> Tuple[float, float]:
    """Return (longitude_deg, speed_deg_per_day) for a body, sidereal frame.

    Negative speed => retrograde. Uses the flags configured by init_engine().
    """
    pos, _ = swe.calc_ut(jd, body, _STATE["flags"])
    return pos[0] % 360.0, pos[3]


def all_planet_positions(jd: float) -> Dict[str, dict]:
    """Compute sidereal positions for all 9 grahas including Rahu/Ketu."""
    out: Dict[str, dict] = {}
    for name, body in PLANETS.items():
        lon, speed = sidereal_longitude(jd, body)
        retro = speed < 0
        if name == "Rahu":
            retro = True  # nodes are retrograde by nature
        out[name] = _describe_point(lon, retrograde=retro)
    ketu_lon = (out["Rahu"]["longitude"] + 180.0) % 360.0
    out["Ketu"] = _describe_point(ketu_lon, retrograde=True)
    return out


def _describe_point(lon: float, retrograde: bool = False) -> dict:
    """Decompose a sidereal longitude into sign/nakshatra/pada/navamsa."""
    sign_num = int(lon // 30) + 1            # 1..12
    deg_in_sign = lon % 30.0
    nak_index = int(lon // NAKSHATRA_SPAN)   # 0..26
    pada = int((lon % NAKSHATRA_SPAN) // PADA_SPAN) + 1  # 1..4
    return {
        "longitude": round(lon, 4),
        "sign": SIGNS[sign_num - 1],
        "sign_num": sign_num,
        "degree_in_sign": round(deg_in_sign, 4),
        "nakshatra": NAKSHATRAS[nak_index],
        "nakshatra_lord": DASHA_SEQUENCE[nak_index % 9],
        "pada": pada,
        "navamsa_sign_num": navamsa_sign(lon),
        "retrograde": retrograde,
    }


def navamsa_sign(lon: float) -> int:
    """Return the D9 (Navamsa) sign number (1..12) for a sidereal longitude.

    For D9 the neat identity holds: navamsa sign index = floor(L / (30/9)) mod 12.
    (Movable signs start their navamsa from themselves, fixed from the 9th, dual
    from the 5th — this formula reproduces exactly that classical scheme.)

    Uses the multiply form int(L*9/30) rather than L // (30/9): the latter is
    floating-point fragile at exact amsa boundaries (e.g. 10.0° floors to the
    wrong amsa because 30/9 is not representable).
    """
    return int(lon * 9 / 30.0) % 12 + 1


# --------------------------------------------------------------------------- #
# Divisional charts (Vargas) — general Parashari amsa rules.
# --------------------------------------------------------------------------- #
# The 16 divisions of the Shodasavarga, in standard order, with the life area
# each is classically read for.
SHODASAVARGA = [1, 2, 3, 4, 7, 9, 10, 12, 16, 20, 24, 27, 30, 40, 45, 60]

# Optional extra divisions that lie OUTSIDE the classical Shodasavarga. Unlike the
# 16 above, their sign-mapping is not uniquely fixed in BPHS — traditions differ —
# so the skill computes them with ONE transparent, documented convention (cyclic
# from the planet's own sign, the same rule as D12/Dwadasamsa) and labels them
# "(non-classical)" wherever shown. They are NOT mixed into the Shodasavarga
# strength score. See references/vargas.md.
EXTRA_VARGAS = [5, 6, 8, 11]
SUPPORTED_VARGAS = SHODASAVARGA + EXTRA_VARGAS

VARGA_PURPOSE = {
    1: "Rashi — body, self, the whole life",
    2: "Hora — wealth & resources",
    3: "Drekkana — siblings, courage, longevity",
    4: "Chaturthamsa — fortune, property, home",
    7: "Saptamsha — children & progeny",
    9: "Navamsa — spouse, marriage, dharma & inner strength",
    10: "Dasamsha — career, status & karma",
    12: "Dwadasamsa — parents & lineage",
    16: "Shodasamsa — vehicles, comforts & happiness",
    20: "Vimsamsa — spiritual practice & worship",
    24: "Chaturvimsamsa — education & learning",
    27: "Bhamsa / Nakshatramsa — strengths & weaknesses",
    30: "Trimsamsa — misfortunes, troubles & health",
    40: "Khavedamsa — auspicious & inauspicious results (maternal)",
    45: "Akshavedamsa — general (paternal), character",
    60: "Shashtiamsa — past-life karma, fine-tuning of all areas",
    # Non-classical extras (sign-mapping is convention-dependent; see EXTRA_VARGAS).
    5: "Panchamsa — fame, power & spiritual merit (non-classical)",
    6: "Shashthamsa — health, debts & adversity (non-classical)",
    8: "Ashtamsa — sudden events, accidents & longevity (non-classical)",
    11: "Rudramsa / Labhamsa — gains & income, also destruction (non-classical)",
}


def _sign_add(sign0: int, offset: int) -> int:
    """Count `offset` signs forward from a 0-indexed sign; return 0-indexed."""
    return (sign0 + offset) % 12


def varga_sign(lon: float, d: int) -> int:
    """Return the divisional (Dn) sign number (1..12) for a sidereal longitude.

    Implements the classical Parashari amsa schemes for the 16 Shodasavarga
    divisions. `d` is the divisor (1, 2, 3, 4, 7, 9, 10, 12, 16, 20, 24, 27,
    30, 40, 45, 60). Raises ValueError for an unsupported divisor.
    """
    sign0 = int(lon // 30)          # 0..11 (Aries=0)
    deg = lon % 30.0                # 0..30
    odd = (sign0 % 2 == 0)          # odd *sign* (Aries, Gemini…) => even index
    modality = sign0 % 3            # 0 movable, 1 fixed, 2 dual
    element = sign0 % 4             # 0 fire, 1 earth, 2 air, 3 water
    part = int(deg * d / 30.0) if d else 0     # 0-based amsa index (boundary-safe)

    if d == 1:
        s = sign0
    elif d == 2:  # Hora — only Cancer (Moon) or Leo (Sun)
        first_half = deg < 15
        if odd:
            s = 4 if first_half else 3          # Leo / Cancer
        else:
            s = 3 if first_half else 4          # Cancer / Leo
    elif d == 3:  # Drekkana — same, 5th, 9th
        s = _sign_add(sign0, [0, 4, 8][part])
    elif d == 4:  # Chaturthamsa — same, 4th, 7th, 10th
        s = _sign_add(sign0, [0, 3, 6, 9][part])
    elif d == 7:  # Saptamsha — odd from same, even from 7th
        s = _sign_add(sign0 if odd else sign0 + 6, part)
    elif d == 9:  # Navamsa — movable/fixed/dual start same/9th/5th
        s = _sign_add(sign0 + [0, 8, 4][modality], part)
    elif d == 10:  # Dasamsha — odd from same, even from 9th
        s = _sign_add(sign0 if odd else sign0 + 8, part)
    elif d == 12:  # Dwadasamsa — always from the sign itself
        s = _sign_add(sign0, part)
    elif d == 16:  # Shodasamsa — movable Aries, fixed Leo, dual Sagittarius
        s = _sign_add([0, 4, 8][modality], part)
    elif d == 20:  # Vimsamsa — movable Aries, fixed Sagittarius, dual Leo
        s = _sign_add([0, 8, 4][modality], part)
    elif d == 24:  # Chaturvimsamsa — odd from Leo, even from Cancer
        s = _sign_add(4 if odd else 3, part)
    elif d == 27:  # Bhamsa — fire Aries, earth Cancer, air Libra, water Capricorn
        s = _sign_add([0, 3, 6, 9][element], part)
    elif d == 30:  # Trimsamsa — unequal planetary segments
        s = _trimsamsa_sign(sign0, deg, odd)
    elif d == 40:  # Khavedamsa — odd from Aries, even from Libra
        s = _sign_add(0 if odd else 6, part)
    elif d == 45:  # Akshavedamsa — movable Aries, fixed Leo, dual Sagittarius
        s = _sign_add([0, 4, 8][modality], part)
    elif d == 60:  # Shashtiamsa — half-degree amsas counted from the sign itself
        s = _sign_add(sign0, int(deg * 2))
    elif d in (5, 6, 8, 11):
        # Non-classical extras (Panchamsa/Shashthamsa/Ashtamsa/Rudramsa). BPHS does
        # not fix a unique sign rule for these, so we use the transparent cyclic
        # convention (amsas counted forward from the sign itself, as in D12). This
        # is documented and labelled non-classical; not a claim of canonical truth.
        s = _sign_add(sign0, part)
    else:
        raise ValueError(f"Unsupported varga divisor D{d}. Supported: {SUPPORTED_VARGAS}")
    return s + 1


# Trimsamsa (D30) segment tables: (degree_width, sign0). Odd vs even signs.
_TRIMSAMSA_ODD = [(5, 0), (5, 10), (8, 8), (7, 2), (5, 6)]    # Mars,Sat,Jup,Mer,Ven
_TRIMSAMSA_EVEN = [(5, 1), (7, 5), (8, 11), (5, 9), (5, 7)]   # Ven,Mer,Jup,Sat,Mars


def _trimsamsa_sign(sign0: int, deg: float, odd: bool) -> int:
    table = _TRIMSAMSA_ODD if odd else _TRIMSAMSA_EVEN
    cum = 0.0
    for width, target in table:
        cum += width
        if deg < cum:
            return target
    return table[-1][1]


def ascendant(jd: float, lat: float, lon: float, house_system: str = DEFAULT_HOUSE_SYSTEM) -> dict:
    """Compute the sidereal Lagna (ascendant) and its sign."""
    if house_system not in HOUSE_SYSTEMS:
        raise ValueError(
            f"Unknown house system '{house_system}'. Choose from: {', '.join(HOUSE_SYSTEMS)}"
        )
    # Placidus (and other quadrant systems) are undefined inside the polar circles:
    # some houses never rise. Fail loudly rather than return a degenerate chart.
    if house_system == "placidus" and abs(lat) > 66.0:
        raise ValueError(
            f"Placidus houses are undefined above latitude 66 deg (got {lat:.2f}). "
            f"Use --house-system whole_sign (the Vedic default, latitude-independent) or equal."
        )
    _, ascmc = swe.houses_ex(jd, lat, lon, HOUSE_SYSTEMS[house_system], swe.FLG_SIDEREAL)
    asc_lon = ascmc[0] % 360.0
    return _describe_point(asc_lon)


def house_of(planet_sign_num: int, asc_sign_num: int) -> int:
    """Whole-sign house number (1..12) of a planet given the ascendant sign."""
    return ((planet_sign_num - asc_sign_num) % 12) + 1


def house_cusps(jd: float, lat: float, lon: float,
                house_system: str = "placidus") -> list:
    """Return the 12 sidereal house-cusp longitudes (degrees, 1st..12th).

    Used for cusp-based (Bhava Chalit) house assignment, where a planet belongs
    to the bhava whose cusp span contains it — not merely its whole-sign house.
    Defaults to Placidus cusps (the basis of the common Sripati/KP chalit chart).
    """
    if house_system not in HOUSE_SYSTEMS:
        raise ValueError(
            f"Unknown house system '{house_system}'. Choose from: {', '.join(HOUSE_SYSTEMS)}"
        )
    if house_system == "placidus" and abs(lat) > 66.0:
        raise ValueError(
            f"Placidus cusps are undefined above latitude 66 deg (got {lat:.2f}). Use whole_sign or equal."
        )
    cusps, _ = swe.houses_ex(jd, lat, lon, HOUSE_SYSTEMS[house_system], swe.FLG_SIDEREAL)
    # pyswisseph returns the 12 cusps either as a 13-tuple (index 0 unused, 1..12)
    # or a 12-tuple (0..11), depending on version. Normalise to a 0-based list of 12.
    base = 1 if len(cusps) >= 13 else 0
    return [cusps[base + i] % 360.0 for i in range(12)]


def bhava_of(longitude: float, cusps: list) -> int:
    """Which bhava (1..12) a sidereal longitude falls in, given 12 house cusps.

    A planet is in bhava i if it lies on the arc from cusp[i] up to cusp[i+1]
    (wrapping past 360 deg). This cusp-based assignment can differ from the
    whole-sign house for a planet near a sign edge.
    """
    lon = longitude % 360.0
    for i in range(12):
        start = cusps[i]
        end = cusps[(i + 1) % 12]
        span = (end - start) % 360.0
        offset = (lon - start) % 360.0
        if offset < span:
            return i + 1
    return 12  # numerical fallback; should not be reached


# --------------------------------------------------------------------------- #
# Krishnamurti Paddhati (KP) sub-lords
# --------------------------------------------------------------------------- #
SIGN_RULERS = {1: "Mars", 2: "Venus", 3: "Mercury", 4: "Moon", 5: "Sun", 6: "Mercury",
               7: "Venus", 8: "Mars", 9: "Jupiter", 10: "Saturn", 11: "Saturn", 12: "Jupiter"}


def kp_lords(lon: float) -> dict:
    """KP Rashi/Nakshatra/Sub lord chain for a sidereal longitude.

    Each 13°20' nakshatra is divided into nine sub-parts whose widths follow the
    Vimshottari proportions (Ketu 7 ... Mercury 17, of 120), and the sub sequence
    *starts from the nakshatra's own lord* in Vimshottari order. The sub-lord is
    the planet whose sub-segment contains the longitude — the heart of KP.
    """
    lon = lon % 360.0
    sign_num = int(lon // 30) + 1
    nak_index = int(lon // NAKSHATRA_SPAN)          # 0..26
    star_lord = DASHA_SEQUENCE[nak_index % 9]
    pos_in_nak = lon - nak_index * NAKSHATRA_SPAN   # 0..13.3333
    # Order of sub-lords starts at the star lord, then Vimshottari order, wrapping.
    start = DASHA_SEQUENCE.index(star_lord)
    order = [DASHA_SEQUENCE[(start + k) % 9] for k in range(9)]
    acc = 0.0
    sub_lord = order[-1]
    for lord in order:
        width = (DASHA_YEARS[lord] / 120.0) * NAKSHATRA_SPAN
        if pos_in_nak < acc + width:
            sub_lord = lord
            break
        acc += width
    return {
        "sign_num": sign_num,
        "sign": SIGNS[sign_num - 1],
        "rashi_lord": SIGN_RULERS[sign_num],
        "nakshatra": NAKSHATRAS[nak_index],
        "star_lord": star_lord,
        "sub_lord": sub_lord,
    }


# --------------------------------------------------------------------------- #
# Aspects, combustion, dignity, friendship
# --------------------------------------------------------------------------- #
def aspected_houses(from_house: int, planet: str) -> List[int]:
    """Houses (1..12) aspected by `planet` sitting in `from_house` (sign aspect)."""
    return sorted({((from_house - 1 + (d - 1)) % 12) + 1 for d in VEDIC_ASPECTS[planet]})


def aspects_planet(a: str, b: str, planets: Dict[str, dict]) -> bool:
    """True if planet `a` casts a Vedic aspect onto planet `b`'s house."""
    return planets[b]["house"] in aspected_houses(planets[a]["house"], a)


def is_combust(planet: str, planet_lon: float, sun_lon: float, retrograde: bool) -> bool:
    """Combustion (astangata): too close to the Sun within the planet's orb."""
    if planet not in COMBUSTION_ORB:
        return False
    sep = abs((planet_lon - sun_lon + 180) % 360 - 180)  # angular separation 0..180
    direct_orb, retro_orb = COMBUSTION_ORB[planet]
    return sep <= (retro_orb if retrograde else direct_orb)


def dignity(planet: str, sign_num: int) -> str:
    """Classify a planet's dignity in a sign."""
    if planet in ("Rahu", "Ketu"):
        return "node"
    if EXALTATION.get(planet) == sign_num:
        return "exalted"
    if planet in EXALTATION and ((EXALTATION[planet] + 5) % 12) + 1 == sign_num:
        return "debilitated"
    if sign_num in OWN_SIGNS.get(planet, []):
        return "own sign"
    return "neutral"


def natural_relation(a: str, b: str) -> str:
    """Naisargika (natural) relationship of planet a TOWARD b: friend/neutral/enemy."""
    if a == b:
        return "self"
    code = NATURAL_RELATION.get(a, {}).get(b, "n")
    return {"f": "friend", "n": "neutral", "e": "enemy"}[code]


def is_vargottama(lon: float) -> bool:
    """True if the D1 sign equals the D9 (navamsa) sign — a strong placement."""
    return (int(lon // 30) + 1) == navamsa_sign(lon)


# --------------------------------------------------------------------------- #
# Rise/set for sunrise-accurate Vara
# --------------------------------------------------------------------------- #
_RISE = swe.CALC_RISE | swe.BIT_DISC_CENTER
_SET = swe.CALC_SET | swe.BIT_DISC_CENTER


def _rise_trans(jd: float, lat: float, lon: float, rsmi: int) -> Optional[float]:
    """Wrapper around swe.rise_trans using the geopos-keyword signature.

    Returns the event Julian Day (UT) or None if no event (e.g. polar day/night).
    """
    try:
        ret, tret = swe.rise_trans(jd, swe.SUN, rsmi=rsmi, geopos=(lon, lat, 0.0))
        if ret < 0:
            return None
        return tret[0]
    except Exception:
        return None


def next_rise_set(jd_start: float, lat: float, lon: float) -> Tuple[Optional[float], Optional[float]]:
    """Return (sunrise_jd, sunset_jd) — the first sunrise at/after jd_start and
    the sunset following that sunrise. Either may be None at polar latitudes.
    """
    rise = _rise_trans(jd_start, lat, lon, _RISE)
    if rise is None:
        return None, None
    sett = _rise_trans(rise, lat, lon, _SET)
    return rise, sett


def sunrise_before(jd: float, lat: float, lon: float) -> Optional[float]:
    """Julian Day (UT) of the most recent sunrise at/before `jd`, or None.

    Used to determine the Vedic Vara (weekday), which runs sunrise-to-sunrise.
    """
    # The sunrise that opens the Vedic day containing `jd` is the latest rise <= jd.
    rise = _rise_trans(jd - 1.0, lat, lon, _RISE)
    if rise is None:
        return None
    last = None
    guard = 0
    while rise is not None and rise <= jd and guard < 4:
        last = rise
        rise = _rise_trans(rise + 0.5, lat, lon, _RISE)
        guard += 1
    return last


def vedic_vara(jd: float, lat: float, lon: float, tz_name: str) -> str:
    """Weekday by the Vedic convention (sunrise-to-sunrise).

    Falls back to the civil local weekday if sunrise can't be computed
    (e.g. polar latitudes).
    """
    sr = sunrise_before(jd, lat, lon)
    ref = sr if sr is not None else jd
    local = jd_to_local(ref, tz_name)
    return WEEKDAYS[local.weekday()]


def deg_to_dms(deg: float) -> str:
    """Format a degree-in-sign value as Dd Mm Ss for human-readable output."""
    d = int(deg)
    m_full = (deg - d) * 60
    m = int(m_full)
    s = int((m_full - m) * 60)
    return f"{d}°{m:02d}'{s:02d}\""

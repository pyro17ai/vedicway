"""
Robustness tests — independent of the engine's own conventions.

Unlike test_cli.py (which pins this engine's own output as golden values), these
tests assert facts that come from ASTRONOMY, not from this code: an eclipse is an
exact Sun-Moon conjunction; Mercury and Venus can never stray far from the Sun;
the Lahiri ayanamsa has a known magnitude; tropical minus sidereal must equal the
ayanamsa. They also fuzz hundreds of deterministic (date, place) combinations and
assert structural invariants that must hold for every chart.

No new dependencies: deterministic index-seeded fuzzing instead of Hypothesis.

Run:  pytest -q tests/test_robustness.py
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "vedic-astrology", "scripts"))

import core  # noqa: E402
import swisseph as swe  # noqa: E402


def setup_module(_):
    # geocentric so body-only tests don't need a place; Lahiri sidereal.
    core.init_engine(ayanamsa="lahiri", node="mean", topocentric=False)


def ang_sep(a, b):
    """Smallest angular separation between two longitudes (0..180)."""
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


# A spread of deterministic (year, month, day, hour) tuples — no randomness.
def fuzz_datetimes(n=160):
    out = []
    for i in range(n):
        year = 1850 + (i * 17) % 200          # 1850..2049
        month = 1 + (i * 5) % 12
        day = 1 + (i * 11) % 28
        hour = (i * 13) % 24
        out.append((year, month, day, hour))
    return out


def fuzz_places(i):
    """A deterministic place with |lat| < 60 (Placidus-safe)."""
    lat = -55.0 + (i * 23) % 110              # -55..54
    lon = -179.0 + (i * 37) % 358             # -179..178
    return lat, lon


# --------------------------------------------------------------------------- #
# Astronomy anchors (NOT self-referential)
# --------------------------------------------------------------------------- #
def test_lahiri_ayanamsa_magnitude_at_j2000():
    # Lahiri/Chitrapaksha ayanamsa at J2000.0 is ~23.85 deg (well-published).
    jd = 2451545.0
    a = core.ayanamsa_value(jd)
    assert 23.6 < a < 24.1, f"Lahiri ayanamsa at J2000 looks wrong: {a}"


def test_tropical_minus_sidereal_equals_ayanamsa():
    jd = core.to_julian_ut(1990, 8, 15, 14, 30, 0, "Asia/Kolkata")
    sid, _ = core.sidereal_longitude(jd, core.PLANETS["Sun"])
    trop, _ = swe.calc_ut(jd, core.PLANETS["Sun"], swe.FLG_MOSEPH)  # tropical, no sidereal flag
    diff = (trop[0] - sid) % 360.0
    assert ang_sep(diff, core.ayanamsa_value(jd)) < 0.02


def test_eclipse_is_a_sun_moon_conjunction():
    # 2024-04-08 total solar eclipse, maximum ~18:18 UT — Sun & Moon coincide.
    jd = swe.julday(2024, 4, 8, 18 + 18 / 60.0, swe.GREG_CAL)
    sun, _ = core.sidereal_longitude(jd, core.PLANETS["Sun"])
    moon, _ = core.sidereal_longitude(jd, core.PLANETS["Moon"])
    assert ang_sep(sun, moon) < 1.5, "Sun/Moon not conjunct at a known total eclipse"


def test_inner_planets_never_far_from_sun():
    # Max elongation: Mercury ~28 deg, Venus ~47 deg. Difference is ayanamsa-free.
    for (y, m, d, h) in fuzz_datetimes():
        jd = swe.julday(y, m, d, h + 0.0, swe.GREG_CAL)
        sun, _ = core.sidereal_longitude(jd, core.PLANETS["Sun"])
        mer, _ = core.sidereal_longitude(jd, core.PLANETS["Mercury"])
        ven, _ = core.sidereal_longitude(jd, core.PLANETS["Venus"])
        assert ang_sep(sun, mer) <= 29.0, f"Mercury too far from Sun on {y}-{m}-{d}"
        assert ang_sep(sun, ven) <= 48.5, f"Venus too far from Sun on {y}-{m}-{d}"


def test_sun_and_moon_never_retrograde():
    for (y, m, d, h) in fuzz_datetimes():
        jd = swe.julday(y, m, d, h + 0.0, swe.GREG_CAL)
        _, sun_sp = core.sidereal_longitude(jd, core.PLANETS["Sun"])
        _, moon_sp = core.sidereal_longitude(jd, core.PLANETS["Moon"])
        assert sun_sp > 0 and moon_sp > 0


# --------------------------------------------------------------------------- #
# Structural invariants over many charts
# --------------------------------------------------------------------------- #
def test_ketu_is_opposite_rahu_everywhere():
    for (y, m, d, h) in fuzz_datetimes():
        jd = swe.julday(y, m, d, h + 0.0, swe.GREG_CAL)
        pos = core.all_planet_positions(jd)
        assert ang_sep(pos["Ketu"]["longitude"],
                       (pos["Rahu"]["longitude"] + 180.0) % 360.0) < 1e-6


def test_chart_invariants_fuzz():
    for i, (y, m, d, h) in enumerate(fuzz_datetimes()):
        jd = swe.julday(y, m, d, h + 0.0, swe.GREG_CAL)
        pos = core.all_planet_positions(jd)
        for name, p in pos.items():
            assert 1 <= p["sign_num"] <= 12
            assert 1 <= p["pada"] <= 4
            assert p["nakshatra"] in core.NAKSHATRAS
            for dvn in core.SUPPORTED_VARGAS:
                assert 1 <= core.varga_sign(p["longitude"], dvn) <= 12
        lat, lon = fuzz_places(i)
        asc = core.ascendant(jd, lat, lon, "whole_sign")
        assert 1 <= asc["sign_num"] <= 12


def test_vimshottari_periods_sum_to_120_years():
    assert sum(core.DASHA_YEARS.values()) == 120


# --------------------------------------------------------------------------- #
# Guards & cusp helpers
# --------------------------------------------------------------------------- #
def test_placidus_high_latitude_raises_but_whole_sign_ok():
    jd = core.to_julian_ut(1990, 1, 1, 12, 0, 0, "UTC")
    with pytest.raises(ValueError):
        core.ascendant(jd, 78.0, 15.0, "placidus")   # Svalbard — polar
    # whole-sign is latitude-independent and must still work
    asc = core.ascendant(jd, 78.0, 15.0, "whole_sign")
    assert 1 <= asc["sign_num"] <= 12


def test_house_cusps_and_bhava_assignment():
    jd = core.to_julian_ut(1990, 8, 15, 14, 30, 0, "Asia/Kolkata")
    cusps = core.house_cusps(jd, 28.6139, 77.2090, "placidus")
    assert len(cusps) == 12
    assert all(0.0 <= c < 360.0 for c in cusps)
    # a longitude one degree past the 1st cusp is in bhava 1
    assert core.bhava_of((cusps[0] + 1.0) % 360.0, cusps) == 1
    # one degree before the 1st cusp wraps into bhava 12
    assert core.bhava_of((cusps[0] - 1.0) % 360.0, cusps) == 12


def test_synthetic_equal_cusps_bhava_math():
    cusps = [(5.0 + 30 * i) % 360.0 for i in range(12)]  # 1st cusp at 5 deg Aries
    assert core.bhava_of(6.0, cusps) == 1
    assert core.bhava_of(36.0, cusps) == 2
    assert core.bhava_of(4.0, cusps) == 12


# --------------------------------------------------------------------------- #
# CLI features added in the robustness/systems waves (run as subprocess)
# --------------------------------------------------------------------------- #
import json  # noqa: E402
import subprocess  # noqa: E402

VEDIC = os.path.join(REPO, "vedic-astrology", "scripts")
REF = ["--date", "1990-08-15", "--time", "14:30:00",
       "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata"]


def _run(script, extra=()):
    cmd = [sys.executable, script, *REF, *extra, "--json"]
    p = subprocess.run(cmd, cwd=VEDIC, capture_output=True, text=True)
    assert p.returncode == 0, f"{script} failed:\n{p.stderr}"
    return json.loads(p.stdout)


def test_chalit_reports_house_shifts():
    r = _run("chalit.py")
    assert len(r["planets"]) == 9
    for p in r["planets"]:
        assert 1 <= p["whole_sign_house"] <= 12
        assert 1 <= p["chalit_house"] <= 12
        assert p["shifted"] == (p["whole_sign_house"] != p["chalit_house"])
    # the reference chart has planets near sign edges -> at least one shift
    assert r["shift_count"] >= 1
    # Ketu must stay exactly opposite Rahu in the chalit chart too (6 houses apart)
    h = {p["planet"]: p["chalit_house"] for p in r["planets"]}
    assert (h["Ketu"] - h["Rahu"]) % 12 == 6


def test_varshaphal_solar_return_hits_natal_sun():
    r = _run("varshaphal.py", ("--age", "36"))
    natal = r["natal"]["sun_longitude"]
    ret = r["solar_return"]["sun_longitude_check"]
    d = abs((natal - ret + 180) % 360 - 180)
    assert d < 0.001, f"solar return Sun {ret} != natal Sun {natal}"
    # Muntha at an age that is a multiple of 12 returns to the natal Lagna sign.
    assert r["muntha"]["sign_num"] == r["natal"]["ascendant_sign_num"]
    assert len(r["varshesha_candidates"]) == 5


def test_shadbala_is_complete_and_six_fold():
    r = _run("strength.py")
    sb = r["shadbala"]
    assert sb.get("complete") is True
    one = next(iter(sb["planets"].values()))
    comps = one["components_virupa"]
    flat = " ".join(comps.keys()).lower()
    assert "sthana" in comps  # nested sub-components
    for src in ("dig", "kala", "cheshta", "naisargika", "drik"):
        assert src in flat, f"Shadbala missing {src}"


def test_kp_sublord_pure_function_invariants():
    # sub-lord widths within each nakshatra must sum to the full nakshatra span,
    # so scanning a nakshatra yields sub-lords only from the 9 dasha lords.
    seen = set()
    lon = 0.0
    while lon < 360.0:
        kp = core.kp_lords(lon)
        assert kp["sub_lord"] in core.DASHA_SEQUENCE
        assert kp["star_lord"] in core.DASHA_SEQUENCE
        assert 1 <= kp["sign_num"] <= 12
        seen.add(kp["sub_lord"])
        lon += 0.37
    assert seen == set(core.DASHA_SEQUENCE)  # every planet appears as a sub-lord


def test_kp_cli_structure_and_day_lord():
    r = _run("kp.py", ("--ayanamsa", "lahiri"))
    assert len(r["cuspal_sub_lords"]) == 12
    assert len(r["planets"]) == 9
    # 1990-08-15 14:30 (after sunrise) was a Wednesday -> day lord Mercury
    assert r["ruling_planets"]["day_lord"] == "Mercury"


def test_kp_day_lord_uses_sunrise_to_sunrise_vedic_day():
    # A birth BEFORE sunrise belongs to the previous Vedic weekday. 1990-08-15 is
    # a Wednesday (civil), so 02:00 is still Tuesday by the sunrise day -> Mars,
    # NOT Mercury. Guards against regressing to civil-weekday day-lord.
    cmd = [sys.executable, "kp.py", "--date", "1990-08-15", "--time", "02:00:00",
           "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata",
           "--ayanamsa", "lahiri", "--json"]
    p = subprocess.run(cmd, cwd=VEDIC, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["ruling_planets"]["day_lord"] == "Mars"


def test_transit_timeline_events_well_formed():
    r = _run("transit_timeline.py", ("--start", "2025-01-01", "--end", "2028-01-01"))
    evs = r["ingress_events"]
    assert len(evs) >= 4  # several slow-planet ingresses over 3 years
    dates = [e["date_local"] for e in evs]
    assert dates == sorted(dates)  # chronological
    for e in evs:
        assert 1 <= e["house_from_moon"] <= 12
        assert e["planet"] in ("Jupiter", "Saturn", "Rahu", "Ketu")


def test_av_transit_scores_in_range():
    r = _run("av_transit.py", ("--on", "2026-06-15"))
    assert r["natal_sav_total"] == 337
    for t in r["transits"]:
        assert 0 <= t["sav_bindu"] <= 56  # SAV per-sign bounds
        assert t["rating"] in ("supportive (high SAV)", "strained (low SAV)", "mixed")


def test_verify_isolates_moon_parallax():
    r = _run("verify.py")
    pos = {p["planet"]: p for p in r["positions"]}
    assert len(r["positions"]) == 9  # no duplicate Ketu
    # Only the Moon should differ materially between topocentric and geocentric.
    assert pos["Moon"]["delta_arcmin"] > 10
    for name in ("Sun", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"):
        assert pos[name]["delta_arcmin"] < 1.0

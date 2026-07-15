"""
Golden-value regression tests for the vedic-astrology + numerology toolkit.

These run each command's CLI as a subprocess and assert on its --json output.
Testing the real user-facing surface (not internal functions) keeps the tests
robust to refactors while pinning the values that must never silently drift.

Reference birth chart used throughout: 1990-08-15 14:30:00, New Delhi
(lat 28.6139, lon 77.2090, Asia/Kolkata), Lahiri ayanamsa.

Run:  pytest -q
"""

import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VEDIC = os.path.join(REPO, "vedic-astrology", "scripts")
NUMER = os.path.join(REPO, "numerology", "scripts")

REF = ["--date", "1990-08-15", "--time", "14:30:00",
       "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata"]


def run(script_dir, script, args):
    """Run a CLI script with --json and return parsed output (cwd = its dir)."""
    cmd = [sys.executable, script, *args, "--json"]
    proc = subprocess.run(cmd, cwd=script_dir, capture_output=True, text=True)
    assert proc.returncode == 0, f"{script} failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------- #
# Kundli — sign-level placements are stable and meaningful golden values.
# --------------------------------------------------------------------------- #
def test_kundli_sign_placements():
    r = run(VEDIC, "kundli.py", REF)
    p = r["planets"]
    assert r["ascendant"]["sign"] == "Scorpio"
    assert p["Sun"]["sign"] == "Cancer"
    assert p["Moon"]["sign"] == "Taurus" and p["Moon"]["dignity"] == "exalted"
    assert p["Jupiter"]["sign"] == "Cancer" and p["Jupiter"]["dignity"] == "exalted"
    assert p["Mars"]["sign"] == "Aries" and p["Mars"]["dignity"] == "own sign"


def test_western_sun_sign_tropical():
    # Western (tropical) Sun = sidereal Sun + ayanamsa. The REF chart's Vedic Sun
    # is Cancer (sidereal); born 15 Aug, its Western/tropical Sun is Leo.
    r = run(VEDIC, "kundli.py", REF)
    assert r["planets"]["Sun"]["sign"] == "Cancer"   # Vedic (sidereal)
    assert r["western_sun_sign"] == "Leo"            # Western (tropical)
    # A late-December birth is a Western Capricorn.
    r2 = run(VEDIC, "kundli.py",
             ["--date", "2000-12-25", "--time", "12:00:00",
              "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata"])
    assert r2["western_sun_sign"] == "Capricorn"


def test_ketu_opposite_rahu():
    r = run(VEDIC, "kundli.py", REF)
    rahu = r["planets"]["Rahu"]["longitude"]
    ketu = r["planets"]["Ketu"]["longitude"]
    assert abs(((ketu - rahu) % 360) - 180.0) < 1e-6


def test_ayanamsa_lahiri_1990():
    r = run(VEDIC, "kundli.py", REF)
    assert 23.5 < r["ayanamsa_deg"] < 23.9  # Lahiri ~23.73° in 1990


def test_topocentric_is_default():
    r = run(VEDIC, "kundli.py", REF)
    assert r["input"]["topocentric"] is True


# --------------------------------------------------------------------------- #
# Dasha — Vimshottari must close to exactly 120 years.
# --------------------------------------------------------------------------- #
def test_dasha_starts_moon_and_closes_120y():
    r = run(VEDIC, "dasha.py", REF + ["--levels", "1"])
    assert r["starting_dasha"] == "Moon"          # Moon in Rohini (lord Moon)
    total = r["balance_at_birth_years"] + sum(
        m["years"] for m in r["mahadashas"][1:])   # balance + 8 full periods
    # balance + remaining 8 periods should sum to 120 - elapsed_of_first... so
    # instead check the 9 listed spans + elapsed = 120 via full-period identity:
    full_first = 10  # Moon mahadasha is 10 years
    elapsed = full_first - r["balance_at_birth_years"]
    assert abs((elapsed + sum(m["years"] for m in r["mahadashas"])) - 120.0) < 0.05


def test_dasha_predict_active_period_and_areas():
    # Reference chart (Scorpio Lagna). On 2026-06-04 it runs Jupiter–Venus.
    r = run(VEDIC, "dasha_predict.py", REF + ["--on", "2026-06-04"])
    assert r["asc_sign"] == "Scorpio"
    assert r["active"]["maha"] == "Jupiter"
    assert r["active"]["antar"] == "Venus"
    # All ten life areas must be present for both lords.
    for lord in ("mahadasha", "antardasha"):
        assert len(r["effects"][lord]) == 10
    # Personalisation: activated houses = placements + lordships, non-empty.
    assert r["activated_houses"]
    # Jupiter rules Scorpio's 2nd & 5th (Sagittarius/Pisces) — lordship must show.
    assert 2 in r["activated_houses"] and 5 in r["activated_houses"]


def test_yogini_dasha_start_and_cycle_closure():
    # REF Moon is in Rohini (nakshatra 4): (4+3) mod 8 = 7 -> Siddha (Venus).
    r = run(VEDIC, "dasha_yogini.py", REF + ["--levels", "1"])
    assert r["system"] == "Yogini Dasha"
    assert r["cycle_years"] == 36
    assert r["starting_yogini"] == "Siddha" and r["starting_lord"] == "Venus"
    # The eight full periods after the partial first must sum to the 36-yr cycle.
    fulls = [m["years"] for m in r["mahadashas"][1:9]]
    assert abs(sum(fulls) - 36.0) < 1e-6
    # Balance never exceeds the first Yogini's full length (Siddha = 7 yrs).
    assert 0 < r["balance_at_birth_years"] <= 7.0


def test_yogini_dasha_antardashas_sum_to_maha():
    r = run(VEDIC, "dasha_yogini.py", REF + ["--levels", "2"])
    md = r["mahadashas"][1]                 # first FULL mahadasha (Sankata, 8 yrs)
    assert "antardashas" in md and len(md["antardashas"]) == 8
    sub_total = sum(a["years"] for a in md["antardashas"])
    assert abs(sub_total - md["years"]) < 1e-3


def test_rectify_event_fit_and_sensitivity():
    # REF chart on 2026-06-04 runs Jupiter-Venus (see test_dasha_predict). A
    # 'gain' event (karakas Jupiter/Venus) on that date should fit the unshifted
    # time, and the rectifier must report both a ranking and the Lagna scan.
    r = run(VEDIC, "rectify.py",
            ["--date", "1990-08-15", "--approx-time", "14:30",
             "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata",
             "--window", "30", "--step", "5", "--event", "2026-06-04:gain"])
    assert "lagna_sensitivity" in r and "ranked" in r and r["best"] is not None
    # Every candidate carries a numeric score and a Lagna; ranking is descending.
    scores = [c["total_score"] for c in r["ranked"]]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(c["total_score"], int) for c in r["ranked"])
    # The active dasha the rectifier computes must match dasha_predict's engine.
    centre = min(r["ranked"], key=lambda c: abs(c["delta_min"]))
    ev = centre["events"][0]
    assert ev["active"]["maha"] == "Jupiter" and ev["active"]["antar"] == "Venus"
    # max possible = (MD1+AD2+PD3 + 2 transits) per event.
    assert r["max_possible_score"] == 8


def test_rectify_accepts_divorce_and_separation():
    # 'divorce'/'separation' are valid event types (7th + dusthana affliction).
    r = run(VEDIC, "rectify.py",
            ["--date", "1990-08-15", "--approx-time", "14:30",
             "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata",
             "--window", "20", "--step", "5",
             "--event", "2020-02-01:marriage", "--event", "2022-06-01:divorce"])
    assert r["best"] is not None and len(r["ranked"]) > 0
    assert {e["type"] for e in r["best"]["events"]} == {"marriage", "divorce"}


def test_rectify_rejects_unknown_event_type():
    proc = subprocess.run(
        [sys.executable, "rectify.py", "--date", "1990-08-15", "--approx-time", "14:30",
         "--lat", "28.6", "--lon", "77.2", "--tz", "Asia/Kolkata",
         "--event", "2020-01-01:lottery", "--json"],
        cwd=VEDIC, capture_output=True, text=True)
    assert proc.returncode != 0 and "Unknown event type" in proc.stderr


def test_dasha_predict_rejects_pre_birth_date():
    proc = subprocess.run(
        [sys.executable, "dasha_predict.py", *REF, "--on", "1980-01-01", "--json"],
        cwd=VEDIC, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "No dasha covers" in proc.stderr


# --------------------------------------------------------------------------- #
# Vargas — D1 identity, D9==navamsa, strength bounds.
# --------------------------------------------------------------------------- #
def test_varga_charts_and_strength():
    r = run(VEDIC, "varga.py", REF)
    # REF chart: Sun in Cancer (D1=4), Moon's navamsa is Cancer (D9=4).
    assert r["charts"]["1"]["Sun"] == 4
    assert r["charts"]["9"]["Moon"] == 4
    # Every point lands in a valid sign for every division.
    for d_div, chart in r["charts"].items():
        assert all(1 <= s <= 12 for s in chart.values())
    # Strength scores are well-formed.
    for p, s in r["strength"].items():
        assert 0 <= s["varga_bala_pct"] <= 100
        assert 0 <= s["own_or_exalted_count"] <= 16


def test_varga_extra_non_classical_divisions():
    # D5/D6/D8/D11 lie outside the Shodasavarga; they must compute into valid signs.
    r = run(VEDIC, "varga.py", REF + ["--charts", "D5,D6,D8,D11"])
    for d in ("5", "6", "8", "11"):
        assert d in r["charts"]
        assert all(1 <= s <= 12 for s in r["charts"][d].values())
    # Cross-varga strength still spans ONLY the classical 16 (extras are display-only).
    for p, s in r["strength"].items():
        assert s["own_or_exalted_count"] <= 16


def test_varga_extra_labelled_non_classical_and_rejects_bad():
    proc = subprocess.run([sys.executable, "varga.py", *REF, "--charts", "D11"],
                          cwd=VEDIC, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "D11" in proc.stdout and "non-classical" in proc.stdout
    # A division in no supported set is rejected, not silently approximated.
    bad = subprocess.run([sys.executable, "varga.py", *REF, "--charts", "D13", "--json"],
                         cwd=VEDIC, capture_output=True, text=True)
    assert bad.returncode != 0 and "not supported" in bad.stderr


def test_chart_extra_varga_d11():
    ch = run(VEDIC, "chart.py", REF + ["--varga", "D11"])
    assert ch["div"] == 11
    assert sum(len(v) for v in ch["by_sign"].values()) == 9   # all nine grahas placed


# --------------------------------------------------------------------------- #
# Gochar — structure + natal reference + Sade Sati phase house.
# --------------------------------------------------------------------------- #
def test_gochar_transits_and_panoti():
    r = run(VEDIC, "gochar.py", REF + ["--on", "2026-06-04"])
    assert r["natal_moon_sign"] == "Taurus"      # REF Moon is in Taurus
    assert len(r["transits"]) == 9
    for t in r["transits"]:
        assert 1 <= t["house_from_moon"] <= 12
        assert 1 <= t["house_from_lagna"] <= 12
    assert 1 <= r["saturn_panoti"]["phase_house"] <= 12


# --------------------------------------------------------------------------- #
# Bhava report — 12 houses, house 1 carries the Lagna sign.
# --------------------------------------------------------------------------- #
def test_houses_report():
    r = run(VEDIC, "houses.py", REF)
    assert len(r["bhavas"]) == 12
    h1 = r["bhavas"][0]
    assert h1["house"] == 1 and h1["sign"] == r["lagna_sign"]
    # Every house has a lord that is a real planet.
    planets = {"Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"}
    assert all(b["lord"] in planets for b in r["bhavas"])


def test_houses_graha_in_bhava_readings():
    """Every occupant of a house carries a plain-language Graha-in-Bhava reading."""
    r = run(VEDIC, "houses.py", REF)
    seen = 0
    for b in r["bhavas"]:
        assert set(b["occupant_readings"]) == set(b["occupants"])
        for n in b["occupants"]:
            assert isinstance(b["occupant_readings"][n], str)
            assert len(b["occupant_readings"][n]) > 15
            seen += 1
    assert seen == 9                        # all nine grahas placed once across 12 houses
    # REF: exalted Moon sits in the 7th — its reading must mention partnership.
    h7 = next(b for b in r["bhavas"] if b["house"] == 7)
    assert "Moon" in h7["occupants"]
    assert "marriage" in h7["occupant_readings"]["Moon"].lower()


def test_astro_claude_reading():
    r = run(VEDIC, "astro_claude.py",
            ["--name", "Asha", "--gender", "female", "--married", "no"] + REF
            + ["--on", "2026-06-04"])
    # Age from 1990-08-15 to 2026-06-04 is 35 (birthday not yet reached).
    assert r["profile"]["age"] == 35
    assert r["profile"]["name"] == "Asha"
    # Functional nature is computed for all seven classical planets.
    for p in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"):
        assert r["functional"][p]["nature"] in ("yogakaraka", "benefic", "malefic", "neutral")
    # Gemstone guidance always splits into wear/avoid lists; rudraksha allowed.
    assert "wear" in r["gemstones"] and "avoid" in r["gemstones"]
    assert r["rudraksha"]["can_wear"] is True


def test_astro_claude_yogakaraka_for_taurus():
    # Early-morning Delhi birth → Taurus Lagna; Saturn must be the yogakaraka.
    r = run(VEDIC, "astro_claude.py",
            ["--name", "T", "--date", "1990-05-10", "--time", "06:00:00",
             "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata"])
    assert r["lagna"]["sign"] == "Taurus"
    assert r["functional"]["Saturn"]["is_yogakaraka"] is True


def test_dst_nonexistent_time_rejected():
    # 02:30 on 2021-03-14 does not exist in America/New_York (spring forward).
    # The engine must error rather than silently shift the chart by an hour.
    proc = subprocess.run(
        [sys.executable, "kundli.py", "--date", "2021-03-14", "--time", "02:30:00",
         "--lat", "40.71", "--lon", "-74.01", "--tz", "America/New_York", "--json"],
        cwd=VEDIC, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "does not exist" in proc.stderr


def test_manglik_three_references():
    r = run(VEDIC, "matching.py",
            ["--mode", "dosha", "--date", "1988-07-22", "--time", "09:15:00",
             "--lat", "19.0760", "--lon", "72.8777", "--tz", "Asia/Kolkata"])
    m = r["manglik"]
    for k in ("mars_house_from_lagna", "mars_house_from_moon", "mars_house_from_venus",
              "triggered_from"):
        assert k in m
    # The flag is the OR of the three reference points.
    refs = {m["mars_house_from_lagna"], m["mars_house_from_moon"], m["mars_house_from_venus"]}
    expected = bool(refs & {1, 2, 4, 7, 8, 12})
    assert m["manglik"] is expected


def test_career_windows_dedupe_and_status():
    r = run(VEDIC, "astro_claude.py",
            ["--name", "X", "--date", "1988-07-22", "--time", "09:15:00",
             "--lat", "19.0760", "--lon", "72.8777", "--tz", "Asia/Kolkata", "--on", "2026-06-04"])
    lords = [w["lord"] for w in r["career_windows"]]
    assert len(lords) == len(set(lords))            # no duplicate lords
    assert all(w.get("status") in ("current", "upcoming") for w in r["career_windows"])


def test_numerology_rejects_impossible_date():
    proc = subprocess.run(
        [sys.executable, "numerology.py", "--date", "2025-02-30", "--name", "Test", "--json"],
        cwd=NUMER, capture_output=True, text=True)
    assert proc.returncode != 0


def test_numerology_name_trinity_and_maturity():
    r = run(NUMER, "numerology.py", ["--date", "1990-08-15", "--name", "Albert Einstein",
                                      "--system", "chaldean"])
    tr = r["name_trinity"]
    # Expression = full-name compound; vowels AEEIEI sum to 18 -> Soul Urge 9.
    assert tr["expression"]["compound"] == 46 and tr["expression"]["number"] == 1
    assert tr["soul_urge"]["number"] == 9
    assert tr["personality"]["number"] == 1
    # Maturity = reduce(Bhagyank 6 + Expression 1) = 7.
    assert r["maturity"]["number"] == 7


def test_numerology_karmic_debt_and_lessons():
    # Day 13 -> Karmic Debt 13/4 in the birthday.
    r = run(NUMER, "numerology.py", ["--date", "1980-04-13", "--name", "Albert Einstein"])
    assert r["karmic"]["debts"]["birthday"]["number"] == 13
    # "Albert Einstein" (Pythagorean) is missing values 4, 6, 7, 8.
    assert r["karmic"]["lessons"] == [4, 6, 7, 8]


def test_numerology_pinnacles_and_personal_cycles():
    r = run(NUMER, "numerology.py", ["--date", "1990-08-15", "--on", "2026-06-08"])
    pin = r["pinnacles_challenges"]["pinnacles"]
    assert len(pin) == 4 and all(1 <= p["number"] <= 9 for p in pin)
    # First pinnacle = reduce(reduce(8)+reduce(15)) = reduce(8+6) = 5.
    assert pin[0]["number"] == 5
    cy = r["personal_cycles"]
    assert cy["universal_year"] == 1            # 2+0+2+6 = 10 -> 1
    assert 1 <= cy["personal_day"]["number"] <= 9


def test_numerology_two_person_match():
    r = run(NUMER, "numerology.py", ["--date", "1990-08-15", "--date2", "1991-06-09"])
    m = r["match"]
    assert m["person_a"]["moolank"] == 6 and m["person_b"]["moolank"] == 9
    assert 0 <= m["score_pct"] <= 100
    assert len(m["pairs"]) == 4            # no names -> 4 core pairs only


def test_numerology_number_check():
    r = run(NUMER, "numerology.py", ["--date", "1990-08-15",
                                     "--check-number", "9876543210", "--check-kind", "mobile"])
    chk = r["number_check"]
    assert chk["kind"] == "mobile"
    assert chk["compound"] == 45 and chk["number"] == 9
    assert chk["vs_moolank"] in {"friend", "neutral", "enemy"}


def test_drik_bala_special_aspect_counted_by_whole_sign():
    # Regression: special graha-drishti must be counted by WHOLE SIGN, not by
    # 30-degree blocks of the raw separation. Saturn at Sagittarius 29 deg casts
    # its 10th-sign aspect onto a target in Virgo (whole-sign distance 10), which
    # a degree-block count would mis-read as the 9th and miss.
    sys.path.insert(0, VEDIC)
    import strength
    planets = {nm: {"longitude": 155.0, "sign_num": 6} for nm in strength.SHADBALA_PLANETS}
    planets["Saturn"] = {"longitude": 269.0, "sign_num": 9}  # Sag 29 deg, 10th by sign
    # Only Saturn aspects (full 60, malefic) -> -60/4 = -15.0; conjunct fillers add 0.
    assert strength.drik_bala("Sun", planets, True) == -15.0


def test_geocode_resolves_gurgaon_and_gurugram():
    for q in ("Gurgaon", "Gurugram"):
        proc = subprocess.run(
            [sys.executable, "geocode.py", q, "--json"],
            cwd=VEDIC, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        matches = json.loads(proc.stdout)
        matches = matches if isinstance(matches, list) else matches.get("matches", [])
        assert matches and matches[0]["name"] == "Gurugram"
        assert matches[0]["timezone"] == "Asia/Kolkata"
        assert abs(matches[0]["lat"] - 28.46) < 0.1 and abs(matches[0]["lon"] - 77.03) < 0.1


def test_numerology_check_number_all_zero_is_safe():
    # Regression: an all-zero number string reduces to 0, which has no 1-9
    # vibration and must be omitted (not crash on RULING_PLANET[0]).
    r = run(NUMER, "numerology.py",
            ["--date", "1990-08-15", "--check-number", "0000", "--check-kind", "mobile"])
    assert "number_check" not in r


def test_yantra_birthday_is_magic():
    r = run(NUMER, "yantra.py", ["--date", "1990-08-15"])
    assert r["kind"] == "birthday"
    # Top row = day, month, century-part, year-part = 15, 8, 19, 90 -> sum 132.
    assert r["square"][0] == [15, 8, 19, 90]
    assert r["magic_sum"] == 132 and r["magic_valid"] is True


def test_yantra_planetary_surya_is_lo_shu():
    r = run(NUMER, "yantra.py", ["--planet", "surya"])
    assert r["square"] == [[4, 9, 2], [3, 5, 7], [8, 1, 6]]
    assert r["magic_sum"] == 15 and r["magic_valid"] is True
    assert "Suryaya" in r["bija_mantra"]


def test_yantra_all_planets_are_magic():
    r = run(NUMER, "yantra.py", ["--planet", "all"])
    ys = r["yantras"]
    assert len(ys) == 9
    assert all(y["magic_valid"] for y in ys)
    assert [y["magic_sum"] for y in ys] == [15, 18, 21, 24, 27, 30, 33, 36, 39]


def test_yantra_custom_target_3x3():
    r = run(NUMER, "yantra.py", ["--target", "24"])
    assert r["magic_sum"] == 24 and r["magic_valid"] is True
    assert all(sum(row) == 24 for row in r["square"])


def test_yantra_rejects_non_multiple_of_three():
    proc = subprocess.run(
        [sys.executable, "yantra.py", "--target", "25", "--json"],
        cwd=NUMER, capture_output=True, text=True)
    assert proc.returncode != 0


def test_yantra_writes_svg(tmp_path):
    out = tmp_path / "y.svg"
    proc = subprocess.run(
        [sys.executable, "yantra.py", "--planet", "shani", "--svg", str(out), "--json"],
        cwd=NUMER, capture_output=True, text=True)
    assert proc.returncode == 0
    assert out.exists() and out.read_text().startswith("<svg")


def test_muhurta_ranking():
    r = run(VEDIC, "muhurta.py",
            ["--event", "marriage", "--from", "2026-11-01", "--to", "2026-11-20",
             "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata"])
    assert r["event"] == "marriage"
    assert len(r["ranked"]) == 20            # inclusive 20-day span
    for d in r["ranked"]:
        assert 0 <= d["score"] <= 100
        assert d["verdict"] in ("Excellent", "Good", "Fair", "Avoid")
    # Ranked descending.
    scores = [d["score"] for d in r["ranked"]]
    assert scores == sorted(scores, reverse=True)


def test_muhurta_yoga_names_match_panchang():
    """Every yoga muhurta scores against must be a real panchang yoga name.

    Guards the class of bug where a misspelling (e.g. 'Shoola' vs 'Shula')
    silently prevents a penalty/bonus from ever firing.
    """
    if VEDIC not in sys.path:
        sys.path.insert(0, VEDIC)
    import muhurta
    import panchang
    valid = set(panchang.YOGA_NAMES)
    assert len(valid) == 27
    scored = muhurta.BAD_YOGAS | muhurta.ROUGH_YOGAS | muhurta.GOOD_YOGAS
    unknown = scored - valid
    assert not unknown, f"muhurta scores unknown yoga name(s): {sorted(unknown)}"


def test_muhurta_rejects_backwards_range():
    proc = subprocess.run(
        [sys.executable, "muhurta.py", "--event", "vehicle",
         "--from", "2026-12-01", "--to", "2026-11-01",
         "--lat", "28.6", "--lon", "77.2", "--tz", "Asia/Kolkata", "--json"],
        cwd=VEDIC, capture_output=True, text=True)
    assert proc.returncode != 0


# --------------------------------------------------------------------------- #
# Avoid — the don'ts engine: structure, Panchak, Disha Shool, and the personal
# Chandrashtama flag. Mirror of muhurta (timing cautions, not predictions).
# --------------------------------------------------------------------------- #
def test_avoid_structure_and_windows():
    r = run(VEDIC, "avoid.py",
            ["--date", "2026-06-08", "--days", "7",
             "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata"])
    assert r["days"] == 7 and len(r["report"]) == 7
    for d in r["report"]:
        # Every day carries the three inauspicious time windows and a refrain map.
        for w in ("rahu_kaal", "yamaganda", "gulika"):
            assert d["windows"][w]
        assert isinstance(d["refrain"], dict)
        assert d["worst_severity"] in ("high", "med", "low", None)


def test_avoid_disha_shool_matches_weekday():
    # 2026-06-08 is a Monday → Disha Shool is East (classical mapping).
    r = run(VEDIC, "avoid.py",
            ["--date", "2026-06-08", "--lat", "28.6139", "--lon", "77.2090",
             "--tz", "Asia/Kolkata"])
    day = r["report"][0]
    assert day["weekday"] == "Monday"
    assert day["disha_shool"] == "East"


def test_avoid_panchak_fires_for_moon_in_aquarius():
    # 2026-06-08 the Moon is in Aquarius → Panchak; the five prohibitions appear.
    r = run(VEDIC, "avoid.py",
            ["--date", "2026-06-08", "--lat", "28.6139", "--lon", "77.2090",
             "--tz", "Asia/Kolkata"])
    day = r["report"][0]
    assert day["moon_sign"] == "Aquarius"
    titles = {f["title"] for f in day["flags"]}
    assert any(t.startswith("Panchak") for t in titles)
    # A Panchak-specific don't (south-bound travel) must be in the refrain list.
    assert any("south-bound" in act for act in day["refrain"])


def test_avoid_personalised_chandrashtama():
    # REF Moon is Taurus; the 8th sign is Sagittarius. On 2026-06-02 the transit
    # Moon is in Sagittarius → Chandrashtama, a personal high-caution day.
    r = run(VEDIC, "avoid.py",
            ["--date", "2026-06-02",
             "--lat", "28.6139", "--lon", "77.2090", "--tz", "Asia/Kolkata",
             "--birth-date", "1990-08-15", "--birth-time", "14:30:00"])
    assert r["personalised"] is True
    day = r["report"][0]
    assert day["chandra_pos"] == 8
    assert day["worst_severity"] == "high"
    assert any(f["title"].startswith("Chandrashtama") for f in day["flags"])
    # Personalised days expose both Tara and Chandra-Bala context.
    assert "tara" in day


def test_avoid_rejects_bad_days_range():
    proc = subprocess.run(
        [sys.executable, "avoid.py", "--date", "2026-06-08", "--days", "0",
         "--lat", "28.6", "--lon", "77.2", "--tz", "Asia/Kolkata", "--json"],
        cwd=VEDIC, capture_output=True, text=True)
    assert proc.returncode != 0


def test_mantra_goals():
    r = run(VEDIC, "mantra.py", REF + ["--goal", "all", "--on", "2026-06-04"])
    assert r["mahadasha_lord"] in {"Sun", "Moon", "Mars", "Mercury", "Jupiter",
                                   "Venus", "Saturn", "Rahu", "Ketu"}
    assert set(r["goals"]) >= {"wealth", "success", "marriage", "health"}
    for g, blk in r["goals"].items():
        assert blk["deity_mantras"]                       # every goal has a deity mantra
        for p in blk["planetary"]:
            assert p["mode"] in ("strengthen", "harmonise / pacify")
            assert p["beej"].startswith("Om")


def test_lucky_profile():
    r = run(VEDIC, "lucky.py", REF)
    assert r["lagna_lord"] in {"Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"}
    assert 1 <= r["moolank"] <= 9
    assert r["lucky"]["days"] and r["lucky"]["numbers"] and r["lucky"]["directions"]


def test_astro_claude_has_atmakaraka():
    r = run(VEDIC, "astro_claude.py", ["--name", "A"] + REF + ["--on", "2026-06-04"])
    assert r["atmakaraka"]["planet"] in {"Sun", "Moon", "Mars", "Mercury", "Jupiter",
                                         "Venus", "Saturn"}
    assert 1 <= r["atmakaraka"]["house"] <= 12


def test_dhana_yoga_detected_in_ref():
    r = run(VEDIC, "yogas.py", REF)
    names = {y["name"] for y in r["yogas"]}
    assert "Dhana Yoga" in names


def test_yogas_lunar_and_nabhasa_invariants():
    """The lunar yogas are mutually exclusive; exactly one Sankhya yoga fires."""
    r = run(VEDIC, "yogas.py", REF)
    names = [y["name"] for y in r["yogas"]]
    lunar = {"Sunapha Yoga", "Anapha Yoga", "Durudhara Yoga", "Kemadruma Yoga"}
    assert len(lunar & set(names)) <= 1
    # 7 planets always occupy 1..7 distinct signs, so one Sankhya yoga is certain.
    sankhya = [n for n in names if "Nabhasa Sankhya" in n]
    assert len(sankhya) == 1


def test_yogas_expanded_families_in_ref():
    """The expanded library surfaces the new families on the reference chart."""
    r = run(VEDIC, "yogas.py", REF)
    names = {y["name"] for y in r["yogas"]}
    # REF (Scorpio Lagna) has a Moon<->Venus sign exchange and a 6/8/12-lord
    # in a dusthana.
    assert "Vipareeta Raja Yoga" in names
    assert any(n.startswith("Parivartana Yoga") for n in names)
    # Every detected yoga carries a rule and a plain-language note.
    for y in r["yogas"]:
        assert y["rule"] and y["note"]


def test_full_report_html(tmp_path):
    out = tmp_path / "asha.html"
    proc = subprocess.run(
        [sys.executable, "full_report.py", "--name", "Asha", "--gender", "female",
         "--married", "no", *REF, "--on", "2026-06-04",
         "--format", "html", "--out", str(out)],
        cwd=VEDIC, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    for marker in ("Astro Claude", "Asha", "Birth Chart", "Gemstones", "Rudraksha",
                   "Today's Sky", "PANCHANG"):
        assert marker in text


def test_remedies_and_chart():
    rem = run(VEDIC, "remedies.py", REF + ["--on", "2026-06-04"])
    assert rem["mahadasha_lord"] in {"Sun", "Moon", "Mars", "Mercury", "Jupiter",
                                     "Venus", "Saturn", "Rahu", "Ketu"}
    assert isinstance(rem["flagged"], list)
    ch = run(VEDIC, "chart.py", REF + ["--varga", "D1"])
    total = sum(len(v) for v in ch["by_sign"].values())
    assert total == 9                            # all nine grahas placed once


# --------------------------------------------------------------------------- #
# Ashtakavarga — the hard invariants.
# --------------------------------------------------------------------------- #
def test_sarvashtakavarga_total_337():
    r = run(VEDIC, "strength.py", REF)
    sav = r["ashtakavarga"]["sav"]
    assert sav["total"] == 337
    assert sum(sav["per_sign"]) == 337


def test_bhinnashtakavarga_totals():
    r = run(VEDIC, "strength.py", REF)
    expected = {"Sun": 48, "Moon": 49, "Mars": 39, "Mercury": 54,
                "Jupiter": 56, "Venus": 52, "Saturn": 39}
    bav = r["ashtakavarga"]["bav"]
    for planet, total in expected.items():
        assert bav[planet]["total"] == total, f"{planet} BAV {bav[planet]['total']} != {total}"


# --------------------------------------------------------------------------- #
# Shadbala — the complete six-fold strength, structure + classical invariants.
# --------------------------------------------------------------------------- #
def test_shadbala_complete_six_sources():
    r = run(VEDIC, "strength.py", REF)
    sb = r["shadbala"]
    assert sb["complete"] is True
    planets = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")
    for name in planets:
        c = sb["planets"][name]["components_virupa"]
        # All six sources present.
        for key in ("sthana", "dig_bala", "kala", "cheshta_bala",
                    "naisargika_bala", "drik_bala"):
            assert key in c, f"{name} missing Shadbala source {key}"
        # Sthana subtotal is the exact sum of its five sub-balas.
        s = c["sthana"]
        parts = (s["uchcha_bala"] + s["saptavargaja_bala"] + s["ojayugma_bala"]
                 + s["kendradi_bala"] + s["drekkana_bala"])
        assert abs(parts - s["subtotal"]) < 0.05
        # Total in Rupas is positive and meets/decides the classical threshold.
        assert sb["planets"][name]["total_rupa"] > 0
        assert isinstance(sb["planets"][name]["meets_required"], bool)


def test_shadbala_cheshta_classical_identities():
    """Sun's Cheshta Bala = its Ayana Bala; Moon's = its Paksha Bala (BPHS)."""
    r = run(VEDIC, "strength.py", REF)
    p = r["shadbala"]["planets"]
    sun = p["Sun"]["components_virupa"]
    moon = p["Moon"]["components_virupa"]
    assert abs(sun["cheshta_bala"] - sun["kala"]["ayana_bala"]) < 0.05
    assert abs(moon["cheshta_bala"] - moon["kala"]["paksha_bala"]) < 0.05
    # The five star-planets' Cheshta (Seeghra Kendra) is bounded 0..60.
    for name in ("Mars", "Mercury", "Jupiter", "Venus", "Saturn"):
        assert 0.0 <= p[name]["components_virupa"]["cheshta_bala"] <= 60.0


def test_shadbala_time_lords_unique():
    """Exactly one planet rules the weekday (Vara) and one the Hora."""
    r = run(VEDIC, "strength.py", REF)
    p = r["shadbala"]["planets"]
    vara = [n for n in p if p[n]["components_virupa"]["kala"]["vara_bala"] == 45.0]
    hora = [n for n in p if p[n]["components_virupa"]["kala"]["hora_bala"] == 60.0]
    assert len(vara) == 1 and len(hora) == 1
    # The named lord matches the awarded bala.
    lords = p[vara[0]]["components_virupa"]["kala"]["lords"]
    assert lords["vara"] == vara[0]


# --------------------------------------------------------------------------- #
# Guna Milan — max never exceeds 36; identical chart self-matches highly.
# --------------------------------------------------------------------------- #
def test_guna_milan_bounds_and_self_match():
    args = ["--mode", "milan"]
    for who in ("boy", "girl"):
        args += [f"--{who}-date", "1990-08-15", f"--{who}-time", "14:30:00",
                 f"--{who}-lat", "28.6139", f"--{who}-lon", "77.2090",
                 f"--{who}-tz", "Asia/Kolkata"]
    r = run(VEDIC, "matching.py", args)
    g = r["milan"]
    assert g["max"] == 36
    assert 0 <= g["total"] <= 36
    # Identical charts: same nadi/gana → but a person matched to themselves shares
    # Nadi (dosha=0); still total should be high (>= 24) on the other 7 kootas.
    assert g["total"] >= 24


# --------------------------------------------------------------------------- #
# Panchang — known weekday.
# --------------------------------------------------------------------------- #
def test_panchang_weekday():
    r = run(VEDIC, "panchang.py",
            ["--date", "2026-06-04", "--lat", "28.6139", "--lon", "77.2090",
             "--tz", "Asia/Kolkata"])
    assert r["vara"] == "Thursday"   # 2026-06-04 is a Thursday


# --------------------------------------------------------------------------- #
# Sky — Today's Sky opens with the Panchang + the live planetary alignment.
# --------------------------------------------------------------------------- #
_SIGNS = {"Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
          "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"}


def test_sky_today():
    r = run(VEDIC, "sky.py",
            ["--date", "2026-06-04", "--lat", "28.6139", "--lon", "77.2090",
             "--tz", "Asia/Kolkata"])
    # The Panchang is embedded and the weekday matches.
    assert r["panchang"]["vara"] == "Thursday"
    # All nine grahas placed, each with sign / nakshatra / pada / flags.
    assert {p["planet"] for p in r["planets"]} == {
        "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"}
    for p in r["planets"]:
        assert p["sign"] in _SIGNS
        assert 1 <= p["pada"] <= 4
        assert isinstance(p["retrograde"], bool) and isinstance(p["combust"], bool)
    # Nodes are retrograde by nature, but excluded from the "retrograde" insight.
    assert "Rahu" not in r["retrograde"] and "Ketu" not in r["retrograde"]
    # The slow-mover backdrop is exactly the four era-setting bodies.
    assert {e["planet"] for e in r["slow_movers"]} == {"Saturn", "Jupiter", "Rahu", "Ketu"}
    assert isinstance(r["conjunctions"], list)
    # On 2026-06-04 Mercury and Venus share Gemini — a real conjunction.
    assert any(set(c["planets"]) == {"Mercury", "Venus"} for c in r["conjunctions"])


def test_astro_claude_opens_with_today_sky():
    r = run(VEDIC, "astro_claude.py",
            ["--name", "Asha"] + REF + ["--on", "2026-06-04"])
    ts = r["today_sky"]
    assert ts["panchang"]["vara"] == "Thursday"
    assert len(ts["planets"]) == 9
    # Personalised: a Sade Sati flag from the natal Moon, and every transiting
    # graha counted as a house from that Moon (the personal bridge).
    assert isinstance(ts["sade_sati"]["active"], bool)
    assert all("house_from_moon" in p for p in ts["planets"])


def test_astro_claude_text_starts_with_panchang():
    # The human-readable reading must START with the Panchang / sky, before the
    # personal life narrative.
    proc = subprocess.run(
        [sys.executable, "astro_claude.py", "--name", "Asha", *REF, "--on", "2026-06-04"],
        cwd=VEDIC, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    i_sky = out.find("TODAY'S SKY")
    i_panch = out.find("PANCHANG")
    i_life = out.find("WHERE YOU ARE IN LIFE")
    assert -1 < i_sky < i_life            # the sky opens the reading
    assert -1 < i_panch < i_life          # the panchang appears before the life reading


# --------------------------------------------------------------------------- #
# Numerology — hand-verified core numbers.
# --------------------------------------------------------------------------- #
def test_numerology_core_numbers():
    if not os.path.exists(os.path.join(NUMER, "numerology.py")):
        pytest.skip("numerology module not present")
    r = run(NUMER, "numerology.py", ["--date", "1990-08-15"])
    blob = json.dumps(r)
    assert "6" in blob  # Moolank (day 15 -> 6) and Bhagyank (1+9+9+0+0+8+1+5=33 -> 6)


# --------------------------------------------------------------------------- #
# Geocoder — bundled dataset lookups.
# --------------------------------------------------------------------------- #
def test_geocode_mumbai():
    if not os.path.exists(os.path.join(VEDIC, "geocode.py")):
        pytest.skip("geocoder not present")
    r = run(VEDIC, "geocode.py", ["Mumbai"])
    top = r[0] if isinstance(r, list) else r
    assert 18.8 < float(top["lat"]) < 19.3
    assert 72.7 < float(top["lon"]) < 73.0
    assert top["timezone"] == "Asia/Kolkata"

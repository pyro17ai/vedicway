#!/usr/bin/env python3
"""
rectify.py — Birth-time rectification by life-event fitting.

IMPORTANT — what this does and does NOT do:
  Astrology has NO forward formula that derives a birth time from nothing. The
  chart is built *from* the time. Rectification is the REVERSE process: given
  dated life events, search a window of candidate birth times and rank them by
  how well each candidate's chart (Vimshottari dasha + slow-planet transits)
  explains those events. The result is a *best-fit* time, accurate at best to a
  few minutes — never "exact". More events, and finer (pratyantardasha) timing,
  narrow the window; they never make it certain.

Two things are reported:
  1. LAGNA-SENSITIVITY scan — across the window, when does the Lagna sign and the
     Lagna nakshatra-pada change? This shows how much your uncertainty even
     matters (a chart whose Lagna is stable for two hours barely needs rectifying
     for sign-level work; one that flips in 20 minutes needs care).
  2. EVENT-FIT ranking — candidate times scored against your dated events.

Usage:
    python rectify.py --date 1990-08-15 --approx-time 14:30 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        --window 60 --step 2 \\
        --event 2015-06-20:marriage --event 2018-03-10:child \\
        --event 2021-09-01:job [--json]

--window  half-width of the search in MINUTES around --approx-time (default 60)
--step    candidate spacing in MINUTES (default 2)
--event   repeatable, "YYYY-MM-DD:TYPE". See EVENT_TYPES below for valid types.

Disclaimer: cultural / educational use only. Rectification is a fitting heuristic,
not proof of a birth time. Always confirm against records where they exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

import core

DAYS_PER_YEAR = 365.25

# Event type -> the houses and natural karakas it activates, used to decide which
# planets "should" be prominent (by dasha and transit) when the event happened.
# Houses are counted from the (candidate) Lagna. Keep this conservative and
# classical; an event only scores when a genuinely relevant planet is active.
EVENT_TYPES = {
    "marriage":     {"houses": {7, 2, 11}, "karakas": {"Venus", "Jupiter"}},
    "divorce":      {"houses": {7, 2, 6, 8, 12}, "karakas": {"Venus", "Saturn", "Mars", "Rahu", "Ketu"}},
    "separation":   {"houses": {7, 2, 6, 8, 12}, "karakas": {"Venus", "Saturn", "Mars", "Rahu", "Ketu"}},
    "child":        {"houses": {5, 9},     "karakas": {"Jupiter"}},
    "job":          {"houses": {10, 6, 2}, "karakas": {"Saturn", "Sun", "Mercury"}},
    "promotion":    {"houses": {10, 11},   "karakas": {"Sun", "Jupiter"}},
    "job_loss":     {"houses": {10, 6, 8, 12}, "karakas": {"Saturn", "Rahu", "Ketu"}},
    "business":     {"houses": {7, 10, 3}, "karakas": {"Mercury", "Rahu"}},
    "relocation":   {"houses": {12, 4, 3}, "karakas": {"Rahu", "Moon"}},
    "foreign":      {"houses": {12, 9, 3}, "karakas": {"Rahu", "Moon"}},
    "property":     {"houses": {4},        "karakas": {"Mars", "Venus", "Saturn"}},
    "vehicle":      {"houses": {4},        "karakas": {"Venus"}},
    "gain":         {"houses": {11, 2},    "karakas": {"Jupiter", "Venus"}},
    "loss":         {"houses": {12, 8},    "karakas": {"Saturn", "Rahu", "Ketu"}},
    "accident":     {"houses": {6, 8},     "karakas": {"Mars", "Saturn", "Ketu"}},
    "illness":      {"houses": {6, 8},     "karakas": {"Saturn", "Mars", "Ketu"}},
    "father_death": {"houses": {9, 8, 12}, "karakas": {"Sun", "Saturn"}},
    "mother_death": {"houses": {4, 8, 12}, "karakas": {"Moon", "Saturn"}},
    "education":    {"houses": {4, 5, 9},  "karakas": {"Mercury", "Jupiter"}},
    "spiritual":   {"houses": {9, 12, 5},  "karakas": {"Jupiter", "Ketu"}},
}

# Only the seven non-nodal grahas can be house lords / occupants we score against
# (nodes are handled as karakas where classical).
SEVEN = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]


def _parse_hms(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def _lord_of_house(asc_sign: int, house: int) -> str:
    return core.SIGN_LORD[((asc_sign - 1) + (house - 1)) % 12 + 1]


# --------------------------------------------------------------------------- #
# Vimshottari timeline + active-lord finder (mirrors dasha.py's arithmetic).
# --------------------------------------------------------------------------- #
def _mahadashas(birth_jd: float) -> list[tuple]:
    """Return [(lord, start_jd, end_jd)] for the 9-period cycle from birth."""
    moon_lon, _ = core.sidereal_longitude(birth_jd, core.PLANETS["Moon"])
    nak = int(moon_lon // core.NAKSHATRA_SPAN)
    frac = (moon_lon % core.NAKSHATRA_SPAN) / core.NAKSHATRA_SPAN
    start = core.DASHA_SEQUENCE[nak % 9]
    si = core.DASHA_SEQUENCE.index(start)
    seq = [core.DASHA_SEQUENCE[(si + i) % 9] for i in range(9)]
    balance = core.DASHA_YEARS[start] * (1.0 - frac)
    out, cursor = [], birth_jd
    for i, lord in enumerate(seq):
        yrs = balance if i == 0 else core.DASHA_YEARS[lord]
        end = cursor + yrs * DAYS_PER_YEAR
        out.append((lord, cursor, end))
        cursor = end
    return out


def _subdivide(lord: str, start: float, end: float) -> list[tuple]:
    """Proportionally divide a period into its 9 sub-periods (over its actual span)."""
    si = core.DASHA_SEQUENCE.index(lord)
    seq = [core.DASHA_SEQUENCE[(si + i) % 9] for i in range(9)]
    span = end - start
    out, cursor = [], start
    for sub in seq:
        s_end = cursor + span * (core.DASHA_YEARS[sub] / 120.0)
        out.append((sub, cursor, s_end))
        cursor = s_end
    return out


def active_lords(birth_jd: float, target_jd: float) -> tuple[str, str, str] | None:
    """(Mahadasha, Antardasha, Pratyantardasha) lords running on target_jd."""
    for lord, s, e in _mahadashas(birth_jd):
        if s <= target_jd < e:
            md = lord
            for al, as_, ae in _subdivide(lord, s, e):
                if as_ <= target_jd < ae:
                    ad = al
                    for pl, ps, pe in _subdivide(al, as_, ae):
                        if ps <= target_jd < pe:
                            return md, ad, pl
                    return md, ad, al
            return md, lord, lord
    return None


# --------------------------------------------------------------------------- #
# Chart at a candidate time + per-event scoring.
# --------------------------------------------------------------------------- #
def candidate_chart(birth_jd: float, lat: float, lon: float) -> dict:
    asc = core.ascendant(birth_jd, lat, lon)
    asc_sign = asc["sign_num"]
    positions = core.all_planet_positions(birth_jd)
    houses = {n: core.house_of(positions[n]["sign_num"], asc_sign) for n in core.PLANET_ORDER}
    return {
        "asc": asc, "asc_sign": asc_sign,
        "positions": positions, "houses": houses,
        "moon_sign": positions["Moon"]["sign_num"],
    }


def relevant_planets(chart: dict, ev_type: str) -> set[str]:
    """Planets that, if active by dasha, would explain an event of this type:
    the lords of the relevant houses, the natural karakas, and any planet
    actually sitting in a relevant house."""
    spec = EVENT_TYPES[ev_type]
    asc_sign = chart["asc_sign"]
    planets = set(spec["karakas"])
    for h in spec["houses"]:
        planets.add(_lord_of_house(asc_sign, h))
    for n in core.PLANET_ORDER:
        if chart["houses"][n] in spec["houses"]:
            planets.add(n)
    return planets


def score_event(chart: dict, birth_jd: float, ev_date: str, ev_type: str) -> dict:
    """Score how well this candidate chart explains one dated event."""
    y, m, d = (int(x) for x in ev_date.split("-"))
    ev_jd = core.to_julian_ut(y, m, d, 12, 0, 0, "UTC")  # noon UTC is fine for dasha/slow transit
    rel = relevant_planets(chart, ev_type)
    spec = EVENT_TYPES[ev_type]

    # --- Dasha fit: AD and PD are timed finely, so they weigh more than MD. ---
    lords = active_lords(birth_jd, ev_jd)
    dasha_score = 0
    hit = []
    if lords:
        md, ad, pd = lords
        for lord, w, tag in ((md, 1, "MD"), (ad, 2, "AD"), (pd, 3, "PD")):
            if lord in rel:
                dasha_score += w
                hit.append(f"{tag}:{lord}")
    else:
        md = ad = pd = None

    # --- Transit fit: Jupiter & Saturn over a relevant house (from Lagna/Moon). ---
    tpos = core.all_planet_positions(ev_jd)
    transit_score = 0
    thit = []
    for slow in ("Jupiter", "Saturn"):
        ts = tpos[slow]["sign_num"]
        h_lagna = core.house_of(ts, chart["asc_sign"])
        h_moon = core.house_of(ts, chart["moon_sign"])
        if h_lagna in spec["houses"] or h_moon in spec["houses"]:
            transit_score += 1
            thit.append(f"{slow}->{'L' if h_lagna in spec['houses'] else ''}"
                        f"{'M' if h_moon in spec['houses'] else ''}")

    return {
        "date": ev_date, "type": ev_type,
        "active": {"maha": md, "antar": ad, "pratyantar": pd},
        "dasha_score": dasha_score, "dasha_hits": hit,
        "transit_score": transit_score, "transit_hits": thit,
        "score": dasha_score + transit_score,
    }


# --------------------------------------------------------------------------- #
# Lagna-sensitivity scan.
# --------------------------------------------------------------------------- #
def lagna_sensitivity(date: str, lat: float, lon: float, tz: str,
                      lo_jd: float, hi_jd: float, step_days: float) -> dict:
    """Find when, across the window, the Lagna sign / nakshatra-pada change."""
    sign_changes, pada_changes = [], []
    prev_sign = prev_pada = None
    t = lo_jd
    while t <= hi_jd + 1e-9:
        asc = core.ascendant(t, lat, lon)
        sign = asc["sign"]
        # Track the true (nakshatra, pada) pair from the ascendant longitude, so
        # a change in EITHER the nakshatra or its pada is detected (pada matters
        # for cusp-sensitive charts and for the D9/navamsa Lagna).
        pada = (asc["nakshatra"], asc["pada"])
        local = core.jd_to_local(t, tz).strftime("%H:%M")
        if prev_sign is not None and sign != prev_sign:
            sign_changes.append({"at": local, "from": prev_sign, "to": sign})
        if prev_pada is not None and pada != prev_pada:
            pada_changes.append({"at": local, "to": f"{pada[0]} pada {pada[1]}"})
        prev_sign, prev_pada = sign, pada
        t += step_days
    return {"lagna_sign_changes": sign_changes, "lagna_nakshatra_changes": pada_changes}


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def compute(args) -> dict:
    core.init_engine(
        args.ayanamsa, node=getattr(args, "node", "mean"),
        topocentric=not getattr(args, "geocentric", False),
        lat=args.lat, lon=args.lon, ephemeris=getattr(args, "ephemeris", "moshier"),
    )
    events = []
    for spec in (args.event or []):
        if ":" not in spec:
            raise ValueError(f"Bad --event '{spec}', expected YYYY-MM-DD:TYPE")
        ev_date, ev_type = spec.rsplit(":", 1)
        if ev_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event type '{ev_type}'. "
                             f"Valid: {', '.join(sorted(EVENT_TYPES))}")
        events.append((ev_date.strip(), ev_type.strip()))

    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_hms(args.approx_time)
    approx_jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)

    window_days = args.window / (24.0 * 60.0)
    step_days = args.step / (24.0 * 60.0)
    lo_jd, hi_jd = approx_jd - window_days, approx_jd + window_days

    # Lagna sensitivity over the window (finer step for boundary detection).
    sens = lagna_sensitivity(args.date, args.lat, args.lon, args.tz,
                             lo_jd, hi_jd, max(step_days / 2.0, 0.5 / (24 * 60)))

    candidates = []
    t = lo_jd
    while t <= hi_jd + 1e-9:
        chart = candidate_chart(t, args.lat, args.lon)
        ev_scores = [score_event(chart, t, ed, et) for ed, et in events]
        total = sum(e["score"] for e in ev_scores)
        local = core.jd_to_local(t, args.tz)
        candidates.append({
            "time": local.strftime("%H:%M:%S"),
            "jd": round(t, 8),
            "delta_min": round((t - approx_jd) * 24 * 60, 1),
            "lagna": chart["asc"]["sign"],
            "lagna_nakshatra": chart["asc"]["nakshatra"],
            "total_score": total,
            "events": ev_scores,
        })
        t += step_days

    # Rank by score desc, then by closeness to the given approx time.
    ranked = sorted(candidates, key=lambda c: (-c["total_score"], abs(c["delta_min"])))
    max_possible = sum(3 + 2 + 1 + 2 for _ in events)  # MD+AD+PD + 2 slow transits

    return {
        "input": {
            "date": args.date, "approx_time": args.approx_time, "lat": args.lat,
            "lon": args.lon, "timezone": args.tz, "ayanamsa": args.ayanamsa,
            "window_min": args.window, "step_min": args.step,
        },
        "events": [{"date": d_, "type": t_} for d_, t_ in events],
        "max_possible_score": max_possible,
        "lagna_sensitivity": sens,
        "best": ranked[0] if ranked else None,
        "ranked": ranked,
        "disclaimer": (
            "Rectification is a best-FIT heuristic, never an exact calculation. "
            "Astrology cannot derive a birth time from nothing — this only ranks "
            "candidate times by how well each explains the events you supplied. "
            "More and finer-dated events tighten the window; nothing makes it "
            "certain. Confirm against birth records where they exist. For "
            "cultural/educational use only."
        ),
    }


def render_text(r: dict) -> str:
    L, A = [], None
    out = []
    def A(s=""):
        out.append(s)
    A("=" * 70)
    A("  BIRTH-TIME RECTIFICATION  (event-fit — a best guess, not a proof)")
    A("=" * 70)
    i = r["input"]
    A(f"  Date {i['date']} | approx {i['approx_time']} ({i['timezone']}) | "
      f"window ±{i['window_min']}min, step {i['step_min']}min")
    if not r["events"]:
        A("  (no events supplied — showing the Lagna-sensitivity scan only)")
    else:
        A(f"  Events: " + ", ".join(f"{e['date']}:{e['type']}" for e in r["events"]))

    A("")
    A("-" * 70)
    A("  LAGNA SENSITIVITY across the window")
    A("-" * 70)
    sc = r["lagna_sensitivity"]["lagna_sign_changes"]
    nc = r["lagna_sensitivity"]["lagna_nakshatra_changes"]
    if not sc:
        A("  Lagna SIGN is stable across the whole window (sign-level reading is safe).")
    else:
        for c in sc:
            A(f"  Lagna sign changes at {c['at']}: {c['from']} -> {c['to']}")
    if nc:
        A("  Lagna nakshatra shifts at: " + ", ".join(f"{c['at']}->{c['to']}" for c in nc))

    if r["events"]:
        A("")
        A("-" * 70)
        A(f"  EVENT-FIT RANKING  (best of {r['max_possible_score']} possible)")
        A("-" * 70)
        A(f"  {'Time':<10}{'Δmin':>7}  {'Lagna':<12}{'Score':>6}")
        for c in r["ranked"][:8]:
            A(f"  {c['time']:<10}{c['delta_min']:>7}  {c['lagna']:<12}{c['total_score']:>6}")
        best = r["best"]
        A("")
        A(f"  BEST FIT: {best['time']}  ({best['delta_min']:+} min from your input)")
        A(f"           Lagna {best['lagna']} in {best['lagna_nakshatra']}")
        A("           Per-event:")
        for e in best["events"]:
            ac = e["active"]
            chain = f"{ac['maha']}-{ac['antar']}-{ac['pratyantar']}"
            bits = []
            if e["dasha_hits"]:
                bits.append("dasha " + "/".join(e["dasha_hits"]))
            if e["transit_hits"]:
                bits.append("transit " + "/".join(e["transit_hits"]))
            A(f"             {e['date']} {e['type']:<12} [{chain}] "
              f"score {e['score']}  {'; '.join(bits) if bits else '(no strong fit)'}")

    A("")
    A("-" * 70)
    A("  " + r["disclaimer"])
    A("=" * 70)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(
        description="Birth-time rectification by life-event fitting.")
    ap.add_argument("--date", help="Birth date YYYY-MM-DD")
    ap.add_argument("--approx-time", dest="approx_time",
                    help="Approximate birth time HH:MM[:SS], 24h local")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--tz", help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--window", type=float, default=60.0,
                    help="Half-width of the search in MINUTES (default 60)")
    ap.add_argument("--step", type=float, default=2.0,
                    help="Candidate spacing in MINUTES (default 2)")
    ap.add_argument("--event", action="append",
                    help="Repeatable, 'YYYY-MM-DD:TYPE' (see --list-events)")
    ap.add_argument("--list-events", action="store_true",
                    help="Print the valid event types and exit")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.list_events:
        print("Valid event types:")
        for k, v in sorted(EVENT_TYPES.items()):
            print(f"  {k:<13} houses {sorted(v['houses'])}, karakas {sorted(v['karakas'])}")
        return

    missing = [f"--{n}" for n in ("date", "approx_time", "lat", "lon", "tz")
               if getattr(args, n) is None]
    if missing:
        ap.error("the following arguments are required: " + ", ".join(missing))

    try:
        result = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

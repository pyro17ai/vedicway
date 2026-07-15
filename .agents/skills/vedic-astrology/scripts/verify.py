#!/usr/bin/env python3
"""verify.py — reproduce / cross-check a chart from another source.

When a chart (JSON/PDF) comes from other software and you want to confirm it
against this engine, the usual surprise is that EVERY planet matches except the
Moon. Most Indian software computes geocentric positions; this skill defaults to
topocentric, and lunar parallax can shift the Moon up to ~1deg. This tool prints
each planet's sidereal longitude under BOTH conventions, highlights the Moon
delta, and — if you pass the external Moon longitude via --expect-moon — tells you
which convention the source used. It also reminds you that some sources encode
degrees as DD<degsym>MM, not decimal degrees.

For cultural/educational use only.
"""
import argparse
import json

import core


def _parse_time(t):
    parts = t.split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    return hh, mm, ss


def _positions(args, topocentric):
    core.init_engine(args.ayanamsa, node=args.node, topocentric=topocentric,
                     lat=args.lat, lon=args.lon, ephemeris=args.ephemeris)
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)
    return {n: p["longitude"] for n, p in core.all_planet_positions(jd).items()}


def _ang(a, b):
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def compute(args):
    topo = _positions(args, True)
    geo = _positions(args, False)
    rows = []
    for name in core.PLANET_ORDER:
        rows.append({
            "planet": name,
            "topocentric": round(topo[name], 4),
            "geocentric": round(geo[name], 4),
            "delta_arcmin": round(_ang(topo[name], geo[name]) * 60.0, 2),
        })
    out = {
        "input": {"date": args.date, "time": args.time, "lat": args.lat, "lon": args.lon,
                  "timezone": args.tz, "ayanamsa": args.ayanamsa},
        "positions": rows,
        "note": "Only the Moon should differ materially (lunar parallax). DD.MM in a "
                "source may mean DDdeg MM' (e.g. 14.57 = 14deg57'), not decimal degrees.",
    }
    if args.expect_moon is not None:
        em = float(args.expect_moon) % 360.0
        dt = _ang(em, topo["Moon"]) * 60.0
        dg = _ang(em, geo["Moon"]) * 60.0
        out["moon_match"] = {
            "expected_moon": em,
            "delta_to_topocentric_arcmin": round(dt, 2),
            "delta_to_geocentric_arcmin": round(dg, 2),
            "source_appears": ("topocentric" if dt < dg else "geocentric"),
        }
    return out


def render_text(r):
    o = []
    A = o.append
    A("=" * 62)
    A("  VERIFY — topocentric vs geocentric cross-check")
    A("=" * 62)
    A("  Planet    Topocentric   Geocentric    delta (arcmin)")
    A("  " + "-" * 52)
    for p in r["positions"]:
        flag = "  <-- parallax" if p["delta_arcmin"] >= 5 else ""
        A(f"  {p['planet']:<8}  {p['topocentric']:>9.4f}   {p['geocentric']:>9.4f}"
          f"   {p['delta_arcmin']:>8.2f}{flag}")
    A("  " + "-" * 52)
    if "moon_match" in r:
        mm = r["moon_match"]
        A(f"  Expected Moon {mm['expected_moon']:.4f}  ->  source appears "
          f"{mm['source_appears'].upper()} "
          f"(topo {mm['delta_to_topocentric_arcmin']}' vs geo {mm['delta_to_geocentric_arcmin']}')")
    A("  " + r["note"])
    A("=" * 62)
    A("  For cultural/educational use only.")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser(description="Cross-check a chart: topocentric vs geocentric.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--expect-moon", default=None, dest="expect_moon",
                    help="external Moon sidereal longitude (deg) to detect the source convention")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = compute(args)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result))


if __name__ == "__main__":
    main()

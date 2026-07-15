#!/usr/bin/env python3
"""
muhurta.py — electional astrology: find the best day/time for an event.

Scans a date range and ranks each day for a chosen event (marriage, business,
vehicle, house-warming, education, travel, contract, investment, surgery, or
general) using the panchang: the weekday (vara), tithi, the Moon's nakshatra, the
nitya yoga, and the karana (flagging Bhadra/Vishti). It avoids Rahu Kaal /
Yamaganda / Gulika and recommends the Abhijit muhurta window. Give birth details
and it also weighs **Tara Bala** (from your janma nakshatra) and **Chandra Bala**
(the Moon's transit from your natal Moon).

Usage:
    python muhurta.py --event marriage --from 2026-11-01 --to 2026-12-15 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata [--top 7] \\
        [--birth-date 1990-08-15 --birth-time 14:30:00 \\
         --birth-lat 28.61 --birth-lon 77.21 --birth-tz Asia/Kolkata]

Disclaimer: cultural / educational use only. A muhurta improves the "weather" of a
start; it is not a guarantee. Not medical/financial/legal advice. For surgery and
all health matters, your doctor's schedule comes first — always.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta

import core
import panchang as pn

N = core.NAKSHATRAS
GENERAL_GOOD = {"Ashwini", "Rohini", "Mrigashira", "Punarvasu", "Pushya", "Hasta",
                "Chitra", "Swati", "Anuradha", "Shravana", "Dhanishta", "Revati",
                "Uttara Phalguni", "Uttara Ashadha", "Uttara Bhadrapada"}
GENERAL_BAD = {"Bharani", "Krittika", "Ardra", "Ashlesha", "Jyeshtha", "Mula"}

# Per-event: favourable nakshatras, preferred weekdays, avoided weekdays, note.
EVENTS = {
    "marriage": {"nak": {"Rohini", "Mrigashira", "Magha", "Uttara Phalguni", "Hasta",
                         "Swati", "Anuradha", "Mula", "Uttara Ashadha",
                         "Uttara Bhadrapada", "Revati"},
                 "good_days": {"Monday", "Wednesday", "Thursday", "Friday"},
                 "bad_days": {"Tuesday", "Saturday"}},
    "business": {"nak": {"Ashwini", "Pushya", "Hasta", "Chitra", "Anuradha",
                         "Shravana", "Dhanishta", "Revati", "Uttara Phalguni"},
                 "good_days": {"Wednesday", "Thursday", "Friday"},
                 "bad_days": {"Tuesday", "Saturday", "Sunday"}},
    "vehicle": {"nak": {"Ashwini", "Rohini", "Mrigashira", "Punarvasu", "Pushya",
                        "Hasta", "Chitra", "Swati", "Anuradha", "Shravana",
                        "Dhanishta", "Shatabhisha", "Revati"},
                "good_days": {"Monday", "Wednesday", "Thursday", "Friday"},
                "bad_days": {"Tuesday", "Saturday"}},
    "house": {"nak": {"Rohini", "Mrigashira", "Uttara Phalguni", "Uttara Ashadha",
                      "Uttara Bhadrapada", "Chitra", "Anuradha", "Revati"},
              "good_days": {"Monday", "Wednesday", "Thursday", "Friday"},
              "bad_days": {"Tuesday", "Sunday"}},
    "education": {"nak": {"Ashwini", "Mrigashira", "Punarvasu", "Pushya", "Hasta",
                          "Chitra", "Swati", "Anuradha", "Shravana", "Dhanishta", "Revati"},
                  "good_days": {"Wednesday", "Thursday", "Friday"},
                  "bad_days": {"Tuesday", "Saturday"}},
    "travel": {"nak": {"Ashwini", "Mrigashira", "Punarvasu", "Pushya", "Hasta",
                       "Anuradha", "Shravana", "Dhanishta", "Revati"},
               "good_days": {"Monday", "Wednesday", "Friday"},
               "bad_days": {"Tuesday", "Saturday", "Sunday"}},
    "contract": {"nak": {"Ashwini", "Pushya", "Hasta", "Chitra", "Swati",
                         "Anuradha", "Shravana", "Revati"},
                 "good_days": {"Wednesday", "Thursday", "Friday"},
                 "bad_days": {"Tuesday", "Saturday"}},
    "investment": {"nak": {"Ashwini", "Pushya", "Hasta", "Chitra", "Anuradha",
                           "Shravana", "Dhanishta", "Revati"},
                   "good_days": {"Wednesday", "Thursday", "Friday"},
                   "bad_days": {"Tuesday", "Saturday"}},
    "surgery": {"nak": {"Ashwini", "Mrigashira", "Punarvasu", "Pushya", "Hasta",
                        "Anuradha", "Shravana", "Dhanishta", "Shatabhisha", "Revati"},
                "good_days": {"Tuesday"}, "bad_days": {},
                "krishna_bonus": True,
                "note": "Surgery muhurta is specialised: Krishna (waning) paksha is "
                        "traditionally preferred and the Moon should avoid the sign ruling "
                        "the body part operated on. ALWAYS follow your surgeon's schedule first."},
    "general": {"nak": GENERAL_GOOD, "good_days": {"Monday", "Wednesday", "Thursday", "Friday"},
                "bad_days": set()},
}

BAD_YOGAS = {"Vyatipata", "Vaidhriti"}
ROUGH_YOGAS = {"Vishkambha", "Atiganda", "Shula", "Ganda", "Vyaghata", "Vajra", "Parigha"}
GOOD_YOGAS = {"Siddhi", "Shubha", "Brahma", "Indra", "Dhruva", "Harshana",
              "Saubhagya", "Sukarma", "Priti", "Ayushman", "Sadhya", "Siddha"}
TARA_NAME = {1: "Janma", 2: "Sampat", 3: "Vipat", 4: "Kshema", 5: "Pratyak",
             6: "Sadhana", 7: "Naidhana", 8: "Mitra", 9: "Parama Mitra"}
TARA_BAD = {3, 5, 7}


def _shim(date_str, lat, lon, tz, ayan):
    class A: pass
    a = A(); a.date = date_str; a.time = "12:00:00"
    a.lat = lat; a.lon = lon; a.tz = tz; a.ayanamsa = ayan
    return a


def _natal_moon(args):
    """Return (nakshatra_index, sign_num) of the natal Moon, or None."""
    if not args.birth_date:
        return None
    core.init_engine(args.ayanamsa)
    y, m, d = (int(x) for x in args.birth_date.split("-"))
    t = (args.birth_time or "12:00:00").split(":")
    hh = int(t[0]); mm = int(t[1]) if len(t) > 1 else 0; ss = int(t[2]) if len(t) > 2 else 0
    blat = args.birth_lat if args.birth_lat is not None else args.lat
    blon = args.birth_lon if args.birth_lon is not None else args.lon
    btz = args.birth_tz or args.tz
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, btz)
    mlon, _ = core.sidereal_longitude(jd, core.PLANETS["Moon"])
    return int(mlon // core.NAKSHATRA_SPAN), int(mlon // 30) + 1


def score_day(pan: dict, ev: dict, natal):
    s = 50.0
    why = []
    # True-neutral branches award 0 so an unremarkable day stays at the 50
    # baseline ("Fair") rather than drifting up into "Good" on nothing.
    nak = pan["nakshatra"]["name"]
    if nak in ev["nak"]:
        s += 25; why.append(f"+nakshatra {nak} is favourable for this event")
    elif nak in GENERAL_BAD:
        s -= 25; why.append(f"-nakshatra {nak} is generally inauspicious")
    elif nak in GENERAL_GOOD:
        s += 12; why.append(f"+nakshatra {nak} is generally auspicious")

    vara = pan["vara"]
    if vara in ev["good_days"]:
        s += 12; why.append(f"+{vara} is a favoured weekday")
    elif vara in ev["bad_days"]:
        s -= 15; why.append(f"-{vara} is best avoided for this event")

    tnum = pan["tithi"]["number"]; tname = pan["tithi"]["name"]
    if tname == "Amavasya":
        s -= 22; why.append("-Amavasya (new moon)")
    elif tnum in (4, 9, 14):
        s -= 18; why.append(f"-Rikta tithi ({tname})")
    elif tname == "Purnima":
        s += 8; why.append("+Purnima (full moon)")
    elif tnum == 8:
        s -= 6; why.append("-Ashtami")
    if ev.get("krishna_bonus") and pan["tithi"]["paksha"] == "Krishna":
        s += 8; why.append("+Krishna paksha (preferred for surgery)")

    yoga = pan["yoga"]["name"]
    if yoga in BAD_YOGAS:
        s -= 18; why.append(f"-{yoga} yoga (inauspicious)")
    elif yoga in ROUGH_YOGAS:
        s -= 7; why.append(f"-{yoga} yoga (rough)")
    elif yoga in GOOD_YOGAS:
        s += 7; why.append(f"+{yoga} yoga (auspicious)")

    bhadra = pan["karana"]["name"] == "Vishti"
    if bhadra:
        s -= 18; why.append("-Vishti (Bhadra) karana — avoid starting work")

    tara = chandra = None
    if natal:
        njak, nsign = natal
        cnt = ((N.index(nak) - njak) % 27) + 1
        tnumb = ((cnt - 1) % 9) + 1
        tara = TARA_NAME[tnumb]
        if tnumb in TARA_BAD:
            s -= 18; why.append(f"-Tara Bala: {tara} (unfavourable from your Moon)")
        elif tnumb == 1:
            why.append("Tara Bala: Janma (mixed)")
        else:
            s += 12; why.append(f"+Tara Bala: {tara} (favourable)")
        day_moon_sign = int(pan["moon_longitude"] // 30) + 1
        cpos = ((day_moon_sign - nsign) % 12) + 1
        chandra = cpos
        if cpos in (4, 8, 12):
            s -= 15; why.append(f"-Chandra Bala: Moon {cpos}th from your Moon (weak)")
        elif cpos in (1, 3, 6, 7, 10, 11):
            s += 8; why.append(f"+Chandra Bala: Moon {cpos}th from your Moon (strong)")

    s = max(0.0, min(100.0, s))
    verdict = ("Excellent" if s >= 78 else "Good" if s >= 62 else
               "Fair" if s >= 45 else "Avoid")
    return s, verdict, why, {"tara": tara, "chandra_pos": chandra}


def compute(args) -> dict:
    natal = _natal_moon(args)
    d0 = datetime.strptime(args.date_from, "%Y-%m-%d").date()
    d1 = datetime.strptime(args.date_to, "%Y-%m-%d").date()
    if d1 < d0:
        raise ValueError("--to is before --from")
    if (d1 - d0).days > 180:
        raise ValueError("range too large (max 180 days)")

    ev = EVENTS[args.event]
    days = []
    cur = d0
    while cur <= d1:
        pan = pn.compute_panchang(_shim(cur.isoformat(), args.lat, args.lon, args.tz, args.ayanamsa))
        s, verdict, why, extra = score_day(pan, ev, natal)
        days.append({
            "date": cur.isoformat(), "weekday": pan["vara"], "score": round(s, 1),
            "verdict": verdict, "nakshatra": pan["nakshatra"]["name"],
            "tithi": f"{pan['tithi']['paksha']} {pan['tithi']['name']}",
            "yoga": pan["yoga"]["name"], "bhadra": pan["karana"]["name"] == "Vishti",
            "abhijit": pan.get("abhijit"), "avoid": {
                "rahu_kaal": pan.get("rahu_kaal"), "yamaganda": pan.get("yamaganda"),
                "gulika": pan.get("gulika")},
            "reasons": why, **extra,
        })
        cur += timedelta(days=1)

    ranked = sorted(days, key=lambda x: x["score"], reverse=True)
    return {"event": args.event, "from": args.date_from, "to": args.date_to,
            "personalised": natal is not None, "note": ev.get("note"),
            "ranked": ranked}


def render_text(r: dict, top: int) -> str:
    L = []
    A = L.append
    A("=" * 70)
    A(f"  MUHURTA — best time for: {r['event'].upper()}")
    A("=" * 70)
    A(f"  Window: {r['from']} to {r['to']}"
      + ("   (personalised with your birth Moon)" if r["personalised"] else ""))
    if r["note"]:
        A(f"  Note: {r['note']}")
    A("-" * 70)
    A(f"  Top {top} days:")
    for d in r["ranked"][:top]:
        bh = "  [Bhadra!]" if d["bhadra"] else ""
        tail = ""
        if d.get("tara"):
            tail = f"  Tara:{d['tara']}"
        A(f"\n  {d['date']} ({d['weekday'][:3]})  {d['verdict']:<9} score {d['score']:>5}{bh}{tail}")
        A(f"     nakshatra {d['nakshatra']} | {d['tithi']} | yoga {d['yoga']}")
        A(f"     best window: Abhijit {d['abhijit'] or 'n/a'}   "
          f"| avoid Rahu {d['avoid']['rahu_kaal'] or 'n/a'}")
        top_reasons = [w for w in d["reasons"] if w.startswith(("+", "-"))][:3]
        if top_reasons:
            A(f"     why: {'; '.join(top_reasons)}")
    A("\n" + "=" * 70)
    A("  Scores blend vara, tithi, nakshatra, yoga and karana"
      + (" with your Tara & Chandra Bala." if r["personalised"] else "."))
    A("  A muhurta improves the start's 'weather' — it is not a guarantee.")
    A("  For cultural/educational use only. For surgery, your doctor comes first.")
    A("=" * 70)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Find an auspicious muhurta for an event over a date range.")
    ap.add_argument("--event", required=True, choices=sorted(EVENTS))
    ap.add_argument("--from", dest="date_from", required=True, help="Range start YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", required=True, help="Range end YYYY-MM-DD")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--top", type=int, default=7)
    ap.add_argument("--birth-date", default=None, help="(optional) for Tara/Chandra Bala")
    ap.add_argument("--birth-time", default="12:00:00")
    ap.add_argument("--birth-lat", type=float, default=None)
    ap.add_argument("--birth-lon", type=float, default=None)
    ap.add_argument("--birth-tz", default=None)
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    for label, val in (("--from", args.date_from), ("--to", args.date_to)):
        try:
            datetime.strptime(val, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: {label} must be YYYY-MM-DD, got '{val}'", file=sys.stderr)
            sys.exit(1)

    try:
        result = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result, args.top))


if __name__ == "__main__":
    main()

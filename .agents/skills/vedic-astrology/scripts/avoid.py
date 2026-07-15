#!/usr/bin/env python3
"""
avoid.py — "What NOT to do" / Dishanirdesh: the don'ts for a day or week.

Where muhurta.py finds the BEST time to start something, this is its mirror: it
reads the panchang (and, if birth details are given, your natal Moon) and surfaces
what to **refrain from** and which **time windows to avoid**, with a concrete
"do-not" list rather than an abstract score.

What it checks per day:
  • Inauspicious time windows — Rahu Kaal, Yamaganda, Gulika Kaal.
  • Vishti (Bhadra) karana — the classic "don't begin auspicious work" half-tithi.
  • Rikta tithi (4th/9th/14th) and Amavasya — weak lunar days for new starts.
  • Harsh yogas (Vyatipata, Vaidhriti, and the rough set).
  • Tikshna / Ugra nakshatras (Bharani, Krittika, Ardra, Ashlesha, Jyeshtha, Mula).
  • Panchak — Moon in Aquarius/Pisces; the five classical prohibitions.
  • Disha Shool — the compass direction to avoid travelling toward, by weekday.
  • PERSONALISED (with birth): Chandrashtama (Moon in the 8th from your natal
    Moon), weak Tara Bala (Vipat/Pratyak/Naidhana), and weak Chandra Bala.

Usage:
    python avoid.py --date 2026-06-08 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--days 7] \\
        [--birth-date 1990-08-15 --birth-time 14:30:00 \\
         --birth-lat 28.61 --birth-lon 77.21 --birth-tz Asia/Kolkata] [--json]

Disclaimer: cultural / educational use only. These are traditional cautions, not
predictions, and never a basis for medical, financial, or legal decisions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

import core
import panchang as pn

N = core.NAKSHATRAS

# Canonical activity phrasings — kept consistent so reasons consolidate cleanly.
A_NEW = "starting anything new (launches, first deals, new ventures)"
A_SIGN = "signing contracts or agreements"
A_TRAVEL = "travel / starting a journey"
A_SHUBH = "weddings & auspicious ceremonies (shubh karya)"
A_BUY = "big purchases (vehicle, property, gold, electronics)"
A_MONEY = "lending, borrowing or investing money"
A_DECIDE = "important decisions, interviews or key meetings"
A_MED = "elective medical procedures (your doctor's schedule comes first)"
A_FIGHT = "confrontations & disputes"

# Tikshna (sharp) + Ugra (fierce) nakshatras — suited only to bold/severing tasks.
HARSH_NAK = {"Bharani", "Krittika", "Ardra", "Ashlesha", "Jyeshtha", "Mula"}
BAD_YOGAS = {"Vyatipata", "Vaidhriti"}
ROUGH_YOGAS = {"Vishkambha", "Atiganda", "Shula", "Ganda", "Vyaghata", "Vajra", "Parigha"}

TARA_NAME = {1: "Janma", 2: "Sampat", 3: "Vipat", 4: "Kshema", 5: "Pratyak",
             6: "Sadhana", 7: "Naidhana", 8: "Mitra", 9: "Parama Mitra"}
TARA_BAD = {3: "Vipat", 5: "Pratyak", 7: "Naidhana"}

# Disha Shool — the direction NOT to set out toward, by weekday (classical).
DISHA_SHOOL = {"Sunday": "West", "Monday": "East", "Tuesday": "North",
               "Wednesday": "North", "Thursday": "South", "Friday": "West",
               "Saturday": "East"}
# A token traditional remedy if travel that way is unavoidable (cultural note only).
DISHA_REMEDY = {"East": "a sip of milk", "West": "a little barley or a snack",
                "North": "a spoon of sesame/jaggery", "South": "a bit of curd"}


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


def assess_day(pan: dict, natal) -> dict:
    """Build the list of cautions for one day. Each flag = severity, title,
    refrain-list and a short note."""
    flags = []   # {sev, title, refrain:[...], note}

    def flag(sev, title, refrain, note=""):
        flags.append({"sev": sev, "title": title, "refrain": refrain, "note": note})

    nak = pan["nakshatra"]["name"]
    yoga = pan["yoga"]["name"]
    tname = pan["tithi"]["name"]
    tnum = pan["tithi"]["number"]
    vara = pan["vara"]
    moon_sign_num = int(pan["moon_longitude"] // 30) + 1
    moon_sign = core.SIGNS[moon_sign_num - 1]

    # --- Vishti (Bhadra) karana ---------------------------------------------
    if pan["karana"]["name"] == "Vishti":
        flag("high", "Vishti (Bhadra) karana",
             [A_NEW, A_SIGN, A_SHUBH, A_TRAVEL],
             "Bhadra is reserved for bold/severing acts, never for auspicious beginnings.")

    # --- Tithi --------------------------------------------------------------
    if tname == "Amavasya":
        flag("high", "Amavasya (new moon)",
             [A_NEW, A_SHUBH, A_TRAVEL, A_BUY],
             "A dark, low-energy lunar day — best kept for rest and remembrance, not new work.")
    elif tnum in (4, 9, 14):
        flag("med", f"Rikta tithi ({tname})",
             [A_NEW, A_SIGN, A_SHUBH, A_BUY],
             "Rikta ('empty') tithis drain new undertakings; fine for clearing/finishing tasks.")
    elif tnum == 8:
        flag("low", "Ashtami",
             [A_SHUBH], "A mixed lunar day — keep major ceremonies for a stronger tithi.")

    # --- Yoga ---------------------------------------------------------------
    if yoga in BAD_YOGAS:
        flag("high", f"{yoga} yoga",
             [A_NEW, A_SIGN, A_SHUBH, A_TRAVEL, A_DECIDE],
             "One of the two most inauspicious nitya yogas — avoid anything you want to last.")
    elif yoga in ROUGH_YOGAS:
        flag("low", f"{yoga} yoga (rough)",
             [A_NEW], "A rough yoga — be cautious launching anything important.")

    # --- Nakshatra ----------------------------------------------------------
    if nak in HARSH_NAK:
        flag("med", f"{nak} nakshatra (tikshna/ugra)",
             [A_SHUBH, A_TRAVEL, A_NEW],
             "A sharp/fierce star — suited to bold or severing acts, not gentle beginnings.")

    # --- Panchak (Moon in Aquarius or Pisces) -------------------------------
    if moon_sign in ("Aquarius", "Pisces"):
        flag("med", f"Panchak (Moon in {moon_sign})",
             ["laying a roof / overhead construction",
              "buying firewood, fuel or large quantities of grass/grain",
              "south-bound travel",
              "funeral arrangements (risk of repetition, by tradition)",
              "buying or assembling a bed / cot"],
             "The five classical Panchak prohibitions; ordinary work is unaffected.")

    # --- Disha Shool (direction to avoid for travel) ------------------------
    direction = DISHA_SHOOL[vara]
    flag("low", f"Disha Shool — {direction}",
         [f"travelling toward the {direction} today"],
         f"If unavoidable, tradition suggests taking {DISHA_REMEDY[direction]} before leaving.")

    # --- Personalised: natal-Moon based -------------------------------------
    personal = {}
    if natal:
        njak, nsign = natal
        # Chandrashtama — Moon in the 8th sign from your janma rashi.
        cpos = ((moon_sign_num - nsign) % 12) + 1
        personal["chandra_pos"] = cpos
        if cpos == 8:
            flag("high", "Chandrashtama (Moon in your 8th)",
                 [A_DECIDE, A_SIGN, A_TRAVEL, A_FIGHT, A_BUY],
                 "Your personal low-fuel day — emotions run thin; rest and defer big moves.")
        elif cpos in (4, 12):
            flag("low", f"Weak Chandra Bala (Moon {cpos}th from your Moon)",
                 [A_DECIDE], "Mood is off-key — keep emotionally-charged decisions for another day.")

        # Tara Bala from janma nakshatra.
        cnt = ((N.index(nak) - njak) % 27) + 1
        tnumb = ((cnt - 1) % 9) + 1
        personal["tara"] = TARA_NAME[tnumb]
        if tnumb in TARA_BAD:
            flag("med", f"Weak Tara Bala — {TARA_BAD[tnumb]}",
                 [A_TRAVEL, A_NEW, A_MONEY],
                 "An unfavourable star-count from your birth star — avoid risk and new commitments.")

    sev_rank = {"high": 0, "med": 1, "low": 2}
    flags.sort(key=lambda f: sev_rank[f["sev"]])

    # Consolidate the refrain-list across all flags (activity -> driving titles).
    refrain = {}
    for f in flags:
        for act in f["refrain"]:
            refrain.setdefault(act, [])
            if f["title"] not in refrain[act]:
                refrain[act].append(f["title"])

    worst = next((f["sev"] for f in flags if f["title"] != f"Disha Shool — {direction}"), None)
    headline = {"high": "Heads-up day — real cautions",
                "med": "Mixed day — a few things to avoid",
                "low": "Mostly clear — minor cautions only",
                None: "Clear day — no notable restrictions"}[worst]

    return {
        "date": pan["input"]["date"], "weekday": vara,
        "nakshatra": nak, "tithi": f"{pan['tithi']['paksha']} {tname}",
        "yoga": yoga, "moon_sign": moon_sign,
        "headline": headline, "worst_severity": worst,
        "windows": {"rahu_kaal": pan.get("rahu_kaal"),
                    "yamaganda": pan.get("yamaganda"),
                    "gulika": pan.get("gulika")},
        "abhijit": pan.get("abhijit"),
        "disha_shool": direction,
        "flags": flags, "refrain": refrain, **personal,
    }


def compute(args) -> dict:
    natal = _natal_moon(args)
    d0 = datetime.strptime(args.date, "%Y-%m-%d").date()
    days = []
    for i in range(args.days):
        cur = d0 + timedelta(days=i)
        pan = pn.compute_panchang(_shim(cur.isoformat(), args.lat, args.lon, args.tz, args.ayanamsa))
        days.append(assess_day(pan, natal))
    return {"from": d0.isoformat(), "days": args.days,
            "personalised": natal is not None, "report": days}


SEV_MARK = {"high": "‼️ ", "med": "⚠️ ", "low": "· "}


def _render_day(d: dict, lines, personalised):
    A = lines.append
    A("-" * 70)
    A(f"  {d['date']} ({d['weekday']})  —  {d['headline']}")
    A(f"     {d['nakshatra']} nakshatra | {d['tithi']} | {d['yoga']} yoga | Moon in {d['moon_sign']}")

    w = d["windows"]
    A("  ⏰ Avoid these time windows (begin nothing important inside them):")
    A(f"       Rahu Kaal {w['rahu_kaal'] or 'n/a'}   |   Yamaganda {w['yamaganda'] or 'n/a'}"
      f"   |   Gulika {w['gulika'] or 'n/a'}")
    if d.get("abhijit"):
        A(f"     (best window instead: Abhijit muhurta {d['abhijit']})")

    if d["refrain"]:
        A("  ❌ Refrain from:")
        for act, why in d["refrain"].items():
            A(f"       • {act}")
            A(f"           ↳ {', '.join(why)}")

    notable = [f for f in d["flags"] if not f["title"].startswith("Disha Shool")]
    if notable:
        A("  Why:")
        for f in notable:
            A(f"     {SEV_MARK[f['sev']]}{f['title']} — {f['note']}")
    A(f"  🧭 Disha Shool: avoid travelling toward the {d['disha_shool']} today.")
    if personalised:
        bits = []
        if "tara" in d:
            bits.append(f"Tara: {d['tara']}")
        if "chandra_pos" in d:
            bits.append(f"Moon {d['chandra_pos']}th from your janma rashi")
        if bits:
            A("  (personalised: " + " | ".join(bits) + ")")


def render_text(r: dict) -> str:
    L = []
    A = L.append
    A("=" * 70)
    title = "WHAT TO AVOID" + ("  (this week)" if r["days"] > 1 else "  (today)")
    A(f"  {title}")
    A("=" * 70)
    span = (f"  {r['from']}  (+{r['days']-1} more day{'s' if r['days'] > 2 else ''})"
            if r["days"] > 1 else f"  {r['from']}")
    A(span + ("   — personalised with your birth Moon" if r["personalised"] else ""))

    if r["days"] > 1:
        flagged = [d for d in r["report"] if d["worst_severity"] in ("high", "med")]
        if flagged:
            A("-" * 70)
            A("  Days to be most careful:")
            for d in flagged:
                A(f"     {SEV_MARK[d['worst_severity']]}{d['date']} ({d['weekday'][:3]}) — {d['headline']}")
        else:
            A("  No high-caution days this week — only the usual daily time windows.")

    for d in r["report"]:
        _render_day(d, L, r["personalised"])

    A("=" * 70)
    A("  These are TRADITIONAL cautions about timing, not predictions. They never")
    A("  override a doctor, a deadline, or common sense. For cultural/educational")
    A("  use only — not for medical, financial, or legal decisions.")
    A("=" * 70)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="What to avoid / refrain from on a day or across a week.")
    ap.add_argument("--date", required=True, help="Start date YYYY-MM-DD (today's don'ts by default)")
    ap.add_argument("--days", type=int, default=1, help="How many days to cover (7 = a week)")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    ap.add_argument("--birth-date", default=None, help="(optional) personalises with your natal Moon")
    ap.add_argument("--birth-time", default="12:00:00")
    ap.add_argument("--birth-lat", type=float, default=None)
    ap.add_argument("--birth-lon", type=float, default=None)
    ap.add_argument("--birth-tz", default=None)
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got '{args.date}'", file=sys.stderr)
        sys.exit(1)
    if not (1 <= args.days <= 40):
        print("ERROR: --days must be between 1 and 40", file=sys.stderr)
        sys.exit(1)

    try:
        result = compute(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()

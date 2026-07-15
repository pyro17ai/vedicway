#!/usr/bin/env python3
"""
full_report.py — one shareable Astro Claude report (PDF or HTML).

Bundles the whole reading into a single document a seeker can keep: cover with
their name and birth details, a snapshot (Lagna, Moon, age, life stage, running
dasha, Sade Sati), today's Panchang + how the planets are aligned today
(personalised), the full birth-chart table, the kundli drawn in South- and
North-Indian style, the current-period life-area reading, career & place-of-work
analysis, the gemstone WEAR/AVOID list for their Lagna, and Rudraksha advice.

PDF is produced with fpdf2 (pure-Python, offline). If fpdf2 is not installed it
falls back to a self-contained HTML file you can open in any browser and
"Print → Save as PDF".

Usage:
    python full_report.py --name "Asha" --gender female --married no \\
        --date 1990-08-15 --time 14:30:00 \\
        --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata \\
        [--on 2026-06-04] [--away unknown] [--format pdf|html] [--out PATH]

Disclaimer: cultural / educational / reflective use only. Not advice; no proven
predictive power; never spend money on gemstones or rituals on this basis.
"""

from __future__ import annotations

import argparse
import html
import os
import sys
from datetime import date, datetime

import core
import astro_claude as ac
import chart as chart_mod
import dasha_predict as dp
import sky as sky_mod


def _parse_time(t: str):
    p = t.split(":")
    return int(p[0]), (int(p[1]) if len(p) > 1 else 0), (int(p[2]) if len(p) > 2 else 0)


def gather(args) -> dict:
    """Collect everything the report needs from the existing engines."""
    reading = ac.compute(args)

    # Birth-chart table (longitude / nakshatra / dignity / house / navamsa).
    core.init_engine(args.ayanamsa, node=args.node,
                     topocentric=not args.geocentric, lat=args.lat, lon=args.lon,
                     ephemeris=args.ephemeris)
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm, ss = _parse_time(args.time)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)
    asc = core.ascendant(jd, args.lat, args.lon)
    pos = core.all_planet_positions(jd)
    rows = []
    for n in core.PLANET_ORDER:
        p = pos[n]
        rows.append({
            "planet": n, "hindi": core.PLANET_HINDI[n],
            "sign": p["sign"], "deg": core.deg_to_dms(p["degree_in_sign"]),
            "house": core.house_of(p["sign_num"], asc["sign_num"]),
            "nakshatra": p["nakshatra"], "pada": p["pada"],
            "dignity": core.dignity(n, p["sign_num"]),
            "retro": "R" if p["retrograde"] else "",
        })

    # Chart diagrams (ASCII).
    class _C: pass
    ca = _C()
    for k in ("date", "time", "lat", "lon", "tz", "ayanamsa", "node",
              "geocentric", "ephemeris"):
        setattr(ca, k, getattr(args, k))
    ca.varga = "D1"
    cdata = chart_mod.compute(ca)
    south = chart_mod.render_south(cdata)
    north = chart_mod.render_north(cdata)

    # Current-period life-area reading.
    try:
        dpred = dp.compute(args)
    except Exception:
        dpred = None

    return {"reading": reading, "asc": asc, "table": rows,
            "south": south, "north": north, "dpred": dpred}


# --------------------------------------------------------------------------- #
# HTML output (zero-dependency, browser print-to-PDF)
# --------------------------------------------------------------------------- #
CSS = """
body{font-family:'Georgia',serif;color:#2b1a0e;max-width:820px;margin:0 auto;padding:28px;line-height:1.5}
h1{color:#b8860b;text-align:center;margin:.2em 0;font-size:30px}
.tag{text-align:center;color:#8a5a2b;font-style:italic;margin-bottom:18px}
h2{color:#7a1f12;border-bottom:2px solid #e0c089;padding-bottom:4px;margin-top:26px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid #d8c39a;padding:5px 8px;text-align:left}
th{background:#f6ecd6}
pre{background:#fbf6ea;border:1px solid #e0c089;padding:10px;font-size:12px;line-height:1.15;overflow-x:auto}
.wear li{color:#1d6b2f}.avoid li{color:#9a2515}
.snap{background:#fbf6ea;border:1px solid #e0c089;border-radius:8px;padding:10px 16px}
.foot{margin-top:28px;font-size:12px;color:#6b5640;border-top:1px solid #e0c089;padding-top:10px}
.cols{display:flex;gap:18px;flex-wrap:wrap}.cols>pre{flex:1;min-width:330px}
"""


def _h(s):  # escape
    return html.escape(str(s))


def render_html(data: dict) -> str:
    r = data["reading"]; p = r["profile"]
    out = [f"<!doctype html><html><head><meta charset='utf-8'><title>Astro Claude — {_h(p['name'])}</title>",
           f"<style>{CSS}</style></head><body>"]
    out.append("<h1>🕉 Astro Claude</h1>")
    out.append("<div class='tag'>A reading for the seeker</div>")

    # Snapshot
    married = {"yes": "married", "no": "unmarried"}.get(p["married"], "marital status not given")
    out.append("<div class='snap'>")
    out.append(f"<b>{_h(p['name'])}</b> &nbsp;·&nbsp; {p['age']} years (as of {p['as_of']}) "
               f"&nbsp;·&nbsp; {_h(p['gender'])} &nbsp;·&nbsp; {married}<br>")
    out.append(f"Born {_h(p['birth'])}<br>")
    out.append(f"Lagna: <b>{core.sign_hi(r['lagna']['sign'])}</b> "
               f"(nakshatra {_h(r['lagna']['nakshatra'])}) &nbsp;·&nbsp; "
               f"Moon: <b>{core.sign_hi(r['moon_sign'])}</b><br>")
    md, ad = r["dasha"]["maha"], r["dasha"]["antar"]
    out.append(f"Running dasha: <b>{core.planet_hi(md)} → {core.planet_hi(ad)}</b>")
    if r["sade_sati"]["active"]:
        out.append(" &nbsp;·&nbsp; <b style='color:#9a2515'>Sade Sati active</b>")
    out.append(f"<br>Life stage: {_h(r['life_stage'])}</div>")

    # Today's sky — the report opens with the same Panchang + alignment as the reading.
    out.append("<h2>Today's Sky — Panchang &amp; Planetary Alignment</h2>")
    sky_text = "\n".join(sky_mod.render_block(r["today_sky"], personal=True))
    out.append(f"<pre>{_h(sky_text)}</pre>")

    # Birth chart table
    out.append("<h2>Birth Chart (Graha Positions)</h2><table>")
    out.append("<tr><th>Planet</th><th>Hindi</th><th>Sign</th><th>Degree</th>"
               "<th>House</th><th>Nakshatra</th><th>Pada</th><th>Dignity</th></tr>")
    for t in data["table"]:
        out.append(f"<tr><td>{_h(t['planet'])}{(' ('+t['retro']+')') if t['retro'] else ''}</td>"
                   f"<td>{_h(t['hindi'])}</td><td>{_h(t['sign'])}</td><td>{_h(t['deg'])}</td>"
                   f"<td>{t['house']}</td><td>{_h(t['nakshatra'])}</td><td>{t['pada']}</td>"
                   f"<td>{_h(t['dignity'])}</td></tr>")
    out.append("</table>")

    # Charts
    out.append("<h2>Kundli Chart</h2><div class='cols'>")
    out.append(f"<pre>{_h(data['south'])}</pre><pre>{_h(data['north'])}</pre></div>")

    # Current period reading
    if data["dpred"]:
        out.append("<h2>Your Current Period — life areas</h2><table>")
        out.append("<tr><th>Area</th><th>Backdrop (Mahadasha)</th><th>Trigger (Antardasha)</th></tr>")
        eff = data["dpred"]["effects"]
        for key, label in dp.LIFE_AREAS:
            out.append(f"<tr><td><b>{_h(label)}</b></td><td>{_h(eff['mahadasha'][key])}</td>"
                       f"<td>{_h(eff['antardasha'][key])}</td></tr>")
        out.append("</table>")

    # Career & place
    out.append("<h2>Career &amp; Place of Work</h2>")
    aw = r["away_analysis"]
    if p["away_from_home"] == "yes" or aw["likely"]:
        out.append("<p>Your chart indicates thriving <b>away from your birthplace</b>:</p><ul>")
        for s in aw["signals"]:
            out.append(f"<li>{_h(s)}</li>")
        out.append("</ul><p>Distance tends to bring the growth — career, income and fortune "
                   "ripen better away from your native soil — at the cost of some separation "
                   "from family and roots.</p>")
    else:
        out.append("<p>Your chart does not strongly push you away from your birthplace; "
                   "relocation is a choice, not a compulsion.</p>")
    if r["career_windows"]:
        out.append("<p><b>Favourable windows to join a job/company:</b></p><ul>")
        for w in r["career_windows"]:
            out.append(f"<li>{w['start']} → {w['end']} — <b>{core.planet_hi(w['lord'])}</b>: "
                       f"{_h(', '.join(w['reasons']))}.</li>")
        out.append("</ul><p><i>Pick the day by muhurta — benefic weekday, good tithi, avoid Rahu Kaal.</i></p>")

    # Gemstones
    out.append(f"<h2>Gemstones — for your {_h(r['lagna']['sign'])} Lagna</h2>")
    g = r["gemstones"]
    out.append("<p><b>✅ Beneficial to wear</b></p><ul class='wear'>")
    for e in (g["wear"] or []):
        out.append(f"<li><b>{_h(e['gem'])}</b> ({core.planet_hi(e['planet'])}) — {_h(e['why'])}.</li>")
    if not g["wear"]:
        out.append("<li>No clearly benefic lord — rely on Rudraksha &amp; charity.</li>")
    out.append("</ul><p><b>⛔ Avoid / do not wear casually</b></p><ul class='avoid'>")
    for e in g["avoid"]:
        out.append(f"<li><b>{_h(e['gem'])}</b> ({core.planet_hi(e['planet'])}) — {_h(e['why'])}.</li>")
    out.append("</ul>")

    # Rudraksha
    out.append("<h2>Rudraksha</h2><p><b>Yes — safe for everyone</b> (Shiva's blessing). Suited beads:</p><ul>")
    for rec in r["rudraksha"]["recommendations"]:
        out.append(f"<li><b>{_h(rec['bead'])}</b> (for {_h(rec['for'])}) — {_h(rec['why'])}.</li>")
    out.append("</ul>")

    out.append("<div class='foot'>Astro Claude — for cultural, educational and reflective use only. "
               "Not medical, financial, legal, or psychological advice, and with no proven "
               "predictive power. Never spend money on gemstones or rituals on this basis. "
               f"Generated {date.today().isoformat()}.</div>")
    out.append("</body></html>")
    return "".join(out)


# --------------------------------------------------------------------------- #
# PDF output (fpdf2, ASCII-safe)
# --------------------------------------------------------------------------- #
def _ascii(s: str) -> str:
    repl = {"–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"',
            "•": "*", "→": "->", "·": "-", "½": "1/2", "⚠": "[!]",
            "🕉": "", "📿": "", "✨": "", "🪐": "", "🌌": ""}
    for k, v in repl.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def render_pdf(data: dict, out_path: str) -> None:
    from fpdf import FPDF

    r = data["reading"]; p = r["profile"]
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def H1(t):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 20); pdf.set_text_color(184, 134, 11)
        pdf.cell(0, 11, _ascii(t), new_x="LMARGIN", new_y="NEXT", align="C")
    def H2(t):
        pdf.ln(2); pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13); pdf.set_text_color(122, 31, 18)
        pdf.cell(0, 8, _ascii(t), new_x="LMARGIN", new_y="NEXT"); pdf.set_text_color(40, 26, 14)
    def body(t, size=10):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", size)
        pdf.multi_cell(0, 5, _ascii(t))
    def mono(t):
        pdf.set_font("Courier", "", 7)
        for line in t.split("\n"):
            pdf.set_x(pdf.l_margin)
            pdf.cell(0, 3, _ascii(line), new_x="LMARGIN", new_y="NEXT")

    H1("Astro Claude")
    pdf.set_font("Helvetica", "I", 11); pdf.set_text_color(138, 90, 43)
    pdf.cell(0, 6, "A reading for the seeker", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(40, 26, 14); pdf.ln(2)

    married = {"yes": "married", "no": "unmarried"}.get(p["married"], "marital status not given")
    md, ad = r["dasha"]["maha"], r["dasha"]["antar"]
    snap = (f"{p['name']}  -  {p['age']} years (as of {p['as_of']})  -  {p['gender']}  -  {married}\n"
            f"Born {p['birth']}\n"
            f"Lagna: {core.sign_hi(r['lagna']['sign'])} (nakshatra {r['lagna']['nakshatra']})  -  "
            f"Moon: {core.sign_hi(r['moon_sign'])}\n"
            f"Running dasha: {core.planet_hi(md)} -> {core.planet_hi(ad)}"
            + ("   [Sade Sati active]" if r["sade_sati"]["active"] else "") + "\n"
            f"Life stage: {r['life_stage']}")
    body(snap)

    H2("Today's Sky - Panchang & Planetary Alignment")
    mono("\n".join(sky_mod.render_block(r["today_sky"], personal=True)))

    H2("Birth Chart (Graha Positions)")
    pdf.set_font("Helvetica", "B", 9)
    widths = [22, 20, 22, 24, 12, 30, 12, 26]
    heads = ["Planet", "Hindi", "Sign", "Degree", "Hse", "Nakshatra", "Pada", "Dignity"]
    for w, hd in zip(widths, heads):
        pdf.cell(w, 6, hd, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for t in data["table"]:
        cells = [t["planet"] + (f" ({t['retro']})" if t["retro"] else ""), t["hindi"], t["sign"],
                 t["deg"], str(t["house"]), t["nakshatra"], str(t["pada"]), t["dignity"]]
        for w, c in zip(widths, cells):
            pdf.cell(w, 6, _ascii(c), border=1)
        pdf.ln()

    H2("Kundli Chart (South Indian)")
    mono(data["south"])
    H2("Kundli Chart (North Indian)")
    mono(data["north"])

    H2("Career & Place of Work")
    aw = r["away_analysis"]
    if p["away_from_home"] == "yes" or aw["likely"]:
        body("Your chart indicates thriving AWAY from your birthplace:")
        for s in aw["signals"]:
            body("  * " + s, 9)
        body("Distance tends to bring the growth, at the cost of some separation from roots.", 9)
    else:
        body("Your chart does not strongly push you away from your birthplace.", 9)
    if r["career_windows"]:
        body("Favourable windows to join a job/company:")
        for w in r["career_windows"]:
            body(f"  * {w['start']} -> {w['end']} - {core.planet_hi(w['lord'])}: "
                 f"{', '.join(w['reasons'])}.", 9)

    H2(f"Gemstones - for your {r['lagna']['sign']} Lagna")
    g = r["gemstones"]
    body("WEAR (beneficial):")
    for e in (g["wear"] or [{"gem": "none clearly benefic - use Rudraksha & charity",
                             "planet": "", "why": ""}]):
        line = f"  * {e['gem']}" + (f" ({core.planet_hi(e['planet'])}) - {e['why']}" if e['planet'] else "")
        body(line, 9)
    body("AVOID (do not wear casually):")
    for e in g["avoid"]:
        body(f"  * {e['gem']} ({core.planet_hi(e['planet'])}) - {e['why']}", 9)

    H2("Rudraksha")
    body("YES - safe for everyone (Shiva's blessing). Suited beads:")
    for rec in r["rudraksha"]["recommendations"]:
        body(f"  * {rec['bead']} (for {rec['for']}) - {rec['why']}", 9)

    pdf.ln(3); pdf.set_font("Helvetica", "I", 8); pdf.set_text_color(107, 86, 64)
    pdf.multi_cell(0, 4, _ascii(
        "Astro Claude - for cultural, educational and reflective use only. Not medical, "
        "financial, legal, or psychological advice, and with no proven predictive power. "
        "Never spend money on gemstones or rituals on this basis. Generated "
        + date.today().isoformat() + "."))
    pdf.output(out_path)


def main():
    ap = argparse.ArgumentParser(description="Generate a shareable Astro Claude report (PDF/HTML).")
    ap.add_argument("--name", required=True)
    ap.add_argument("--gender", default="unspecified",
                    choices=["male", "female", "other", "unspecified"])
    ap.add_argument("--married", default="unknown", choices=["yes", "no", "unknown"])
    ap.add_argument("--away", default="unknown", choices=["yes", "no", "unknown"])
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--on", default=date.today().isoformat())
    ap.add_argument("--format", default="auto", choices=["auto", "pdf", "html"])
    ap.add_argument("--out", default=None, help="Output path (default ./<Name>_kundli_<date>.<ext>)")
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true")
    ap.add_argument("--ephemeris", default="moshier", choices=["moshier", "swiss"])
    args = ap.parse_args()

    for label, val in (("--on", args.on), ("--date", args.date)):
        try:
            datetime.strptime(val, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: {label} must be YYYY-MM-DD, got '{val}'", file=sys.stderr)
            sys.exit(1)

    # Decide format.
    fmt = args.format
    have_fpdf = False
    try:
        import fpdf  # noqa: F401
        have_fpdf = True
    except ImportError:
        pass
    if fmt == "auto":
        # Honor the requested output extension so we never write PDF bytes
        # into a .html file (or vice versa). Default to PDF when no hint.
        ext = os.path.splitext(args.out)[1].lower() if args.out else ""
        if ext == ".html" or ext == ".htm":
            fmt = "html"
        elif ext == ".pdf":
            fmt = "pdf" if have_fpdf else "html"
        else:
            fmt = "pdf" if have_fpdf else "html"
    if fmt == "pdf" and not have_fpdf:
        print("NOTE: fpdf2 not installed (pip install fpdf2) — writing HTML instead.", file=sys.stderr)
        fmt = "html"

    # Warn if an explicit --format contradicts the --out extension, so we don't
    # silently write (e.g.) HTML bytes into a .pdf file without telling the user.
    if args.out:
        ext = os.path.splitext(args.out)[1].lower()
        if (fmt == "html" and ext == ".pdf") or (fmt == "pdf" and ext in (".html", ".htm")):
            print(f"NOTE: writing {fmt.upper()} content into '{args.out}' "
                  f"(its extension suggests otherwise — set --format auto to honor the extension).",
                  file=sys.stderr)

    safe_name = "".join(c for c in args.name if c.isalnum() or c in "-_") or "seeker"
    out = args.out or f"./{safe_name}_kundli_{args.date}.{fmt}"

    try:
        data = gather(args)
        if fmt == "pdf":
            render_pdf(data, out)
        else:
            with open(out, "w", encoding="utf-8") as f:
                f.write(render_html(data))
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Report written: {out}")


if __name__ == "__main__":
    main()

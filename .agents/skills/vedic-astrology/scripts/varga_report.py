#!/usr/bin/env python3
"""varga_report.py — a shareable divisional-chart ATLAS for any birth data.

Renders the requested vargas (default: all 20 = 16 Shodasavarga + D5/D6/D8/D11)
as South-Indian grids, each accompanied — unless --no-readings — by a five-part
explainer that shows HOW each life-area judgment is deduced:

  1. What it shows        (the life area)
  2. How it is built      (the amsa division, e.g. 30deg / 9 for D9)
  3. Technical read       (divisional Lagna + its lord's dignity, who sits with the
                           Lagna, which planets are exalted/own/debilitated)
  4. Significator + how we deduce it  (the karaka for the area + a transparent
                           3-factor verdict: STRONG / MODERATE / MIXED / TENDER)
  5. In plain words       (a one-line everyday takeaway)

The verdict is a transparent rule-of-thumb (Lagna-lord dignity + karaka dignity +
exalted-vs-debilitated count), NOT a classical Vimshopaka or a definitive judgment;
a full reading also weighs aspects, conjunctions and yogas. Outputs PDF (needs
fpdf2) or falls back to HTML.

Usage:
  python3 varga_report.py --name "Asha" --date 1990-08-15 --time 14:30:00 \
    --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --charts all+ --out ./Asha_vargas.pdf

For cultural/educational use only — not scientifically validated.
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
         "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
ABBR = ["Ar", "Ta", "Ge", "Cn", "Le", "Vi", "Li", "Sc", "Sg", "Cp", "Aq", "Pi"]
PL_ABBR = {"Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me",
           "Jupiter": "Ju", "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"}
PLANETS = list(PL_ABBR.keys())
# South-Indian fixed layout: (row,col) -> sign number 1..12; centre 2x2 = label.
SI_LAYOUT = {(0, 0): 12, (0, 1): 1, (0, 2): 2, (0, 3): 3, (1, 0): 11, (1, 3): 4,
             (2, 0): 10, (2, 3): 5, (3, 0): 9, (3, 1): 8, (3, 2): 7, (3, 3): 6}

# sign index 0..11 -> ruling planet
LORD = {0: "Mars", 1: "Venus", 2: "Mercury", 3: "Moon", 4: "Sun", 5: "Mercury",
        6: "Venus", 7: "Mars", 8: "Jupiter", 9: "Saturn", 10: "Saturn", 11: "Jupiter"}
EXALT = {"Sun": 0, "Moon": 1, "Mars": 9, "Mercury": 5, "Jupiter": 3, "Venus": 11, "Saturn": 6}
DEBIL = {"Sun": 6, "Moon": 7, "Mars": 3, "Mercury": 11, "Jupiter": 9, "Venus": 5, "Saturn": 0}
OWN = {"Sun": [4], "Moon": [3], "Mars": [0, 7], "Mercury": [2, 5], "Jupiter": [8, 11],
       "Venus": [1, 6], "Saturn": [9, 10]}
FRIEND = {"Sun": {"Moon", "Mars", "Jupiter"}, "Moon": {"Sun", "Mercury"},
          "Mars": {"Sun", "Moon", "Jupiter"}, "Mercury": {"Sun", "Venus"},
          "Jupiter": {"Sun", "Moon", "Mars"}, "Venus": {"Mercury", "Saturn"},
          "Saturn": {"Mercury", "Venus"}}
ENEMY = {"Sun": {"Venus", "Saturn"}, "Moon": set(), "Mars": {"Mercury"},
         "Mercury": {"Moon"}, "Jupiter": {"Mercury", "Venus"},
         "Venus": {"Sun", "Moon"}, "Saturn": {"Sun", "Moon", "Mars"}}


def dignity(p, sign_idx):
    if p in ("Rahu", "Ketu"):
        return "node"
    if EXALT[p] == sign_idx:
        return "exalted"
    if sign_idx in OWN[p]:
        return "own sign"
    if DEBIL[p] == sign_idx:
        return "debilitated"
    lord = LORD[sign_idx]
    if lord == p:
        return "own sign"
    if lord in FRIEND[p]:
        return "friendly"
    if lord in ENEMY[p]:
        return "enemy"
    return "neutral"


# Per-varga reading config: (area, how-built, [karakas], plain-language takeaway).
# "Lagna lord" in karakas resolves to that chart's ascendant lord.
V = {
 1:  ("the whole life, body & self", "the natural birth chart (no division)",
      ["Lagna lord"],
      "the master map; every other chart magnifies one life area within it."),
 2:  ("wealth & resources", "each sign split in 2 halves of 15deg (only Cancer or Leo result)",
      ["Jupiter", "Venus"],
      "more planets in Leo (Sun's hora) favours self-earned wealth & status; in Cancer (Moon's hora) favours flowing, accumulated wealth."),
 3:  ("siblings, courage & initiative", "each sign split in 3 of 10deg",
      ["Mars"],
      "strength of the 3rd lord and Mars shows drive, valour and the sibling bond."),
 4:  ("home, property & fortune", "each sign split in 4 of 7.5deg",
      ["Mars", "Moon"],
      "a dignified 4th lord / Moon points to stable property, vehicles and domestic peace."),
 5:  ("fame, power & authority", "non-classical: 5 parts, counted from the planet's own sign",
      ["Sun"],
      "a strong Sun and a dignified Lagna lord favour recognition and command over others."),
 6:  ("health, disease & debts", "non-classical: 6 parts from the planet's own sign",
      ["Saturn", "Mars"],
      "benefics well-placed protect health; malefics on the 6th/8th flag chronic strain or debt."),
 7:  ("children & progeny", "each sign split in 7 of ~4.28deg",
      ["Jupiter"],
      "a strong Jupiter and 5th lord favour healthy progeny and creative legacy."),
 8:  ("sudden events, accidents & longevity", "non-classical: 8 parts from the planet's own sign",
      ["Saturn"],
      "a protected 8th and steady Saturn soften shocks; afflictions warn to be careful with risk."),
 9:  ("spouse, marriage, dharma & inner strength", "each sign split in 9 of 3deg20'",
      ["Venus", "Jupiter"],
      "the most important varga after D1; it tests whether a D1 promise is real (vargottama = doubled)."),
 10: ("career, status & public karma", "each sign split in 10 of 3deg",
      ["Sun", "Saturn", "Mercury", "Jupiter"],
      "judges your work life; a strong D10 Lagna lord and 10th house show a powerful, visible career."),
 11: ("gains & income (Labha)", "non-classical: 11 parts from the planet's own sign",
      ["Jupiter"],
      "a dignified 11th lord favours steady gains, fulfilled desires and good income flow."),
 12: ("parents & lineage", "each sign split in 12 of 2deg30'",
      ["Sun", "Moon"],
      "Sun reads the father's line, Moon the mother's; their dignity shows what each parent gives."),
 16: ("vehicles, comforts & happiness", "each sign split in 16",
      ["Venus"],
      "a strong Venus / 4th lord favours luxury, conveyances and material ease."),
 20: ("spiritual practice & worship", "each sign split in 20",
      ["Jupiter", "Ketu"],
      "Jupiter and Ketu well-placed deepen devotion, discipline and inner growth."),
 24: ("education & learning", "each sign split in 24",
      ["Mercury", "Jupiter"],
      "Mercury and the 4th/5th lords show academic capacity and what is mastered."),
 27: ("innate strengths & weaknesses", "each sign split in 27 (the nakshatra-amsa)",
      ["Moon"],
      "reads raw vitality and resilience; a strong Lagna lord and Moon = robust constitution."),
 30: ("misfortunes, troubles & character", "each sign split in 30 of 1deg (uneven malefic scheme)",
      ["Mars", "Saturn", "Rahu"],
      "where the malefics fall warns of the kind of trouble; benefics here give protection and ethics."),
 40: ("maternal-line results", "each sign split in 40",
      ["Moon"],
      "Moon's dignity shows the gifts and karma inherited through the mother's family."),
 45: ("paternal-line & character", "each sign split in 45",
      ["Sun", "Jupiter"],
      "Sun and Jupiter show the values, conduct and karma carried from the father's line."),
 60: ("past-life karma (the finest layer)", "each sign split in 60 of 0deg30'",
      ["Lagna lord"],
      "the deepest varga; classically weighted heavily, it colours the karmic backdrop of the whole life."),
}
NONCLASSICAL = {5, 6, 8, 11}


def _parse_time(t):
    parts = [int(x) for x in t.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def compute(args):
    core.init_engine(ayanamsa=args.ayanamsa, node=args.node,
                     topocentric=not args.geocentric, lat=args.lat, lon=args.lon)
    y, m, d = [int(x) for x in args.date.split("-")]
    hh, mm, ss = _parse_time(args.time)
    jd = core.to_julian_ut(y, m, d, hh, mm, ss, args.tz)
    asc = core.ascendant(jd, args.lat, args.lon)
    positions = core.all_planet_positions(jd)
    lons = {name: positions[name]["longitude"] for name in core.PLANET_ORDER}
    lons["Lagna"] = asc["longitude"]
    points = list(core.PLANET_ORDER) + ["Lagna"]
    charts = {}
    for d_div in core.SUPPORTED_VARGAS:
        charts[d_div] = {pt: core.varga_sign(lons[pt], d_div) for pt in points}
    return charts


def requested(arg):
    arg = arg.strip().lower()
    if arg == "all":
        return list(core.SHODASAVARGA)
    if arg == "all+":
        return list(core.SUPPORTED_VARGAS)
    out = []
    for tok in arg.replace(" ", "").split(","):
        n = int(tok.lstrip("dD"))
        if n not in core.SUPPORTED_VARGAS:
            raise SystemExit(f"D{n} not supported. Supported: {core.SUPPORTED_VARGAS}")
        out.append(n)
    return out


def house_of(sign1, asc):
    return ((sign1 - asc) % 12) + 1


def reading_lines(n, ch):
    area, build, karakas, plain = V[n]
    asc = ch["Lagna"]
    asc_idx = asc - 1
    asc_lord = LORD[asc_idx]
    bysign = {}
    for p in PLANETS:
        bysign.setdefault(ch[p], []).append(p)
    exalted = [p for p in PLANETS if p not in ("Rahu", "Ketu") and dignity(p, ch[p] - 1) == "exalted"]
    debil = [p for p in PLANETS if p not in ("Rahu", "Ketu") and dignity(p, ch[p] - 1) == "debilitated"]
    own = [p for p in PLANETS if p not in ("Rahu", "Ketu") and dignity(p, ch[p] - 1) == "own sign"]
    al_sign = ch[asc_lord]
    al_dig = dignity(asc_lord, al_sign - 1)
    al_h = house_of(al_sign, asc)
    kfacts = []
    for k in karakas:
        if k == "Lagna lord":
            k = asc_lord
        if k in ch:
            ks = ch[k]
            kfacts.append((k, SIGNS[ks - 1], dignity(k, ks - 1), house_of(ks, asc)))
    with_asc = [PL_ABBR[p] for p in bysign.get(asc, [])]
    key = "D%d" % n + ("  (non-classical)" if n in NONCLASSICAL else "")
    L = [("h", f"{key}  -  {area}")]
    L.append(("b", "What it shows:  " + area + "."))
    L.append(("b", "How it is built:  " + build +
              ". Each planet's fine longitude lands in one sub-part, which maps to a sign here."))
    tech = f"Lagna = {SIGNS[asc_idx]} (lord {asc_lord}). That lord sits in {SIGNS[al_sign - 1]} ({al_dig}), house {al_h}."
    if with_asc:
        tech += "  With the Lagna: " + ", ".join(with_asc) + "."
    if exalted:
        tech += "  Exalted: " + ", ".join(exalted) + "."
    if own:
        tech += "  Own sign: " + ", ".join(own) + "."
    if debil:
        tech += "  Debilitated: " + ", ".join(debil) + "."
    L.append(("b", "Technical read:  " + tech))
    if kfacts:
        ks = "; ".join(f"{k} in {sg} ({dg}), house {h}" for k, sg, dg, h in kfacts)
        L.append(("b", f"Significator(s) for this area:  {ks}."))
    lordbias = {"exalted": 2, "own sign": 2, "friendly": 1, "neutral": 0,
                "node": 0, "enemy": -1, "debilitated": -2}.get(al_dig, 0)
    score = len(exalted) * 2 + len(own) - len(debil) + lordbias
    verdict = ("STRONG" if score >= 3 else "MODERATE-to-strong" if score >= 1
               else "MIXED / neutral" if score == 0 else "TENDER (needs support)")
    L.append(("b", f"How we deduce it:  weigh (1) the Lagna-lord {asc_lord}'s dignity ({al_dig}), "
                   f"(2) the area significator(s) above, and (3) how many planets are exalted/own vs "
                   f"debilitated ({len(exalted) + len(own)} dignified, {len(debil)} debilitated). "
                   f"Net read: {verdict}."))
    L.append(("p", "In plain words:  " + plain))
    return L


# ---------- PDF rendering ----------

def draw_grid(pdf, x, y, size, n, ch):
    asc = ch["Lagna"]
    bysign = {}
    for p in PLANETS:
        bysign.setdefault(ch[p], []).append(PL_ABBR[p])
    cell = size / 4.0
    pdf.set_draw_color(150, 150, 150)
    pdf.set_line_width(0.2)
    for (r, c), sign in SI_LAYOUT.items():
        cx, cy = x + c * cell, y + r * cell
        pdf.rect(cx, cy, cell, cell)
        pdf.set_xy(cx + 0.5, cy + 0.4)
        pdf.set_font("Helvetica", "", 4.6)
        pdf.set_text_color(130, 130, 130)
        pdf.cell(cell - 1, 2, ABBR[sign - 1] + ("*" if sign == asc else ""))
        pdf.set_text_color(0, 0, 0)
        pls = bysign.get(sign, [])
        if pls:
            pdf.set_font("Helvetica", "B", 5.4)
            pdf.set_xy(cx + 0.5, cy + cell / 2 - 1.4)
            pdf.multi_cell(cell - 1, 2.2, " ".join(pls), align="C")
    cx, cy = x + cell, y + cell
    pdf.set_draw_color(205, 205, 205)
    pdf.rect(cx, cy, cell * 2, cell * 2)
    pdf.set_xy(cx, cy + cell - 2)
    pdf.set_font("Helvetica", "B", 6)
    pdf.set_text_color(175, 175, 175)
    pdf.cell(cell * 2, 4, "D%d" % n, align="C")
    pdf.set_text_color(0, 0, 0)


def render_pdf(args, charts, divisions, out):
    from fpdf import FPDF
    show_readings = not args.no_readings
    pdf = FPDF("P", "mm", "A4")
    pdf.set_auto_page_break(False)
    pdf.set_title(f"{args.name} - Divisional Charts (Varga)")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(140, 60, 20)
    pdf.cell(0, 9, f"{args.name} - Divisional Charts" + (", Explained" if show_readings else ""),
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "I", 9.5)
    pdf.set_text_color(90, 90, 90)
    basis = f"{args.ayanamsa.title()} / {'geocentric' if args.geocentric else 'topocentric'}"
    pdf.cell(0, 5.5, f"{len(divisions)} vargas - South Indian style - {basis} - {args.on}",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)
    if show_readings:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, "How to read this document", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.3)
        pdf.multi_cell(0, 4.2,
            "A divisional (varga) chart magnifies ONE area of life. We take each planet's exact longitude, "
            "cut its 30deg sign into N equal parts (N = the chart number), and see which part it falls in; "
            "that part maps to a sign in the new chart. We judge the area by three things: (1) the new chart's "
            "Lagna (ascendant) and its ruling planet's dignity, (2) the natural significator (karaka) for that area "
            "- Venus for marriage, Sun/Saturn for career, Jupiter for children, and (3) how many planets are "
            "dignified (exalted / own sign) versus debilitated. 'Exalted' = a planet's best sign, 'debilitated' = "
            "its weakest, 'own sign' = it rules where it sits. In each grid the sign sits top-left of the box and "
            "'*' marks that chart's Lagna; planets are Su Mo Ma Me Ju Ve Sa Ra Ke.")
        pdf.ln(1)
    pdf.set_font("Helvetica", "I", 7.6)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(0, 3.6,
        "D5/D6/D8/D11 are non-classical extras (sign-mapping varies by tradition). The verdict is a transparent "
        "rule-of-thumb, not a classical Vimshopaka or a final judgment. For cultural and educational use only - "
        "astrology is not scientifically validated and must not drive medical, financial, or legal decisions.")
    pdf.set_text_color(0, 0, 0)

    grid = 48.0
    if show_readings:
        for i, n in enumerate(divisions):
            top = 16 if i % 2 == 0 else 158
            if i % 2 == 0:
                pdf.add_page()
            draw_grid(pdf, 14, top + 4, grid, n, charts[n])
            tx = 14 + grid + 8
            tw = 210 - tx - 12
            pdf.set_xy(tx, top)
            for kind, txt in reading_lines(n, charts[n]):
                pdf.set_x(tx)
                if kind == "h":
                    pdf.set_font("Helvetica", "B", 11)
                    pdf.set_text_color(140, 60, 20)
                    pdf.multi_cell(tw, 5.5, txt)
                    pdf.set_text_color(0, 0, 0)
                    pdf.ln(0.5)
                elif kind == "p":
                    pdf.set_font("Helvetica", "BI", 8.4)
                    pdf.set_text_color(30, 90, 40)
                    pdf.multi_cell(tw, 4.0, txt)
                    pdf.set_text_color(0, 0, 0)
                    pdf.ln(0.3)
                else:
                    pdf.set_font("Helvetica", "", 8.2)
                    pdf.multi_cell(tw, 4.0, txt)
                    pdf.ln(0.3)
            if i % 2 == 0:
                pdf.set_draw_color(220, 220, 220)
                pdf.line(14, 150, 198, 150)
    else:
        # compact: 6 grids per page
        col_x = [18, 115]
        per = 6
        for i, n in enumerate(divisions):
            slot = i % per
            if slot == 0:
                pdf.add_page()
                base = 22
            row = slot // 2
            col = slot % 2
            y = base + row * 80
            pdf.set_xy(col_x[col], y - 5)
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(140, 60, 20)
            pdf.cell(60, 4, "D%d - %s" % (n, V[n][0]))
            pdf.set_text_color(0, 0, 0)
            draw_grid(pdf, col_x[col], y, 58, n, charts[n])
    pdf.output(out)
    return out


def render_html(args, charts, divisions, out):
    rows = []
    for n in divisions:
        ch = charts[n]
        cells = []
        bysign = {}
        for p in PLANETS:
            bysign.setdefault(ch[p], []).append(PL_ABBR[p])
        for r in range(4):
            for c in range(4):
                if (r, c) in SI_LAYOUT:
                    sign = SI_LAYOUT[(r, c)]
                    star = "*" if sign == ch["Lagna"] else ""
                    pls = " ".join(bysign.get(sign, []))
                    cells.append(f"<td><small>{ABBR[sign-1]}{star}</small><br><b>{pls}</b></td>")
                elif (r, c) == (1, 1):
                    cells.append(f'<td rowspan=2 colspan=2 class=ctr>D{n}</td>')
                elif (r, c) in ((1, 2), (2, 1), (2, 2)):
                    continue
        grid = "<table class=g>" + "".join(
            "<tr>" + "".join(cells[r * 4:r * 4 + 4]) + "</tr>" if False else "" for r in range(4)) + "</table>"
        # simpler: rebuild row by row
        grid = "<table class=g>"
        idx = 0
        for r in range(4):
            grid += "<tr>"
            for c in range(4):
                if (r, c) in SI_LAYOUT:
                    sign = SI_LAYOUT[(r, c)]
                    star = "*" if sign == ch["Lagna"] else ""
                    pls = " ".join(bysign.get(sign, []))
                    grid += f"<td><small>{ABBR[sign-1]}{star}</small><br><b>{pls}</b></td>"
                elif (r, c) == (1, 1):
                    grid += f'<td rowspan=2 colspan=2 class=ctr>D{n}</td>'
            grid += "</tr>"
        grid += "</table>"
        read = ""
        if not args.no_readings:
            for kind, txt in reading_lines(n, ch):
                tag = "h3" if kind == "h" else ("em" if kind == "p" else "p")
                read += f"<{tag}>{txt}</{tag}>"
        rows.append(f"<section>{grid}<div class=r>{read}</div></section>")
    html = ("<html><head><meta charset=utf-8><style>"
            "body{font-family:sans-serif;margin:24px;color:#222}"
            "h1{color:#8c3c14}section{display:flex;gap:16px;border-bottom:1px solid #eee;padding:12px 0}"
            "table.g{border-collapse:collapse}td{border:1px solid #aaa;width:42px;height:42px;"
            "text-align:center;font-size:11px}td.ctr{color:#aaa}.r{flex:1;font-size:13px}"
            "h3{color:#8c3c14;margin:.2em 0}em{color:#1e5a28}</style></head><body>"
            f"<h1>{args.name} - Divisional Charts</h1>" + "".join(rows) +
            "<p><small>Cultural/educational use only - not scientifically validated.</small></p></body></html>")
    with open(out, "w") as f:
        f.write(html)
    return out


def main():
    ap = argparse.ArgumentParser(description="Shareable divisional-chart atlas (PDF/HTML) with per-chart readings.")
    ap.add_argument("--name", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--charts", default="all+", help="e.g. 'D9,D10', 'all' (16), 'all+' (20). Default all+")
    ap.add_argument("--no-readings", action="store_true", help="grids only, no interpretive text")
    ap.add_argument("--on", default=date.today().isoformat())
    ap.add_argument("--format", default="auto", choices=["auto", "pdf", "html"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--ayanamsa", default=core.DEFAULT_AYANAMSA)
    ap.add_argument("--node", default="mean", choices=["mean", "true"])
    ap.add_argument("--geocentric", action="store_true",
                    help="use geocentric positions (most Indian software does; shifts the Moon ~up to 1deg)")
    args = ap.parse_args()

    charts = compute(args)
    divisions = requested(args.charts)
    safe = args.name.replace(" ", "_")
    fmt = args.format
    out = args.out
    if fmt == "auto":
        try:
            import fpdf  # noqa: F401
            fmt = "pdf"
        except Exception:
            fmt = "html"
    if not out:
        out = f"./{safe}_vargas_{args.on}.{ 'pdf' if fmt == 'pdf' else 'html'}"
    if fmt == "pdf":
        try:
            render_pdf(args, charts, divisions, out)
        except ImportError:
            out = os.path.splitext(out)[0] + ".html"
            render_html(args, charts, divisions, out)
    else:
        render_html(args, charts, divisions, out)
    print("Report written:", out)


if __name__ == "__main__":
    main()

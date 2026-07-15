# 🪔 Astro Claude — Vedic Astrology & Numerology Claude Code Skills (Jyotish + Ank Jyotish)

> **Astro Claude, for the seeker** — a free, guided Vedic-astrology reader. It asks
> your name, birth details, and a couple of life questions, then gives one warm,
> plain-language reading with real depth: where you are in life now, your career
> and whether you'll thrive away from your birthplace, a good time to take a new
> job, which gemstones to **wear vs. avoid** for *your* ascendant, and whether you
> can wear a Rudraksha — every point backed by the astrological reasoning, with
> planets named in Hindi.

Offline **Vedic / Hindu astrology** and **numerology** skills for
[Claude Code](https://claude.com/claude-code). Read **today's sky** (panchang +
how every planet is aligned now), cast a birth chart, compute dasha periods,
generate the daily panchang (with Rahu Kaal & sunrise), detect classical
yogas, score planetary strength (Ashtakavarga + Shadbala), match horoscopes
(36-point Guna Milan), scan for doshas (Manglik, Kaal Sarpa), and run a full
numerology profile — entirely on your machine, **with no API keys and no network
calls**.

This repo ships **two sibling skills**: `vedic-astrology/` (ephemeris-based) and
`numerology/` (pure arithmetic), plus a bundled offline **city geocoder**.

All planetary math is done with the [Swiss Ephemeris](https://www.astro.com/swisseph/)
in **sidereal (Vedic) mode**, using the **Lahiri ayanamsa** by default.

> ⚠️ **For cultural, educational, and entertainment use only.** Vedic astrology
> is not a scientifically validated predictive method. Do not use it for medical,
> financial, legal, or other consequential decisions.

---

## ✨ Features

| Command | What it computes |
|---------|------------------|
| **Astro Claude** (`astro_claude.py`) | **The guided seeker's reading** — **opens with today's Panchang + how the stars are aligned today**, then name + age + life stage, career & working-away-from-home analysis, a good time to join a job, **gemstone WEAR/AVOID for your Lagna**, and Rudraksha advice — all reasoned, Hindi planet names |
| **Full report** (`full_report.py`) | A single **shareable PDF** (via fpdf2) or **HTML** bundling the whole reading — **opens with today's Panchang + sky alignment** — plus birth-chart table + South/North Indian kundli diagram |
| **Kundli** (`kundli.py`) | D1 Rashi chart — sidereal positions, signs, whole-sign houses, Lagna, nakshatra + pada, **D9 navamsa**, dignity, **vargottama** & **combustion** flags, retrogrades |
| **Vimshottari Dasha** (`dasha.py`) | 120-year Mahadasha / Antardasha / **Pratyantardasha** timeline from the Moon's nakshatra |
| **Yogini Dasha** (`dasha_yogini.py`) | The **36-year**, 8-Yogini cycle (Mangala…Sankata) with antardashas — a companion timing system to cross-read against Vimshottari |
| **Dasha Effects** (`dasha_predict.py`) | **Chart-aware interpretation** of the *currently running* period — effects on daily life, mind, career, money, marriage, health, family, enemies, education & spirituality. Personalised by house placement, lordship, dignity, combustion & the Maha↔Antar relationship |
| **Today's Sky** (`sky.py`) | **The opening view** — today's **Panchang** + a detailed read of **how every graha is aligned now** (sign, nakshatra, retrograde, combustion, conjunctions, slow-mover backdrop). No birth chart needed; optionally personalised (house-from-Moon + Sade Sati) |
| **Panchang** (`panchang.py`) | The five limbs (Tithi, Nakshatra, Yoga, Karana, **sunrise-based Vara**) plus **sunrise/sunset, Rahu Kaal, Yamaganda, Gulika, Abhijit muhurta** |
| **Yogas** (`yogas.py`) | **Aspect-aware** detection (Vedic drishti, not just conjunction) across the major families: Gajakesari, Budhaditya, Chandra-Mangala, the five Pancha Mahapurusha, Raja, Dhana, the lunar yogas (Sunapha/Anapha/Durudhara/Kemadruma), Adhi, Amala, Vipareeta Raja, Neecha Bhanga, Parivartana, Daridra, Shakata, and the Nabhasa Sankhya/Ashraya yogas |
| **Strength** (`strength.py`) | **Ashtakavarga** (BAV + SAV, verified to 337) and the **complete six-fold Shadbala** (Sthana, Dig, Kala, Cheshta, Naisargika, Drik — every source computed, methods documented) |
| **Vargas** (`varga.py`) | Full **Shodasavarga** (16 divisional charts) — D9 marriage, **D10 career**, D7 children, D2 wealth, D24 education, D30 adversity, D60 — plus cross-varga dignity counts & strength, and **4 optional non-classical divisions** (D5/D6/D8/D11, clearly labelled) |
| **Transits** (`gochar.py`) | **Gochar** from the natal Moon, **Sade Sati** & Dhaiya detection, slow-planet transits, and transit graded by natal Ashtakavarga bindus |
| **Bhava report** (`houses.py`) | House-by-house: sign, lord + lord's placement/dignity, occupants **with a Graha-in-Bhava reading for each (all 9 planets × 12 houses)**, aspecting planets, and natural karaka |
| **Rectification** (`rectify.py`) | **Birth-time rectification** by event-fitting — ranks candidate times against your dated life events (dasha + transit fit) and scans Lagna-sensitivity. Honest best-fit, never an "exact" calculation |
| **Remedies** (`remedies.py`) | Traditional **upaya** (deity, mantra, gemstone, charity) for the dasha lord + weak/afflicted planets — *cultural only, clearly disclaimed* |
| **Mantra guidance** (`mantra.py`) | **Goal-specific mantras** (wealth, success, marriage, health, education, children, protection, peace, spirituality) — a deity mantra + the chart's planetary beej mantra (strengthen/pacify) with weekday & japa count |
| **Chart diagram** (`chart.py`) | ASCII **North-Indian** (diamond) & **South-Indian** (grid) kundli for any varga |
| **Matching** (`matching.py`) | **Guna Milan** (36-point Ashtakoot), **Manglik** (Mangal Dosha), **Kaal Sarpa Dosha** |
| **Geocoder** (`geocode.py`) | Offline city → latitude / longitude / IANA timezone (bundled GeoNames dataset) |
| **Muhurta** (`muhurta.py`) | **Electional timing** — ranks the best days in a range for marriage, business, vehicle, house, travel, contracts, surgery… by vara/tithi/nakshatra/yoga/karana (+ Tara & Chandra Bala with birth), Abhijit window, Rahu-Kaal avoid |
| **Avoid / don'ts** (`avoid.py`) | **What NOT to do** today or across a week — Rahu Kaal/Yamaganda/Gulika windows, Vishti (Bhadra), Rikta tithi & Amavasya, harsh yogas, tikshna nakshatras, **Panchak**, **Disha Shool** (direction not to travel), and — with birth — **Chandrashtama** & weak Tara/Chandra Bala, each mapped to concrete "refrain from…" actions |
| **Lucky profile** (`lucky.py`) | Lucky **day, colour, number, direction, metal, gem & deity** from your Lagna lord, Moon lord, yogakaraka + Moolank |
| **Answer Book** (`references/answer-book.md`) | Routes every seeker question (career, money, marriage, children, health, timing, legal…) to the right tool **and the chart factor behind the answer** |
| **Numerology** (`numerology/`) | Moolank, Bhagyank, Naamank (Chaldean + Pythagorean), name trinity (Expression / Soul Urge / Personality) + Maturity, Karmic Debt & Lessons, Lo Shu grid, Pinnacles & Challenges, personal year/month/day, two-person compatibility, lucky mobile/house/vehicle/business-name checker, name-correction hints |
| **Yantra** (`numerology/yantra.py`) | **Magic-square yantras** as text, JSON & printable **SVG** — personalised 4×4 birth yantra, the nine Navagraha planetary yantras (with bija mantras), and custom-number squares, plus a plain-language *how to use a yantra* guide |

Configurable **ayanamsa** (Lahiri / Raman / KP / Yukteshwar / Fagan-Bradley),
**house system** (Whole Sign / Placidus / Equal), **node** (mean / true), and
**topocentric** positions by default (geocentric optional).

---

## 📦 Installation

### 1. Install as a Claude Code skill

Copy the `vedic-astrology/` folder into your Claude Code skills directory:

```bash
git clone https://github.com/samarth1106/vedic-astrology-skill.git
cp -r vedic-astrology-skill/vedic-astrology ~/.claude/skills/
```

(Or, for a single project, drop it in `.claude/skills/` inside that project.)

### 2. Install the Python dependencies

```bash
cd ~/.claude/skills/vedic-astrology
pip install -r requirements.txt        # pyswisseph + pytz
```

That's it. The skill activates automatically when you ask Claude about a kundli,
horoscope, dasha, panchang, etc.

### Use the scripts directly (no Claude needed)

```bash
cd vedic-astrology/scripts

python3 kundli.py   --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata
python3 dasha.py    --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --levels 2
python3 dasha_yogini.py --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --levels 2
python3 dasha_predict.py --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --on 2026-06-04
python3 varga.py    --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --charts D9,D10
python3 gochar.py   --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --on 2026-06-04
python3 houses.py   --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --house 10
python3 remedies.py --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata
python3 chart.py    --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --style both --varga D1
python3 rectify.py  --date 1990-08-15 --approx-time 14:30 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --window 90 --step 3 --event 2015-06-20:marriage --event 2018-03-10:child
python3 panchang.py --date 2026-06-04                  --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata
python3 avoid.py    --date 2026-06-08 --days 7         --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata --birth-date 1990-08-15 --birth-time 14:30:00
python3 sky.py      --date 2026-06-04                  --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata
python3 yogas.py    --date 1990-08-15 --time 14:30:00 --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata

# add --json to any command for machine-readable output
```

---

## 🗣️ Talking to Claude

Once installed, just ask naturally:

> "Cast my kundli — born 15 Aug 1990, 2:30 PM, in New Delhi."
>
> "What's my current Vimshottari dasha?"
>
> "I'm in Mercury–Venus dasha — how will it affect my career, money, and marriage?"
>
> "Am I going through Sade Sati right now? What are the transits doing?"
>
> "Show my D10 career chart and read my 10th house."
>
> "Draw my kundli in North Indian style."
>
> "How are the stars aligned today? Give me today's sky and panchang."
>
> "Give me today's panchang for Mumbai."
>
> "Which yogas are in this chart?"

Claude will ask for any missing birth details (it needs **date, exact local time,
latitude, longitude, and IANA timezone**) and then run the right script.

---

## 📥 Inputs explained

| Input | Format | Example | Notes |
|-------|--------|---------|-------|
| Date | `YYYY-MM-DD` | `1990-08-15` | Local birth date |
| Time | `HH:MM[:SS]` (24h) | `14:30:00` | **Local clock time at the birthplace.** The ascendant moves ~1° every 4 minutes, so accuracy matters. |
| Latitude | decimal degrees | `28.6139` | North positive |
| Longitude | decimal degrees | `77.2090` | **East positive, West negative** |
| Timezone | IANA name | `Asia/Kolkata` | Not a numeric offset like `+5:30` |

**Unknown birth time?** The Moon sign, dasha, and houses become unreliable. Use a
noon default only for sign-level information, and treat the Lagna/houses as invalid.
If you know *roughly* when you were born and have a few dated life events, try
`rectify.py` — it ranks candidate times by how well each fits those events
(a best-fit estimate, not a guarantee).

---

## 🧮 How it works

```
vedic-astrology-skill/         # git repo (push this)
├── README.md  LICENSE  NOTICE  .gitignore
├── examples/sample-output.md
├── tests/test_cli.py           # golden-value regression suite
├── .github/workflows/ci.yml    # CI: pytest on py3.10–3.12
├── vedic-astrology/            # SKILL 1 — copy into ~/.claude/skills/
│   ├── SKILL.md
│   ├── requirements.txt        # pyswisseph, pytz
│   ├── data/cities.csv         # bundled GeoNames geocoder dataset
│   ├── scripts/
│   │   ├── core.py             # the ONLY place Swiss Ephemeris is configured
│   │   ├── astro_claude.py     # Astro Claude — the guided seeker's reading
│   │   ├── full_report.py      # shareable PDF/HTML report
│   │   ├── kundli.py  dasha.py  dasha_yogini.py  dasha_predict.py  panchang.py  yogas.py
│   │   ├── lucky.py  mantra.py  muhurta.py  avoid.py
│   │   ├── sky.py              # Today's Sky — panchang + planetary alignment (opening view)
│   │   ├── strength.py         # Ashtakavarga + Shadbala
│   │   ├── varga.py            # 16 Shodasavarga + 4 extra divisions + cross-varga strength
│   │   ├── gochar.py           # transits + Sade Sati
│   │   ├── houses.py           # bhava (house-by-house) report
│   │   ├── remedies.py         # traditional upaya (cultural only)
│   │   ├── chart.py            # North/South Indian ASCII chart
│   │   ├── rectify.py          # birth-time rectification by event-fitting
│   │   ├── matching.py         # Guna Milan + doshas
│   │   └── geocode.py          # offline city lookup
│   └── references/             # answer-book, astro-claude, dasha-effects, gochar,
│                               # interpretation, nakshatras, vargas, yogas
└── numerology/                 # SKILL 2 — stdlib only, no ephemeris
    ├── SKILL.md
    ├── scripts/numerology.py
    ├── scripts/yantra.py        # magic-square yantras (text / JSON / SVG)
    └── references/
        ├── numbers.md
        └── yantra.md            # what a yantra is + how to use one
```

## ✅ Tests

```bash
pip install pytest
pytest -q          # 68 golden-value checks (SAV=337, BAV totals, dasha closure,
                   # sign placements, Guna Milan bounds, weekday, geocoder…)
```

CI runs the suite on Python 3.10–3.12 on every push and PR.

- **`core.py` owns the engine.** Sidereal mode, ayanamsa, planet IDs, nakshatra
  and dasha constants, and local→UT time conversion all live in one file. It uses
  the built-in **Moshier ephemeris**, so no large `.se1` data files are needed.
- Longitudes are **sidereal**. Tithi uses the Moon−Sun difference (ayanamsa-independent);
  nakshatra and yoga use sidereal longitudes (ayanamsa-dependent).
- **Ketu** = Rahu + 180°; **Rahu** uses the mean lunar node.

### Accuracy & scope notes

- Yoga detection now spans the **major families** but is still not exhaustive
  (the Nabhasa Akriti/Dala yogas and many nakshatra/varga yogas remain) — see
  `references/yogas.md`.
- Panchang elements change through the day; the tool reports values at the given
  clock time. Vara (weekday) uses the civil date (Vedic days run sunrise-to-sunrise).
- Divisional charts (the 16 Shodasavarga, plus 4 optional non-classical extras
  D5/D6/D8/D11), today's-sky panchang/alignment, Ashtakavarga, transits/gochar,
  Sade Sati, bhava analysis, remedies, chart diagrams, and the complete six-fold
  Shadbala are now included. Still **not** covered: Jaimini Chara dasha,
  KP sub-lords, and Varshaphal (annual chart).
- The `varga.py` **VargaBala %** is the skill's own transparent dignity score,
  **not** the classical Vimshopaka — see `references/vargas.md`. The exact
  own/exalted/debilitated counts are the reliable figures.
- `remedies.py` is **traditional/cultural only** — not advice, no demonstrated
  effect; never buy gemstones on its basis.

---

## 📜 License

Licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)** — see
[`LICENSE`](LICENSE).

**Why AGPL and not MIT?** This skill depends on the Swiss Ephemeris, which is
dual-licensed under AGPL-3.0 *or* a paid commercial license. To stay
license-compatible, this project is AGPL-3.0. If you want to use it in a
closed-source or commercial product without AGPL obligations, obtain a
[Swiss Ephemeris Professional License](https://www.astro.com/swisseph/swephinfo_e.htm)
from Astrodienst AG. See [`NOTICE`](NOTICE) for full attribution.

*This licensing summary is provided in good faith and is not legal advice.*

---

## 🙏 Acknowledgements

- [Swiss Ephemeris](https://www.astro.com/swisseph/) by Astrodienst AG
- [pyswisseph](https://github.com/astrorigin/pyswisseph) Python binding
- The Lahiri ayanamsa follows the Indian government's Rashtriya Panchang standard.

## 🤝 Contributing

Issues and PRs welcome — especially additional yogas, divisional charts, and
sunrise-accurate panchang. By contributing you agree your contributions are
licensed under AGPL-3.0.

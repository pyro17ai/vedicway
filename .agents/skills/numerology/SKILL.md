---
name: numerology
description: Compute a numerology report offline from a birth date (and optional full name). Generates the Moolank (psychic/birth number), Bhagyank (destiny/life-path number), Naamank (name number in Chaldean and/or Pythagorean systems), the name trinity (Expression/Destiny, Soul Urge/Antaratma from vowels, Personality from consonants) and Maturity number, ruling planets, number compatibility via planetary friendships, the karmic layer (Karmic Debt 13/14/16/19 and Karmic Lessons from missing name values), the Lo Shu grid with strength/weakness arrows, Pinnacles and Challenges life-stage cycles, personal year/month/day and universal-year cycles, two-person (couple/relationship) compatibility, a lucky-number checker for mobile/house/vehicle/account numbers and business names, lucky attributes (gemstone/day/colors), and a name-correction hint. Also generates yantras (magic-square diagrams) — a personalised 4×4 birth yantra, the nine Navagraha planetary yantras, and custom-number yantras — as text, JSON, and printable SVG images, with a plain-language guide on what a yantra is and how to use one. Pure Python standard library — no ephemeris, no network, no dependencies. Use when the user says numerology, ank jyotish, life path number, destiny number, moolank, bhagyank, naamank, name number, soul urge, expression number, personality number, maturity number, karmic debt, karmic lesson, lo shu grid, pinnacle, challenge, personal year, personal month, personal day, lucky number, lucky mobile number, lucky house number, name compatibility, numerology match, couple compatibility, business name numerology, numerology report, Chaldean, Pythagorean, name correction, yantra, magic square, birth yantra, planetary yantra, navagraha yantra, surya/chandra/mangal/budh/guru/shukra/shani/rahu/ketu yantra, how to use a yantra, or make me a yantra.
license: AGPL-3.0
---

# Numerology (Ank Jyotish)

Offline numerology calculator. All math runs locally in pure Python — **only the
standard library, no ephemeris, no API keys, no network**. This module inherits
the repository's **AGPL-3.0** license.

> **Disclaimer — state this to the user when presenting results.** This skill is
> for cultural, educational, and entertainment purposes only. It is **not
> predictive** and must not be used for medical, financial, legal, or other
> consequential decisions.

## Required & optional inputs

| Input | Format | Required | Notes |
|-------|--------|----------|-------|
| Date  | `YYYY-MM-DD` | **Yes** | Date of birth. Drives Moolank, Bhagyank, Lo Shu, Pinnacles. |
| Name  | `"Full Name"` | No | Enables Naamank, name trinity, Maturity, compatibility, Karmic Lessons, name-correction. |
| Year  | `YYYY` | No | Enables the personal-year theme. |
| `--on`  | `YYYY-MM-DD` | No | Personal year/month/day + universal-year cycles for that date. |
| `--date2` | `YYYY-MM-DD` | No | Second person's DOB — adds two-person (couple) compatibility. `--name2` optional. |
| `--check-number` | digit string | No | Score a mobile/house/vehicle/account number vs the core numbers (`--check-kind`). |
| `--check-name` | `"Business Name"` | No | Score a business/brand name vs the core numbers. |

Only the date is required. Everything else degrades gracefully when omitted.

## The two name-number systems

- **Chaldean** — ancient system, values 1–8 only (no letter is assigned 9).
  Reports the *compound* number first, then reduces to a single digit.
- **Pythagorean** — modern A=1…I=9, J=1…R=9, S=1…Z=8 system.

Default `--system both` reports both. The first requested system is used for the
compatibility and name-correction logic.

## Routing — running the script

One script, `scripts/numerology.py`. It prints a clean text report by default and
accepts `--json` for machine-readable output.

```bash
cd scripts

# Full report (date + name + personal year, both systems)
python3 numerology.py --date 1990-08-15 --name "Albert Einstein" \
  --system both --year 2026

# Minimal (date only)
python3 numerology.py --date 1990-08-15

# Chaldean only, keep master numbers 11/22/33 unreduced where noted
python3 numerology.py --date 2000-02-29 --system chaldean --keep-master

# Personal cycles for a specific date (universal/personal year, month, day)
python3 numerology.py --date 1990-08-15 --on 2026-06-08

# Two-person (couple) compatibility
python3 numerology.py --date 1990-08-15 --name "Person A" \
  --date2 1991-06-09 --name2 "Person B"

# Lucky-number checks (mobile / house / vehicle / account, and a business name)
python3 numerology.py --date 1990-08-15 \
  --check-number "9876543210" --check-kind mobile \
  --check-name "Acme Labs"

# JSON output for further processing
python3 numerology.py --date 1990-08-15 --name "Albert Einstein" --json
```

### Flags

- `--date YYYY-MM-DD` — **required**, date of birth.
- `--name "Full Name"` — optional; enables name-based sections.
- `--system chaldean|pythagorean|both` — default `both`.
- `--year YYYY` — optional; adds the personal-year theme.
- `--keep-master` — keep 11/22/33 unreduced in Moolank/Bhagyank/Naamank where the
  reduction would otherwise pass through a master number. Ruling-planet lookups
  still use the fully reduced single digit.
- `--on YYYY-MM-DD` — add personal year/month/day + universal-year cycles for that date.
- `--date2 YYYY-MM-DD` / `--name2` — add two-person (couple) compatibility.
- `--check-number "digits"` / `--check-kind number|mobile|house|vehicle|account` —
  score an arbitrary number against the core numbers.
- `--check-name "Business Name"` — score a business/brand name against the core numbers.
- `--json` — emit JSON instead of the formatted text report.

## Yantras — `scripts/yantra.py`

A second script generates **numeric yantras** (magic-square diagrams) as text,
JSON, and **printable SVG images**. A magic square is a grid where every row,
column, and diagonal sum to the same total. Three kinds:

```bash
cd scripts

# Personalised 4×4 birth yantra from a date of birth (+ printable SVG)
python3 yantra.py --date 1990-08-15 --svg birth_yantra.svg

# A Navagraha planetary 3×3 yantra (surya/chandra/mangal/budh/guru/
#   shukra/shani/rahu/ketu) — prints its bija mantra + best day
python3 yantra.py --planet guru --svg guru_yantra.svg

# All nine planetary yantras at once (SVG path used as a filename prefix)
python3 yantra.py --planet all --svg navagraha

# A custom 3×3 magic square for any total (must be a multiple of 3)
python3 yantra.py --target 24 --svg lucky_yantra.svg

# JSON for further processing
python3 yantra.py --planet shani --json
```

- **Birth yantra (`--date`)** — 4×4; top row is day/month/century-part/year-part,
  every line sums to their total. Occasional zero/negative cells (small birth
  months) are mathematically fine — the square stays magic.
- **Planetary yantra (`--planet`)** — 3×3; Surya = the classical Lo Shu (sum 15),
  each later graha lifts the centre by one. Includes the traditional **bija
  (seed) mantra** and best weekday.
- **Custom yantra (`--target N`)** — 3×3 for any total `N` that is a multiple of 3.
- `--svg PATH` writes a decorative SVG (gated bhupura + lotus-petal ring + grid).

**Always offer the "how to use" guidance** — many people don't know what a yantra
is for. Load `references/yantra.md` and explain: what a yantra is (a focusing
diagram, not a prediction), which one fits the user's goal, and the simple daily
practice (face east/north, set an intention, soft-gaze the centre — *trataka* —
and repeat the mantra ~108×). Be honest that it is a contemplative/cultural aid
that complements real action, never replaces medical/financial/legal help.

## What the report contains

1. **Moolank** (psychic / birth number) — reduced day of birth, with ruling planet.
2. **Bhagyank** (destiny / life-path) — reduced sum of all DOB digits, shows the chain.
3. **Naamank** (name number) — compound + reduced, per requested system.
4. **Name trinity** (with a name) — **Expression / Destiny** (all letters, natural
   talents), **Soul Urge / Antaratma** (vowels, inner cravings), **Personality**
   (consonants, outer impression), plus the **Maturity** number (Life Path + Expression).
   Y counts as a vowel only when it has no adjacent vowel in its word.
5. **Ruling planet** — Sun/Moon/Jupiter/Rahu/Mercury/Venus/Ketu/Saturn/Mars for 1–9.
6. **Compatibility** — whether the Naamank is friend/neutral/enemy to the Moolank
   and Bhagyank, using planetary friendships, with a recommendation.
7. **Karmic layer** — **Karmic Debt** numbers (13/14/16/19 appearing as a core
   compound) and **Karmic Lessons** (the 1–9 values entirely absent from the name).
8. **Lo Shu grid** — digit placement, counts, missing numbers, and detected
   arrows of strength (line fully present) and weakness (line fully absent).
9. **Pinnacles & Challenges** — four life-stage peak themes and four challenge
   lessons, each with the age range it governs (derived from the reduced DOB).
10. **Personal year** (only with `--year`) — the 1–9 theme for that year.
11. **Personal cycles** (only with `--on`) — universal year, personal year/month/day.
12. **Lucky attributes** — gemstone, days, and colors for the Moolank's ruler.
13. **Name-correction hint** — if the name conflicts with a core number, the target
    single-digit Naamank values that are friends of *both* core numbers (principle
    only — the skill does not auto-generate spellings).
14. **Number check** (only with `--check-number`) — a mobile/house/vehicle/account
    number's compound + reduced value and whether it is friendly to the core numbers.
15. **Business/name check** (only with `--check-name`) — a brand name's number vs the core.
16. **Two-person compatibility** (only with `--date2`) — friend/neutral/enemy across
    both people's core (and optional name) numbers, with a 0–100% score and verdict.

## Presenting results

1. Run the script; relay the text table directly or use `--json` and reformat.
2. **Always restate the disclaimer** — this is non-predictive, cultural content.
3. For per-number meanings (keywords, strengths, challenges, lucky attributes) and
   the master-number notes, load `references/numbers.md` on demand.
4. Be honest about scope: numerology is a traditional symbolic system, not a
   measurement of anything. Name correction gives target *numbers* and the
   underlying principle, not specific spellings.

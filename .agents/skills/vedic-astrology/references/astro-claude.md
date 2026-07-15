# Astro Claude — the seeker's reading

`astro_claude.py` is the friendly front door. It runs the intake, then one
consolidated, plain-language reading with the astrological "why" behind every
statement. Planets are named in Hindi (Surya, Chandra, Mangal, Budh, Guru,
Shukra, Shani, Rahu, Ketu).

## Intake (always first)

Name · DOB · **exact** time · birthplace (→ geocode) · gender · married? · (optional)
working away from birthplace? · any specific question. See SKILL.md.

## Opens with today's sky (always)

Before the personal reading, every Astro Claude output **starts with today's
sky** — computed by `sky.py` and embedded as the first block:

- **The Hindu Panchang** for the day at the seeker's place — vara (weekday),
  tithi + paksha, the Moon's nakshatra, yoga, karana, sunrise/sunset, Rahu Kaal
  (avoid) and the auspicious Abhijit muhurta.
- **How the stars are aligned today** — the live sidereal position of all nine
  grahas (sign, nakshatra + pada), what is **retrograde** (review, don't force)
  or **combust** (dimmed), the **conjunctions** (shared-sign blends), and the
  **slow-mover backdrop** (Shani, Guru, Rahu/Ketu) that sets the era's tone.
- **Personalised** — each transiting graha is also counted as a house from the
  seeker's **natal Moon**, and Saturn's house-from-Moon flags **Sade Sati /
  Dhaiya** — so the shared sky is tied back to *them* before the reading narrows.

`sky.py` also stands alone (no birth chart) for "what's the panchang today" or
"how are the stars aligned now". It reuses `panchang.py` for the almanac.

## What it derives, and how

- **Age & life stage** — age from DOB to `--on`; mapped to a classical 12-year
  life-quarter narrative.
- **Running dasha** — current Mahadasha→Antardasha (from `dasha.py`). Pair with
  `dasha_predict.py` for the full life-area breakdown.
- **Sade Sati** — Saturn transiting the 12th/1st/2nd from the natal Moon.
- **Working away from birthplace** — the 4th house is home/native roots. Signals:
  4th lord in the 8th/9th/12th, **Rahu/Ketu in the 4th or 12th** (Rahu-in-12th is
  a classic foreign-settlement marker), non-node planets in the 12th, Moon in a
  dusthana. Two+ signals (or a strong foreign marker) ⇒ likely to settle away.
  Consequence framing: distance brings the growth, at the cost of distance from
  roots.
- **Good time to join a company** — scans upcoming Antardashas for lords that
  rule a career house (2/6/10/11) or are natural career significators (Guru,
  Budh, Surya) or the Yogakaraka, and lists those date windows with reasons. The
  user then picks the *day* by muhurta (benefic weekday, good tithi, avoid Rahu
  Kaal — `panchang.py`).

## Functional benefic/malefic — the basis for gemstone advice

Gemstone advice is computed from **house lordship for the seeker's own Lagna**,
not generically:

- **Yogakaraka** — one planet ruling both a trikona (5th/9th) AND a kendra
  (4th/7th/10th). Its gemstone is the single most auspicious to wear.
  (e.g. Saturn for Taurus/Libra, Mars for Cancer/Leo, Venus for Capricorn/Aquarius.)
- **Functional benefic** — the Lagna lord, and lords of the trikona (5th/9th) that
  don't also own a dusthana. Their gems support luck and strength → **WEAR**.
- **Functional malefic** — lords of the dusthana (6th/8th/12th) with no trikona
  rulership. Strengthening them with a gem amplifies their harmful side →
  **DON'T WEAR**.
- **Rahu/Ketu** gems (gomed, lehsunia) are intense and must be tested → not casual.

So the same gemstone is right for one ascendant and wrong for another — that is
why the advice is "with respect to planetary position", as it should be.

## Rudraksha

Rudraksha is Shiva's blessing and is considered **safe for everyone** — unlike
gemstones, it does not "backfire". 5-mukhi is universally fine. The script also
suggests the mukhi for the running-dasha planet (to strengthen a benefic, or
steady a malefic), and 7-mukhi during Sade Sati. Mukhi↔planet mappings vary by
tradition; the common set is used (Surya 1, Chandra 2, Mangal 3, Budh 4, Guru 5,
Shukra 6, Shani 7, Rahu 8, Ketu 9).

## Tone & honesty

Warm, simple, personal — but every claim carries its astrological reason. Astro
Claude is **free, cultural/educational/reflective only**, with no demonstrated
predictive power, and must never push anyone to spend money on gems or rituals.
Always close with the disclaimer.

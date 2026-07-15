# Interpretation Reference

Plain-language associations for relaying a chart. These are **traditional cultural
significations**, not predictions. Always pair interpretation with the disclaimer.

## The 9 Grahas (planets)

| Graha | Karaka (signifies) | Keywords |
|-------|--------------------|----------|
| Sun (Surya) | Soul, father, authority | Vitality, ego, leadership, status |
| Moon (Chandra) | Mind, mother, emotions | Feeling, comfort, the public, memory |
| Mars (Mangala) | Energy, siblings, courage | Drive, conflict, property, discipline |
| Mercury (Budha) | Intellect, speech | Logic, commerce, communication, wit |
| Jupiter (Guru) | Wisdom, children, fortune | Growth, teaching, ethics, optimism |
| Venus (Shukra) | Love, art, comforts | Relationships, beauty, luxury, taste |
| Saturn (Shani) | Discipline, longevity | Limits, labor, delay, endurance |
| Rahu (N node) | Ambition, the foreign | Obsession, innovation, disruption |
| Ketu (S node) | Detachment, the past | Spirituality, loss, mastery, mystery |

## The 12 Bhavas (houses)

| House | Name | Domain |
|-------|------|--------|
| 1 | Tanu | Self, body, vitality, overall direction |
| 2 | Dhana | Wealth, family, speech, food |
| 3 | Sahaja | Courage, siblings, effort, skills |
| 4 | Sukha | Home, mother, comfort, property, heart |
| 5 | Putra | Children, creativity, intellect, romance |
| 6 | Ari | Enemies, debts, disease, service, conflict |
| 7 | Yuvati | Partnership, marriage, business, others |
| 8 | Randhra | Transformation, longevity, secrets, inheritance |
| 9 | Dharma | Fortune, beliefs, guru, father, long travel |
| 10 | Karma | Career, status, action, public life |
| 11 | Labha | Gains, networks, aspirations, elder siblings |
| 12 | Vyaya | Loss, expenditure, foreign lands, liberation, sleep |

## The 12 Rashis (signs) and lords

| Sign | Element | Quality | Lord |
|------|---------|---------|------|
| Aries | Fire | Movable | Mars |
| Taurus | Earth | Fixed | Venus |
| Gemini | Air | Dual | Mercury |
| Cancer | Water | Movable | Moon |
| Leo | Fire | Fixed | Sun |
| Virgo | Earth | Dual | Mercury |
| Libra | Air | Movable | Venus |
| Scorpio | Water | Fixed | Mars |
| Sagittarius | Fire | Dual | Jupiter |
| Capricorn | Earth | Movable | Saturn |
| Aquarius | Air | Fixed | Saturn |
| Pisces | Water | Dual | Jupiter |

## Graha in Bhava (planet in house)

For *what a specific planet does in a specific house*, run **`houses.py`** — its
bhava report now prints a concise traditional reading for every planet occupying
a house (a `→ Planet: …` line in text, `occupant_readings` in `--json`), for all
nine grahas across the twelve houses. Tune each reading by the planet's **dignity**
(exalted/own strengthens it; debilitated/combust strains it), the **aspects** on
the house, and the **house lord's** placement — `houses.py` reports all four.

A house with no occupant is read through its **lord's** placement and the planets
**aspecting** it, not skipped.

## A simple reading order

1. **Lagna (1st house) & its lord** — overall constitution and life direction.
2. **Moon sign & nakshatra** — the emotional mind; the basis of dasha timing.
   See `nakshatras.md` for the Moon-nakshatra personality notes.
3. **Sun sign** — soul, vitality, the "Vedic sun-sign."
4. **Planet dignities** — exalted/own = strong; debilitated = challenged.
5. **House occupancy** — which planets sit in which bhavas, and what that means
   (run `houses.py` for the Graha-in-Bhava readings).
6. **Yogas** — notable combinations (see `yogas.md`).
7. **Current dasha** — which planetary period is active now (run `dasha.py` and,
   as a cross-check, the Yogini cycle via `dasha_yogini.py`).
8. **Strength** — confirm with the six-fold Shadbala + Ashtakavarga (`strength.py`).

## Dasha interpretation

A planet's Mahadasha colors that whole period with its significations; the running
Antardasha (sub-period) modifies it. E.g. a Jupiter–Venus period blends growth/
wisdom (Jupiter) with relationships/comfort (Venus). Keep it descriptive and
non-deterministic.

> Everything here is cultural tradition for educational/entertainment use only.

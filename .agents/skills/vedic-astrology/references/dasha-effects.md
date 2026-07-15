# Dasha Effects — interpretation model

`dasha_predict.py` turns a *running* Vimshottari period into a life-area reading.
It does not just print a planet's textbook meaning — it personalises it to the
chart. This file documents the model so Claude can explain or extend it.

## How a reading is layered

1. **Karaka layer (generic).** Each dasha lord has classical significations for
   ten life areas (below). These are the baseline.
2. **Chart layer (personal).** The lord's **house placement**, the **house(s) it
   rules** from the Lagna, its **dignity** (exalted / own / debilitated /
   neutral), and **combustion / retrogression** in *this* chart. This is what
   makes the reading specific to one person.
3. **Blend layer.** The **Mahadasha lord (backdrop)** sets the multi-year theme;
   the **Antardasha lord (active trigger)** times what surfaces now. Their
   **natural relationship** (friend / neutral / enemy — `core.NATURAL_RELATION`)
   says whether the two cooperate or clash. Nodes (Rahu/Ketu) act through the
   house they sit in and their dispositor, so their blends read as "karmic /
   unpredictable."

A dasha sets a **backdrop of probabilities, not certainties**. Always present it
with that caveat.

## Life areas (the ten columns)

`daily` · `mind` · `career` · `money` · `relationships` · `health` · `family` ·
`enemies` · `education` · `spirituality`

## Per-planet keyword summary

| Lord | Core theme | Strongest areas | Cautions |
|------|-----------|-----------------|----------|
| **Sun** | authority, status, self | career, daily, spirituality | ego, heart/eyes, clashes with authority |
| **Moon** | mind, public, mother | mind, family, relationships | moods, fluids, instability |
| **Mars** | energy, courage, conflict | enemies, career, health(risk) | anger, accidents, blood, disputes |
| **Mercury** | intellect, trade, speech | education, career, money | nerves, over-cleverness, scattered |
| **Jupiter** | wisdom, growth, fortune | money, education, relationships, spirituality | over-optimism, weight/liver |
| **Venus** | love, luxury, art | relationships, money, daily | indulgence, kidneys/reproductive |
| **Saturn** | duty, delay, endurance | career(slow), health(chronic) | fear, isolation, bones/joints, delays |
| **Rahu** | ambition, foreign, sudden | career(sudden), money(volatile) | obsession, deception, mystery illness |
| **Ketu** | detachment, moksha, endings | spirituality, education(research) | losses, separation, dissatisfaction |

## House significations used (Bhava)

1 self/body · 2 wealth/family/speech · 3 courage/siblings/communication ·
4 home/mother/property · 5 children/romance/education · 6 enemies/debts/disease ·
7 spouse/partnership/business · 8 sudden events/inheritance/occult ·
9 fortune/dharma/father/guru · 10 career/status/authority ·
11 gains/income/friends · 12 loss/expense/foreign/moksha.

**House quality:** kendra = {1,4,7,10} (prominent), trikona = {1,5,9}
(fortunate), dusthana = {6,8,12} (difficult but transformative), upachaya =
{3,6,10,11} (improve over time).

## Reading the chart layer

- A dasha lord **activates the houses it rules and the house it sits in.** Example:
  a Mercury dasha where Mercury rules the 1st & 4th and sits in the 7th channels
  self/home matters (1, 4) *through* partnership and public dealings (7).
- **Dignity tunes the volume:** exalted/own → results flow easily; debilitated →
  strained, delayed, under-delivering; combust → the lord's significations are
  weakened/obscured; retrograde → results turn inward and get revisited.
- **Dusthana lordship** (6/8/12) in an otherwise benefic dasha can quietly drain
  the good — name it, don't hide it.

## Scope / honesty

This is a curated, deterministic interpretation — not exhaustive jyotish. It
deliberately omits transit (gochar) triggers, divisional-chart confirmation,
ashtakavarga of the dasha lord, and yoga interactions. It is a *starting* reading,
to be confirmed against the whole chart. For cultural/educational use only.

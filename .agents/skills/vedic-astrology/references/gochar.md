# Transits (Gochar) & Sade Sati

`gochar.py` places the transiting planets against the natal chart. The classical
reference for gochar is the **natal Moon (Chandra Lagna)**, not the Lagna — the
script reports the house from both.

## Sade Sati

Saturn's ~7.5-year passage over the natal Moon and the signs on either side:

| Saturn's house from Moon | Phase |
|--------------------------|-------|
| 12th | Rising (onset) — expenses, sleep, letting-go themes |
| 1st (over the Moon) | Peak — heaviest pressure on mind, health, confidence |
| 2nd | Setting (release) — strain on finances/family, then relief |

**Dhaiya** (small panoti), ~2.5 years each:

| Saturn's house from Moon | Phase |
|--------------------------|-------|
| 4th | Ardhashtama Shani — home, mother, property, peace of mind |
| 8th | Ashtama Shani — health, obstacles, sudden disruption |

Sade Sati is a maturing pressure, not a doom sentence — the script and any
reading should frame it that way.

## Gochar good/bad houses (from the Moon)

Each planet has classically favourable houses to transit, counted from the Moon
(e.g. Jupiter is good in the 2/5/7/9/11; Saturn in the 3/6/11). The script labels
each transit "favourable" or "challenging" on this basis. This is the raw rule —
real practice also weighs **Vedha** (mutual obstruction) and the planet's natal
strength, which this v1 does not yet model.

## Transit through Ashtakavarga

A transit's payoff is gated by the **natal Sarvashtakavarga bindus** in the sign
being transited: a planet crossing a sign with **≥30 bindus** tends to deliver;
**≤25 bindus** tends to struggle. The script pulls the natal SAV (the same
verified computation as `strength.py`) and tags each transit strong/moderate/weak.

## Read transits WITH the dasha

Transits don't act alone — they trigger what the running **dasha** has set up.
The natural workflow is: `dasha_predict.py` for the backdrop, then `gochar.py`
for the timing on top. For cultural/educational use only.

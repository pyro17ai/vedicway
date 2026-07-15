# Predictive & advanced tools

How to read the outputs of `chalit.py`, `transit_timeline.py`, `av_transit.py`,
`varshaphal.py`, and `kp.py`. Load this when a question reaches beyond the natal
D1 into *timing*, *cusp accuracy*, or the *KP / Tajika* systems. Everything here is
for cultural and educational use only — state the disclaimer with any reading.

## Bhava Chalit (`chalit.py`) — is the house real?

Whole-sign houses (the skill default) equate sign = house, which is clean but
silently misfiles a planet sitting near a sign edge. The chalit chart draws real
Placidus/Sripati cusps and assigns each planet to the bhava whose cusp span
contains it.

- **Use it to QA a house claim before trusting it.** If a "10th-house Mercury
  (career)" becomes a 9th-house Mercury under cusps, the career reading is
  birth-time sensitive — flag that, don't assert.
- A planet flagged `shifted` is near a cusp; its house-based significations are
  the first thing to wobble if the birth time is even a few minutes off. Pair with
  `rectify.py`.
- Whole-sign remains the primary frame for sign-based logic (lordships, aspects);
  chalit is a cross-check on *house occupancy*, not a replacement.

## Transit timeline (`transit_timeline.py`) — what's coming

Lists the exact dates the slow, classically weighted planets (Jupiter, Saturn,
Rahu, Ketu) change sign within a range, the house each enters from the natal Moon
(the gochar reference), and Sade Sati / Dhaiya phases.

- **Read it WITH the dasha, not instead of it.** A transit triggers what the
  running Mahadasha/Antardasha already promises; an ingress in a barren dasha is a
  weaker event. Run `dasha_predict.py` for the backdrop.
- Retrograde planets can cross the same boundary 2-3 times (enter, retrograde back,
  re-enter) — the timeline shows each crossing; the *last* one is the settled
  ingress.
- Sade Sati phases (Saturn in the 12th/1st/2nd from the Moon) are periods of
  restructuring, not doom — say so, and never frame them as fate.

## Ashtakavarga transit (`av_transit.py`) — is the transit supported

Scores where a planet is transiting by the natal Ashtakavarga bindus of that sign.

- **SAV (Sarvashtakavarga) of the transited sign:** >= 30 supportive, <= 25
  strained, 26-29 mixed (average is 28; total across 12 signs is always 337).
- **The transiting planet's own BAV (Bhinnashtakavarga):** >= 4-5 bindus in that
  sign strengthens its own transit specifically.
- Use it to grade a transit flagged by the timeline: a Saturn ingress into a
  high-SAV sign is far easier than into a low-SAV one. It is a *modifier*, never a
  standalone verdict.

## Varshaphal (`varshaphal.py`) — the year ahead (Tajika)

The annual chart cast for the exact solar return (Sun back on its natal sidereal
longitude) for a chosen age.

- **Muntha** advances one sign per year from the natal Lagna; its house in the
  annual chart colours the year's theme. At ages that are multiples of 12 it
  returns to the natal Lagna sign.
- **Varshesha (year lord)** is the chief office-bearer for the year. Its final
  selection uses **Panchavargeeya Bala**, which this tool does NOT fully compute —
  it lists the five candidate office-bearers (Muntha lord, annual-Lagna lord,
  natal-Lagna lord, Tri-rashi lord, Dina/Ratri lord). Present them as candidates,
  not a decided lord. Do not invent the winner.
- The annual chart is a *yearly overlay* on the natal promise, read together with
  the running dasha — not a fresh fate.

## KP — Krishnamurti Paddhati (`kp.py`)

KP refines the chart with the **sub-lord**: each nakshatra is divided into nine
sub-parts in Vimshottari proportions, starting from the star (nakshatra) lord. The
sub-lord of a point is KP's single most decisive factor.

- **Cuspal Sub-Lord (CSL)** of a house governs whether that house's matters
  fructify; the planetary sub-lords drive significator analysis.
- **Ruling Planets** (day lord, Moon's & Lagna's rashi/star/sub lords) are the
  KP timing/horary tool.
- KP conventionally uses its **own ayanamsa** (KP-Newcomb) and **Placidus cusps**;
  `kp.py` defaults to `--ayanamsa kp`. Pass `--ayanamsa lahiri` only to align it
  with the rest of the skill, and say so — the sub-lords shift slightly between
  ayanamsas because a few arc-minutes can move a point across a narrow sub-segment.
- Full KP significator/fructification chains and horary (1-249) are beyond this
  tool's current scope; it provides the verified sub-lord layer they build on.

## The honest frame for all of the above

These tools compute classical factors precisely; they do **not** predict events.
Always state the factor (cusp / ingress / bindu / Muntha / sub-lord), then the
indication, then the disclaimer. Where an answer depends on another person's free
choice, an exact date, or a count, give indications only and say it is not
chart-determinable.

# Divisional charts (Vargas)

`varga.py` computes the **Shodasavarga** — the 16 classical divisions — for all
nine grahas and the Lagna, plus a cross-varga strength view.

## What each division is read for

| Dn | Name | Life area |
|----|------|-----------|
| D1 | Rashi | the whole life, body, self |
| D2 | Hora | wealth & resources (only Cancer/Leo possible) |
| D3 | Drekkana | siblings, courage, longevity |
| D4 | Chaturthamsa | fortune, property, home |
| D7 | Saptamsha | children & progeny |
| D9 | Navamsa | spouse, marriage, dharma, inner strength |
| D10 | Dasamsha | **career, status, karma** |
| D12 | Dwadasamsa | parents & lineage |
| D16 | Shodasamsa | vehicles, comforts, happiness |
| D20 | Vimsamsa | spiritual practice & worship |
| D24 | Chaturvimsamsa | education & learning |
| D27 | Bhamsa | strengths & weaknesses |
| D30 | Trimsamsa | misfortunes, troubles, health |
| D40 | Khavedamsa | maternal-line results |
| D45 | Akshavedamsa | paternal-line, character |
| D60 | Shashtiamsa | past-life karma, finest layer |

## Non-classical extra divisions (D5, D6, D8, D11)

Beyond the Shodasavarga, `varga.py` and `chart.py` can also compute four extra
divisions on request (`--charts D5,D6,D8,D11`, `--charts all+`, or `chart.py
--varga D11`):

| Dn | Name | Commonly read for |
|----|------|-------------------|
| D5  | Panchamsa | fame, power, authority, spiritual merit |
| D6  | Shashthamsa | health, disease, debts, adversity |
| D8  | Ashtamsa | sudden events, accidents, longevity, legacies |
| D11 | Rudramsa / Labhamsa | gains & income (Labha), also destruction (Rudra) |

**Honesty caveat — read this before using them.** These four are **not part of
the classical Shodasavarga**, and unlike D9/D10 their sign-mapping is **not
uniquely fixed** in the *Brihat Parashara Hora Shastra*; different traditions and
software use different rules. This skill therefore computes them with **one
transparent, documented convention**: the amsas are counted cyclically forward
from the planet's own sign (the same rule used for D12 / Dwadasamsa). They are
**always labelled "(non-classical)"** in the output, and are **excluded from the
cross-varga strength score** (which spans only the classical 16). If your
lineage uses a different scheme for any of these, treat this skill's result as
that one convention, not a canonical truth — `core.varga_sign()` is the single
place to change it.

## How to read them

- **Confirm the D1 promise in the relevant varga.** A strong 10th-house promise
  in D1 only delivers if the same planets/lords are also strong in **D10**.
  Marriage is judged in **D9**, children in **D7**, career in **D10**.
- **Vargottama** (a planet in the same sign in D1 and D9) is a notable strength —
  the `kundli.py` output already flags it.
- **Cross-varga strength.** The script reports, per planet: how many of the 16
  vargas it is own/exalted in (more = steady), how many it is debilitated in, a
  transparent **VargaBala %**, and a **Shadvarga score /20**.

## Honesty note on the strength numbers

- **VargaBala %** is the *skill's own transparent scheme*, NOT the classical
  Vimshopaka Bala. It scores each varga by the planet's dignity there
  (own/exalted 1.0, friend 0.66, neutral 0.5, enemy 0.33, debilitated 0.0) and
  averages over all 16. Use it as a relative comparison, not an absolute.
- **Shadvarga /20** uses the one well-established weighting (D1=6, D2=2, D3=4,
  D9=5, D12=2, D30=1) applied to the same dignity score. It approximates — does
  not reproduce — a full classical Shadvarga Vimshopaka.
- The **own/exalted and debilitated counts** are exact and unambiguous; lead with
  those when judging a planet's varga strength.

## Shareable atlas — `varga_report.py`

For a downloadable **atlas** of the divisional charts, use `varga_report.py`
(distinct from `full_report.py`, which renders only the D1 narrative). It draws
every requested varga as a South-Indian grid and, unless `--no-readings`, pairs
each with a five-part explainer: what the chart shows, how the amsa is built, a
technical read (divisional Lagna + its lord's dignity, who sits with the Lagna,
exalted/own/debilitated planets), the area significator (karaka) plus a
transparent three-factor verdict (STRONG / MODERATE / MIXED / TENDER), and a
plain-language takeaway. `--charts all+` = all 20; PDF needs `fpdf2`, else it
falls back to HTML. The verdict is a reproducible rule-of-thumb (Lagna-lord
dignity + karaka dignity + dignified-vs-debilitated count), **not** a classical
Vimshopaka or a final judgment — a real reading also weighs aspects and yogas.

## Reproducing a chart from other software (geocentric vs topocentric)

When verifying this skill's output against an externally-supplied chart (e.g. a
JSON or PDF from common Indian software), expect **every planet to match except
possibly the Moon**. Most Indian software computes **geocentric** positions,
while this skill defaults to **topocentric** (corrected for the observer's place
on Earth's surface). Topocentric correction is negligible for all grahas except
the Moon, where lunar parallax can shift the longitude by **up to ~1°**. If only
the Moon disagrees by tens of arc-minutes, re-run with `--geocentric` to match —
do **not** assume a data error. Because the Moon's nakshatra/pada usually survive
the shift, the Vimshottari dasha is normally unaffected (the exception is a Moon
sitting on a nakshatra boundary). Also note some sources encode degrees as
`DD°MM` (e.g. `14.57` = 14°57′), not decimal degrees.

## Engine

All amsa mappings live in `core.varga_sign(lon, D)`. The 16 Shodasavarga follow
the standard Parashari rules; the 4 extras (D5/D6/D8/D11) use the documented
cyclic convention above. D9 is verified to equal `core.navamsa_sign` across the
whole zodiac. Every division is built from the **sidereal (Lahiri by default)**
longitude — the ayanamsa is applied once, then inherited by all charts. For
cultural/educational use only.

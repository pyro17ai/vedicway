# Yogas — Definitions and Caveats

A **yoga** is a specific planetary combination said to produce a defined effect.
Classical texts (Brihat Parashara Hora Shastra, Phaladeepika, Saravali, etc.)
describe hundreds, often with overlapping or conflicting rules. This skill detects
a **broad, well-defined set** computable from the D1 (Rashi) chart — covering the
major families — but it is still not exhaustive. Absence of a yoga here does
**not** mean none exist — it means none from this set were found.

## Detected

### Gajakesari Yoga
- **Rule used:** Jupiter occupies a kendra (1st, 4th, 7th, or 10th house) *counted
  from the Moon*.
- **Tradition:** intelligence, good reputation, respect.
- **Caveat:** stricter versions require Jupiter to be strong/unafflicted.

### Budhaditya Yoga
- **Rule used:** Sun and Mercury in the same sign/house (conjunction).
- **Tradition:** intellect, communication, analytical skill.
- **Caveat:** some texts discount it if Mercury is combust (too close to the Sun).
  The skill **flags combustion** in the note when it applies.

### Chandra-Mangala Yoga
- **Rule used:** Moon and Mars in the same sign/house.
- **Tradition:** financial drive, enterprise.

### Pancha Mahapurusha Yogas
Five "great person" yogas, one per non-luminary classical planet:

| Yoga | Planet | Rule used |
|------|--------|-----------|
| Ruchaka | Mars | Mars exalted or in own sign **and** in a kendra |
| Bhadra | Mercury | Mercury exalted or own sign **and** in a kendra |
| Hamsa | Jupiter | Jupiter exalted or own sign **and** in a kendra |
| Malavya | Venus | Venus exalted or own sign **and** in a kendra |
| Sasa | Saturn | Saturn exalted or own sign **and** in a kendra |

- **Tradition:** pronounced strength of that planet's significations.

### Raja Yoga
- **Rule used:** a **kendra lord** (lord of house 1/4/7/10) is **associated** with a
  **trikona lord** (lord of house 1/5/9), counted from the Lagna. Association =
  conjunction **or** mutual/one-way Vedic aspect (graha drishti).
- **Tradition:** status, authority, success.
- **Caveat:** sign-exchange Raja yogas surface separately as **Parivartana Yoga**
  (below). Strength/affliction of the lords still matters and is not scored here.

### Dhana Yoga
- **Rule used:** a wealth-house lord (2nd/11th) is associated (conjunction or
  aspect) with a wealth/fortune-house lord (1/2/5/9/11).
- **Tradition:** accumulation of money, strongest in the dasha of the planets involved.

### Lunar yogas — Sunapha / Anapha / Durudhara / Kemadruma
Counted from the Moon, looking at planets **other than the Sun and the nodes**:
- **Sunapha:** planet(s) in the 2nd from the Moon — self-earned wealth, intelligence.
- **Anapha:** planet(s) in the 12th from the Moon — composed nature, wellbeing.
- **Durudhara:** both the 2nd **and** the 12th occupied — comfort and good means.
- **Kemadruma:** none of the 2nd, 12th, or the Moon's own sign occupied — an
  affliction yoga. **Easily cancelled** (a planet in a kendra from Moon/Lagna, the
  Moon in a kendra, etc.), so it is reported as a caution, not a verdict.
- These four are **mutually exclusive** by construction.

### Adhi Yoga
- **Rule used:** two or more natural benefics (Mercury/Jupiter/Venus) in the
  6th/7th/8th from the Moon.
- **Tradition:** leadership, status, dependable allies.

### Amala Yoga
- **Rule used:** a natural benefic in the 10th from the Lagna or the Moon.
- **Tradition:** a spotless reputation and lasting good name through work.

### Vipareeta Raja Yoga (Harsha / Sarala / Vimala)
- **Rule used:** the lord of a dusthana (6/8/12) is placed in a dusthana.
  Harsha = 6th lord, Sarala = 8th lord, Vimala = 12th lord.
- **Tradition:** a "reversal" — difficulty turning into gain, often after a crisis
  or through the undoing of rivals.

### Neecha Bhanga Raja Yoga
- **Rule used:** a planet is **debilitated**, and the debilitation is cancelled by
  at least one of: (a) the debilitation-sign lord (dispositor) is in a kendra from
  the Lagna or Moon; (b) the planet that is **exalted** in that same sign is in a
  kendra from the Lagna or Moon; (c) the dispositor is itself exalted.
- **Tradition:** the debilitation is lifted and can turn into a rise-after-struggle,
  especially in that planet's dasha.
- **Caveat:** classical texts list several more cancellation conditions; this uses
  the three most widely agreed.

### Parivartana Yoga (Maha / Khala / Dainya)
- **Rule used:** two planets occupy **each other's** signs (mutual reception).
  Classified by the houses involved: **Dainya** if a 6/8/12 house is involved,
  **Khala** if the 3rd is involved, otherwise **Maha** (between good houses).
- **Tradition:** the affairs of the two houses become linked — strongly supportive
  for Maha, mixed/effortful for Khala, struggling for Dainya.

### Daridra Yoga
- **Rule used:** the 11th (gains) lord falls in a dusthana (6/8/12).
- **Tradition:** a caution on gains/income leaking away. **Offset** by Dhana/Raja
  yogas and the lord's strength — weigh against the whole chart.

### Shakata Yoga
- **Rule used:** the Moon is in the 6th/8th/12th from Jupiter.
- **Tradition:** fortunes that rise and fall in cycles. Cancelled if the Moon is in
  a kendra from the Lagna.

### Nabhasa yogas — Sankhya & Ashraya
- **Sankhya (by sign-count):** the number of **distinct signs** the seven planets
  occupy — 1 Gola, 2 Yuga, 3 Soola, 4 Kedara, 5 Pasa, 6 Damini, 7 Veena. One always
  applies. Describes the overall spread/concentration of the personality.
- **Ashraya (by modality):** all seven planets in one modality — **Rajju** (movable,
  restless/enterprising), **Musala** (fixed, steady/determined), **Nala** (dual,
  adaptable). Rare.

## Dignity reference (used by Mahapurusha detection)

| Planet | Exalted in | Own sign(s) | Debilitated in |
|--------|-----------|-------------|----------------|
| Sun | Aries | Leo | Libra |
| Moon | Taurus | Cancer | Scorpio |
| Mars | Capricorn | Aries, Scorpio | Cancer |
| Mercury | Virgo | Gemini, Virgo | Pisces |
| Jupiter | Cancer | Sagittarius, Pisces | Capricorn |
| Venus | Pisces | Taurus, Libra | Virgo |
| Saturn | Libra | Capricorn, Aquarius | Aries |

## Not yet implemented (candidates for the future)

The Nabhasa **Akriti** yogas (shape-based: Gada, Sakata, Vajra, Yava, Kamala,
Vapi, Yupa, etc.) and **Dala** yogas; Kala Sarpa (covered separately in
`matching.py` as a dosha); Chandra/Surya Mangala edge variants; and the many
nakshatra-based and divisional-chart yogas. Strength-weighting of every detected
yoga (via Shadbala) is also a future refinement — for now, read each yoga
alongside `strength.py`.

> All effects listed are traditional cultural associations, not predictions of
> real-life outcomes.

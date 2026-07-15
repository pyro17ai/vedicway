# Astro Claude — the Answer Book (question → tool → reason)

This is the routing map for the seeker's real questions. Every row names the
**tool** to run and the **chart factor** (house, karaka, dasha, varga, transit,
or numerology) the answer rests on — so **no answer is ever given without its
astrological reason**. Always state the factor, then the reading, then the
disclaimer. Lead with `astro_claude.py` for any broad personal question; use the
specific tool to go deeper.

Honesty rule: where a question cannot be determined from a chart (loyalty,
certainty of a verdict, a person's free choice), say so plainly and give the
*indications* only — never a false certainty.

## Today & the Sky (no birth chart needed)
| Question | Tool | Factor / reason |
|---|---|---|
| How are the stars/planets aligned today | **sky** | live sidereal positions of all nine grahas — sign + nakshatra, retrograde/combust, conjunctions, slow-mover backdrop |
| What's the panchang today / now | sky, panchang | the five limbs (vara, tithi, nakshatra, yoga, karana) + sunrise, Rahu Kaal, Abhijit |
| Is today a good day generally | sky, panchang | tithi/vara quality, Rahu Kaal to avoid, Abhijit window; for a *specific* event use muhurta |
| What sign is the Moon/Sun/Saturn in now | sky | current transiting sign + nakshatra of any graha (the Moon sets the day's mood) |

> Astro Claude opens every personal reading with this same "today's sky" block,
> there personalised (house-from-natal-Moon + Sade Sati).

## Personal Life & Self
| Question | Tool | Factor / reason |
|---|---|---|
| Life purpose / soul mission | astro_claude, houses, varga | **Atmakaraka** (soul planet) + its house, the 10th (karma), 9th (dharma), D9 Lagna |
| Strengths & weaknesses | strength, varga, astro_claude | Shadbala + Ashtakavarga + cross-varga dignity; exalted vs debilitated/combust planets |
| Personality | kundli, houses | Lagna sign + lord, Moon sign, birth nakshatra, 1st-house occupants |
| Repeating patterns / karmic lessons | astro_claude, houses | **Rahu–Ketu axis** (the karmic spine), Saturn's house, 12th house |
| Future outlook | dasha_predict, gochar | running Mahadasha/Antardasha + current transits & Sade Sati |
| Will I be successful | yogas, houses, dasha | Raja yoga, 10th/11th strength, yogakaraka, supportive dasha |
| Obstacles despite hard work | houses, strength, gochar | 6/8/12 lords & occupants, low Shadbala of the karaka, Sade Sati, a malefic-lord dasha |
| Lucky numbers/colours/days/directions | **lucky**, numerology | Lagna lord + Moon lord + yogakaraka attributes; Moolank from birth day |
| Most important years | dasha, gochar | Mahadasha/Antardasha changes, Sade Sati, major Jupiter/Saturn transits |

## Career & Business
| Question | Tool | Factor / reason |
|---|---|---|
| Best career / which industry | varga (D10), houses | **Dasamsha (D10)**, 10th lord & its sign, planets in/aspecting the 10th, Amatya significations |
| Should I switch jobs / promotion timing | astro_claude, gochar | favourable upcoming Antardashas (lord of 2/6/10/11) + Jupiter transit to 10th/11th |
| Government job | houses, yogas | strong **Sun** + 10th, Sun–Saturn or Sun–Moon links, Raja yoga |
| Start a business vs job | houses | 7th (business/trade) & 3rd (enterprise) vs 6th (service/employment) strength |
| Partnership favourable | matching, houses | 7th house + partner-chart Guna Milan; 7th lord condition |
| Best time to launch | panchang, astro_claude | electional muhurta (tithi/vara/Rahu Kaal) within a supportive dasha |
| Business not growing | houses, gochar | 2/11 affliction, a 6/8/12-lord dasha, adverse transit; remedies |
| Lucky business name | numerology | Naamank (name number) vs Moolank/Bhagyank |
| Relocate / work abroad | astro_claude | 4th lord placement, **Rahu/Ketu in 4/12**, 12th occupants (away-from-home engine) |

## Money & Wealth
| Question | Tool | Factor / reason |
|---|---|---|
| Will I be wealthy | yogas, varga (D2), houses | **Dhana yoga**, Hora (D2), 2nd/11th lords & their dasha |
| When finances improve | astro_claude, dasha | Antardasha of 2/11/9 lords; Dhana-yoga planets' periods |
| Why losing money | houses, gochar | 12th (loss) & 6th (debt) activity, malefic-lord dasha, adverse transit |
| Inherit wealth | houses | 8th house (inheritance/legacies) & its lord |
| Good period for financial growth | dasha | dasha of wealth/fortune lords |
| Remove financial obstacles | remedies, mantra | gem/mantra/charity for the weak wealth-lord or dasha lord |
| Which mantra for wealth / success / a goal | **mantra** | goal-deity mantra (Lakshmi/Ganesha/Saraswati…) + the beej mantra of the planet ruling the goal's houses, strengthen-vs-pacify by functional nature |
| Numerology number for wealth | numerology | Moolank/Bhagyank wealth compatibility |
| Buy stocks/property/invest now | panchang, astro_claude | timing = muhurta + dasha + 5th (speculation)/4th (property) condition |

## Love, Relationships & Marriage
| Question | Tool | Factor / reason |
|---|---|---|
| When will I marry / find love | astro_claude, dasha, varga | 7th lord & Venus dasha/transit, **D9 (Navamsa)**, 7th-house activation |
| Compatibility with partner | **matching** | 36-point Guna Milan + Manglik + Nadi/Bhakoot (needs partner's birth data) |
| Love vs arranged marriage | houses | 5th (romance)/7th link, Venus–Rahu in 5/7 → love-leaning |
| Successful / harmonious marriage | varga (D9), houses | Navamsa strength, 7th-house benefics vs malefics, Venus/Jupiter |
| Delayed marriage / why | houses, matching | Saturn on 7th, 7th-lord affliction, **Manglik (Mangal dosha)** |
| Manglik / doshas | **matching** | Mars in 1/2/4/7/8/12, Kaal Sarpa |
| Divorce / second marriage | houses | 7th/8th afflictions, 2nd & 7th-lord condition (indicative only) |
| Is my partner loyal / will we reunite | — | **Not chart-determinable** — give only 7th-house indications, never a verdict |
| Reduce marriage obstacles | remedies | Venus/Jupiter/Mars remedies as indicated |

## Family & Children
| Question | Tool | Factor / reason |
|---|---|---|
| Will I / when will I have children | varga (D7), houses, dasha | **Saptamsha (D7)**, 5th house & lord, Jupiter (putrakaraka), 5th-lord dasha |
| Delays in childbirth | houses | malefics on 5th, Saturn/Ketu influence, afflicted Jupiter |
| Relationship with parents | houses, varga (D12) | 4th (mother)/9th (father), **Dwadasamsa (D12)** |
| Family conflict / harmony | houses | 2nd (family)/4th condition, malefic-lord dasha |
| Child's future | (separate chart) | needs the child's own birth details → run a fresh reading |

## Health
| Question | Tool | Factor / reason |
|---|---|---|
| Recurring health issues | houses, varga (D30) | 6th (disease)/8th (chronic), **Trimsamsa (D30)**, afflicted Sun/Moon (vitality) |
| Difficult health period ahead | dasha, gochar | dasha of 6/8/12 lord, Sade Sati, malefic transit to Lagna/Moon |
| Improve wellbeing / habits to avoid | dasha_predict, remedies | the health-area reading of the running dasha; remedies |
| Mental stress | houses | Moon (mind) condition, 12th, Sade Sati (always: see a real doctor) |

## Education
| Question | Tool | Factor / reason |
|---|---|---|
| Field of study / which course | varga (D24), houses | **Chaturvimsamsa (D24)**, 4th/5th, Mercury (learning)/Jupiter (wisdom) |
| Competitive exam success | houses, dasha | 5th & 9th strength, Mercury, supportive dasha/transit at exam time |
| Higher education / study abroad | houses, astro_claude | 9th house, 12th/Rahu (foreign), D24 |
| Struggling academically | houses, remedies | afflicted 5th-lord/Mercury, malefic-lord dasha; remedies |

## Property, Vehicles & Real Estate
| Question | Tool | Factor / reason |
|---|---|---|
| Buy / sell house, buy vs rent, when | varga (D4), houses, panchang | **Chaturthamsa (D4)**, 4th house (property) & Mars, muhurta for the transaction |
| Lucky property / city / direction | lucky, astro_claude | supportive-planet direction; away-from-home signals for city |
| Best house / vehicle / mobile number | numerology | number reduced vs Moolank/Bhagyank |
| Lucky vehicle colour / best day to buy | lucky, panchang | supportive-planet colour; muhurta day (Venus = vehicles) |
| Agricultural land favourable | houses | 4th & Mars, Saturn (land) condition |

## Travel & Relocation
| Question | Tool | Factor / reason |
|---|---|---|
| Settle abroad / immigration / foreign benefit | astro_claude | 12th (foreign), Rahu, 9th (long travel); away-from-home engine |
| Move cities / best time to relocate | astro_claude, panchang | away signals + a supportive dasha + muhurta |
| Which country | — | **Not precisely determinable** — give direction/foreign indications only |

## Spirituality
| Question | Tool | Factor / reason |
|---|---|---|
| Spiritual path / soul mission | astro_claude, varga (D20) | **Atmakaraka**, 9th/12th, Ketu, **Vimsamsa (D20)** |
| Karmas I carry / drawn to practices | houses | Rahu–Ketu axis, Saturn (karmic debt), 12th |
| Which deity / discipline suits me | remedies, lucky | Ishta from Atmakaraka/Lagna-lord; the planet's deity |
| Increase inner peace | dasha_predict, remedies | spirituality-area reading + the prescribed mantra/charity |

## Timing (the universal "best time to…")
Run **muhurta.py** with the event and a date range — it ranks the days by vara,
tithi, nakshatra, yoga and karana (and, with birth details, Tara & Chandra Bala)
and hands back the best window (Abhijit) plus the times to avoid (Rahu Kaal etc.).
Events: marriage, business, vehicle, house, education, travel, contract,
investment, surgery, general. For a single named day, **panchang.py** confirms the
muhurta. Also check the day falls inside a supportive **dasha** and clean
**transit**. Event-house keys: start
business → 10th/3rd; vehicle/marriage → Venus & 7th; invest → 5th/2nd; change job
→ 6/10; relocate → away-engine; sign contracts → Mercury/3rd; surgery → avoid Moon
in a tender sign & malefic tithis. "When will good times begin / difficulties
end" → read the **dasha sequence** (benefic vs malefic-lord periods) and the end
of **Sade Sati**.

## Legal & Litigation
| Question | Tool | Factor / reason |
|---|---|---|
| Win a court case / settle vs fight | houses, dasha | **6th house** (you vs opponent) strength relative to the 7th, lord dasha |
| When will it resolve | dasha, gochar | the period when the 6th/8th activation passes |
| Is this agreement favourable | houses, panchang | 7th (the other party), muhurta for signing — **indications only**, never a guarantee |

## Numerology-specific
All handled by the **numerology** sibling skill: destiny number (Bhagyank), life
path / radical (Moolank), name number (Naamank, Chaldean + Pythagorean), Lo Shu
grid, name-correction hints, personal year, and number compatibility for a
mobile/vehicle/house/business number or a date. **Signature style** is subjective
and **not computed** — say so.

## What Astro Claude will NOT pretend to answer
Loyalty of another person, certainty of a court verdict, another's free choices,
exact number of children, a precise foreign country, signature style. For these,
give the chart's *indications* and the reason — and be honest that the rest is
not determinable. This honesty is part of the reading, not a failure of it.

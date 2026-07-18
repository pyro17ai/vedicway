export type DemoPlanet = {
  id: string;
  name: string;
  glyph: string;
  rasiIndex: number;
  sign: string;
  degree: number;
  nakshatra: string;
  pada: number;
  additional?: boolean;
};

export type SouthIndianSign = {
  rasiIndex: number;
  name: string;
  glyph: string;
  row: number;
  column: number;
};

export const demoSnapshot = {
  profile: "Александр",
  date: "15 сентября 1998",
  time: "17:28",
  place: "Москва, Россия",
  timezone: "UTC+4",
  ayanamsa: "Lahiri",
  houseSystem: "Whole-sign",
  source: "Положения основной карты D1",
  ascendant: {
    sign: "Скорпион",
    signEn: "Scorpio",
    degree: 23.7133,
    nakshatra: "Джйештха",
  },
  moon: {
    sign: "Рак",
    degree: 25.7398,
    nakshatra: "Ашлеша",
    pada: 3,
  },
} as const;

export const southIndianSigns: SouthIndianSign[] = [
  { rasiIndex: 1, name: "Овен", glyph: "\u2648\uFE0E", row: 1, column: 1 },
  { rasiIndex: 2, name: "Телец", glyph: "\u2649\uFE0E", row: 1, column: 2 },
  { rasiIndex: 3, name: "Близнецы", glyph: "\u264A\uFE0E", row: 1, column: 3 },
  { rasiIndex: 4, name: "Рак", glyph: "\u264B\uFE0E", row: 1, column: 4 },
  { rasiIndex: 5, name: "Лев", glyph: "\u264C\uFE0E", row: 2, column: 4 },
  { rasiIndex: 6, name: "Дева", glyph: "\u264D\uFE0E", row: 3, column: 4 },
  { rasiIndex: 7, name: "Весы", glyph: "\u264E\uFE0E", row: 4, column: 4 },
  { rasiIndex: 8, name: "Скорпион", glyph: "\u264F\uFE0E", row: 4, column: 3 },
  { rasiIndex: 9, name: "Стрелец", glyph: "\u2650\uFE0E", row: 4, column: 2 },
  { rasiIndex: 10, name: "Козерог", glyph: "\u2651\uFE0E", row: 4, column: 1 },
  { rasiIndex: 11, name: "Водолей", glyph: "\u2652\uFE0E", row: 3, column: 1 },
  { rasiIndex: 12, name: "Рыбы", glyph: "\u2653\uFE0E", row: 2, column: 1 },
];

export const demoPlanets: DemoPlanet[] = [
  { id: "sun", name: "Солнце", glyph: "☉", rasiIndex: 6, sign: "Дева", degree: 28.9325, nakshatra: "Читра", pada: 2 },
  { id: "moon", name: "Луна", glyph: "☽", rasiIndex: 4, sign: "Рак", degree: 25.7398, nakshatra: "Ашлеша", pada: 3 },
  { id: "mars", name: "Марс", glyph: "♂", rasiIndex: 7, sign: "Весы", degree: 1.1571, nakshatra: "Читра", pada: 3 },
  { id: "mercury", name: "Меркурий", glyph: "☿", rasiIndex: 7, sign: "Весы", degree: 23.5851, nakshatra: "Вишакха", pada: 2 },
  { id: "jupiter", name: "Юпитер", glyph: "♃", rasiIndex: 7, sign: "Весы", degree: 27.6234, nakshatra: "Вишакха", pada: 3 },
  { id: "venus", name: "Венера", glyph: "♀", rasiIndex: 6, sign: "Дева", degree: 26.0182, nakshatra: "Читра", pada: 1 },
  { id: "saturn", name: "Сатурн", glyph: "♄", rasiIndex: 4, sign: "Рак", degree: 28.8553, nakshatra: "Ашлеша", pada: 4 },
  { id: "rahu", name: "Раху", glyph: "☊", rasiIndex: 12, sign: "Рыбы", degree: 1.1941, nakshatra: "Пурва Бхадрапада", pada: 4 },
  { id: "ketu", name: "Кету", glyph: "☋", rasiIndex: 6, sign: "Дева", degree: 1.1941, nakshatra: "Уттара Пхалгуни", pada: 2 },
  { id: "uranus", name: "Уран", glyph: "♅", rasiIndex: 11, sign: "Водолей", degree: 17.3422, nakshatra: "Шатабхиша", pada: 4, additional: true },
  { id: "neptune", name: "Нептун", glyph: "♆", rasiIndex: 10, sign: "Козерог", degree: 23.1242, nakshatra: "Шравана", pada: 4, additional: true },
  { id: "pluto", name: "Плутон", glyph: "♇", rasiIndex: 9, sign: "Стрелец", degree: 0.5803, nakshatra: "Мула", pada: 1, additional: true },
];

const houseSigns = [
  "Скорпион",
  "Стрелец",
  "Козерог",
  "Водолей",
  "Рыбы",
  "Овен",
  "Телец",
  "Близнецы",
  "Рак",
  "Лев",
  "Дева",
  "Весы",
];

export const wholeSignHouses = houseSigns.map((sign, index) => ({
  number: index + 1,
  sign,
  system: "whole-sign",
}));

export const classicalDrishti = [
  { glyph: "♄", label: "Сатурн → Дева", value: "3-й аспект", note: "из Рака" },
  { glyph: "♄", label: "Сатурн → Козерог", value: "7-й аспект", note: "из Рака" },
  { glyph: "♄", label: "Сатурн → Овен", value: "10-й аспект", note: "из Рака" },
  { glyph: "♂", label: "Марс → Козерог", value: "4-й аспект", note: "из Весов" },
  { glyph: "♂", label: "Марс → Овен", value: "7-й аспект", note: "из Весов" },
  { glyph: "♂", label: "Марс → Телец", value: "8-й аспект", note: "из Весов" },
  { glyph: "♃", label: "Юпитер → Водолей", value: "5-й аспект", note: "из Весов" },
  { glyph: "♃", label: "Юпитер → Овен", value: "7-й аспект", note: "из Весов" },
  { glyph: "♃", label: "Юпитер → Близнецы", value: "9-й аспект", note: "из Весов" },
] as const;

export const explanationCards = [
  {
    glyph: "ASC",
    title: "Лагна в Скорпионе",
    summary: "Восходящий знак задаёт первый whole-sign дом и каркас расположения домов.",
    fact: "Ascendant · Scorpio · 23,7133°",
    source: "Положения основной карты D1",
  },
  {
    glyph: "☽",
    title: "Луна в Раке",
    summary: "Лунный знак рассчитан в сидерическом зодиаке с айанамшей Lahiri.",
    fact: "Moon · Cancer · 25,7398°",
    source: "Положения основной карты D1",
  },
  {
    glyph: "✦",
    title: "Накшатра Ашлеша",
    summary: "Положение Луны попадает в Ашлешу, третью паду.",
    fact: "Moon · Ashlesha · pada 3",
    source: "Положения основной карты D1",
  },
  {
    glyph: "Ⅰ",
    title: "Дома whole-sign",
    summary: "Первый дом начинается со Скорпиона, следующие знаки занимают дома по порядку.",
    fact: "House 1 · Scorpio · whole-sign",
    source: "Связь положений основной карты D1",
  },
] as const;

export type QuestionTopic = "Все" | "Отношения" | "Работа" | "Деньги" | "Энергия" | "Смысл";

export type DemoQuestion = {
  glyph: string;
  title: string;
  prompt: string;
  topics: QuestionTopic[];
  fact: string;
  source: string;
  insufficient?: boolean;
};

export const questionTopics: QuestionTopic[] = ["Все", "Отношения", "Работа", "Деньги", "Энергия", "Смысл"];

export const demoQuestions: DemoQuestion[] = [
  {
    glyph: "☽",
    title: "Луна в Раке",
    prompt: "Какие условия помогают мне восстанавливать чувство внутренней опоры?",
    topics: ["Отношения", "Энергия"] as QuestionTopic[],
    fact: "Луна · Рак · 25,7398° · Ашлеша · пада 3",
    source: "Положения основной карты D1",
  },
  {
    glyph: "Ⅶ",
    title: "Отношения и седьмой дом",
    prompt: "Какие качества я ищу в партнёрстве и как проявляю взаимность?",
    topics: ["Отношения"] as QuestionTopic[],
    fact: "7 дом · Телец · whole-sign",
    source: "Связь положений основной карты D1",
  },
  {
    glyph: "♄",
    title: "Периоды и работа",
    prompt: "Какие периоды сильнее затрагивают карьерные решения и ответственность?",
    topics: ["Работа"] as QuestionTopic[],
    fact: "Основная карта готова, расчёт периодов ещё не завершён.",
    source: "Расчёт периодов Вимшоттари ещё готовится",
    insufficient: true,
  },
  {
    glyph: "Ⅱ",
    title: "Деньги и второй дом",
    prompt: "Какие привычки помогают мне устойчиво обращаться с ресурсами?",
    topics: ["Деньги"] as QuestionTopic[],
    fact: "2 дом · Стрелец · whole-sign",
    source: "Связь положений основной карты D1",
  },
  {
    glyph: "♂",
    title: "Марс и направление силы",
    prompt: "Куда я направляю усилие, когда нужно действовать решительно?",
    topics: ["Энергия", "Работа"] as QuestionTopic[],
    fact: "Марс · Весы · 1,1571° · Читра · пада 3",
    source: "Положения основной карты D1",
  },
  {
    glyph: "Ⅸ",
    title: "Смысл и девятый дом",
    prompt: "Какие идеи помогают мне выстраивать личную систему ориентиров?",
    topics: ["Смысл"] as QuestionTopic[],
    fact: "9 дом · Рак · whole-sign",
    source: "Связь положений основной карты D1",
  },
];

export function formatDegree(value: number, precision = 4) {
  return `${value.toFixed(precision).replace(".", ",")}°`;
}

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTENT_ROOT = REPOSITORY_ROOT / "content" / "astrology-guide" / "articles"

TECHNICAL_CITATION_PATTERNS = (
    "github.com/",
    "docs.rs/panchangam",
    "astro.com/swisseph",
)

FALLBACK_CITATIONS = {
    "data-rozhdeniya-julian-day": "https://vedicway.ru/guide/yulianskiy-den",
    "granica-znaka-lagny": "https://vedicway.ru/guide/lagna-na-granice-znaka",
    "koordinaty-mesta-rozhdeniya-v-karte": (
        "https://vedicway.ru/guide/podgotovka-dannyh-rozhdeniya"
    ),
    "lagna-na-granice-znaka": "https://vedicway.ru/guide/granica-znaka-lagny",
    "letnee-vremya-i-natalnaya-karta": (
        "https://vedicway.ru/guide/istoricheskiy-chasovoy-poyas"
    ),
    "mestnoe-zvezdnoe-vremya-i-lagna": (
        "https://vedicway.ru/guide/zvezdnoe-vremya-i-ascendent"
    ),
    "moon-based-and-lagna-based-dashas": "https://vedicway.ru/guide/dashi-v-dzhyotish",
    "ogranicheniya-rascheta-natalnoj-karty": (
        "https://vedicway.ru/guide/proverka-raschyota-karty"
    ),
    "polozheniya-grah-v-sidereicheskoj-karte": (
        "https://vedicway.ru/guide/siderealnyj-i-tropicheskij-zodiak"
    ),
    "proverka-raschyota-karty": (
        "https://vedicway.ru/guide/podgotovka-dannyh-rozhdeniya"
    ),
    "retrogradnost-i-stacionarnost-grah": "https://vedicway.ru/guide/graha-v-dzhyotishe",
    "scenarii-pri-neizvestnom-vremeni": (
        "https://vedicway.ru/guide/karta-bez-vremeni-rozhdeniya"
    ),
    "sistemy-domov-v-sidereicheskoj-karte": "https://vedicway.ru/guide/bhava-i-lagna",
    "versii-raschyota-karty": "https://vedicway.ru/guide/proverka-raschyota-karty",
    "vybor-aynamshi-i-sistemy-domov": "https://vedicway.ru/guide/ayanamsha",
    "yulianskiy-den": "https://vedicway.ru/guide/data-rozhdeniya-julian-day",
}

LITERAL_REPLACEMENTS = (
    ("Swiss Ephemeris Programming Interface", "правила эфемеридного расчёта"),
    ("Swiss Ephemeris programming interface", "правила эфемеридного расчёта"),
    ("программное руководство Swiss Ephemeris", "описание эфемеридной методики"),
    ("Программное руководство Swiss Ephemeris", "Описание эфемеридной методики"),
    ("техническая документация Swiss Ephemeris", "правила эфемеридного расчёта"),
    ("Техническая документация Swiss Ephemeris", "Правила эфемеридного расчёта"),
    ("общая документация Swiss Ephemeris", "описание эфемеридного расчёта"),
    ("Общая документация Swiss Ephemeris", "Описание эфемеридного расчёта"),
    ("документация Swiss Ephemeris", "описание эфемеридного расчёта"),
    ("Документация Swiss Ephemeris", "Описание эфемеридного расчёта"),
    ("руководство Swiss Ephemeris", "описание эфемеридной методики"),
    ("Руководство Swiss Ephemeris", "Описание эфемеридной методики"),
    ("в Swiss Ephemeris", "в эфемеридной методике"),
    ("В Swiss Ephemeris", "В эфемеридной методике"),
    ("для Swiss Ephemeris", "для эфемеридного расчёта"),
    ("Swiss Ephemeris", "эфемеридная методика"),
    ("руководство pyswisseph", "сопоставление вариантов аянамши"),
    ("Руководство pyswisseph", "Сопоставление вариантов аянамши"),
    ("техническом перечне pyswisseph", "сопоставлении вариантов аянамши"),
    ("pyswisseph", "сопоставление вариантов аянамши"),
    ("документация Panchangam", "описание традиционного расчёта панчанги"),
    ("Документация Panchangam", "Описание традиционного расчёта панчанги"),
    ("документации panchangam", "описании традиционного расчёта панчанги"),
    ("библиотеки panchangam", "методики расчёта панчанги"),
    ("библиотека panchangam", "методика расчёта панчанги"),
    ("Panchangam", "традиционная схема панчанги"),
    ("panchangam", "традиционная схема панчанги"),
    ("репозиторий PyJHora", "сопоставление расчётных методик"),
    ("Репозиторий PyJHora", "Сопоставление расчётных методик"),
    ("README PyJHora", "сопоставление расчётных подходов"),
    ("README проекта", "описание расчётного подхода"),
    ("README", "описание методики"),
    ("в PyJHora", "в одной из расчётных методик"),
    ("В PyJHora", "В одной из расчётных методик"),
    ("настройки PyJHora", "различия расчётных подходов"),
    ("версию PyJHora", "редакцию расчётной методики"),
    ("PyJHora показывает", "Сопоставление расчётных методик показывает"),
    ("PyJHora сообщает", "Сопоставление расчётных методик показывает"),
    ("PyJHora содержит", "Сравнительная методика содержит"),
    ("PyJHora принимает", "Сравнительная методика использует"),
    ("PyJHora", "сравнительная расчётная методика"),
    ("JHora", "классическими расчётными таблицами"),
    ("в исходном коде compute_dasha.rs", "в сравнительном описании системы даш"),
    ("В исходном коде compute_dasha.rs", "В сравнительном описании системы даш"),
    ("в файле compute_dasha.rs", "в сравнительной схеме расчёта даш"),
    ("В файле compute_dasha.rs", "В сравнительной схеме расчёта даш"),
    ("Файл compute_dasha.rs", "Сравнительная схема расчёта даш"),
    ("файл compute_dasha.rs", "сравнительная схема расчёта даш"),
    ("исходный файл compute_dasha.rs", "сравнительное описание системы даш"),
    ("compute_dasha.rs", "сравнительная схема расчёта даш"),
    ("compute_dasha", "сравнительная схема расчёта даш"),
    ("ashtottari.py", "расчёт Ашоттари-даши"),
    ("vimsottari.py", "расчёт Вимшоттари-даши"),
    ("vimshottari.py", "расчёт Вимшоттари-даши"),
    ("yogini.py", "расчёт Йогини-даши"),
    ("chara.py", "расчёт Чара-даши"),
    ("narayana.py", "расчёт Нараяна-даши"),
    ("swe_set_sid_mode()", "выбор режима аянамши"),
    ("swe_set_sid_mode", "выбор режима аянамши"),
    ("swe_split_deg()", "точное деление долготы"),
    ("swe_split_deg", "точное деление долготы"),
    ("swe_calc_ut()", "эфемеридный расчёт положения"),
    ("swe_calc_ut", "эфемеридный расчёт положения"),
    ("swe_calc()", "эфемеридный расчёт положения"),
    ("swe_calc", "эфемеридный расчёт положения"),
    ("swe_utc_to_jd()", "перевод времени в юлианскую шкалу"),
    ("swe_utc_to_jd", "перевод времени в юлианскую шкалу"),
    ("swe_utc_time_zone()", "перевод местного времени в UTC"),
    ("swe_utc_time_zone", "перевод местного времени в UTC"),
    ("swe_houses_ex()", "расчёт домов с заданной аянамшей"),
    ("swe_houses_ex", "расчёт домов с заданной аянамшей"),
    ("swe_houses()", "расчёт домов"),
    ("swe_houses", "расчёт домов"),
    ("swe_sidtime()", "расчёт звёздного времени"),
    ("swe_sidtime", "расчёт звёздного времени"),
    ("swe_version()", "обозначение редакции эфемерид"),
    ("swe_version", "обозначение редакции эфемерид"),
    ("swe_get_current_file_data()", "проверку состава эфемеридных данных"),
    ("swe_get_current_file_data", "проверку состава эфемеридных данных"),
    ("birth_jd", "момент рождения по юлианской шкале"),
    ("moon_longitude", "сидерическая долгота Луны"),
    ("lagna_sign", "знак Лагны"),
    ("tjd_et", "шкала TT"),
    ("jd_et", "шкала TT"),
    ("tjd_ut", "шкала UT1"),
    ("jd_ut", "шкала UT1"),
    ("SIDM_TRUE_CITRA", "True Chitra"),
    ("SIDM_RAMAN", "Raman"),
    ("SEFLG_SIDEREAL", "сидерический режим"),
    ("FLG_SIDEREAL", "сидерический режим"),
    ("программный контракт", "набор исходных параметров"),
    ("Программный контракт", "Набор исходных параметров"),
    ("контракт конкретной программы", "набор исходных параметров выбранной методики"),
    ("контракт программы", "набор исходных параметров"),
    ("программная реализация", "расчётная методика"),
    ("Программная реализация", "Расчётная методика"),
    ("техническая реализация", "расчётная методика"),
    ("Техническая реализация", "Расчётная методика"),
    ("конкретная реализация", "конкретная методика"),
    ("исходный код", "описание расчётного правила"),
    ("Исходный код", "Описание расчётного правила"),
    ("программные функции", "расчётные процедуры"),
    ("функции библиотеки", "расчётные процедуры"),
    ("функция библиотеки", "расчётная процедура"),
    ("функции домов", "расчёты домов"),
    ("расчётной функции", "расчёте"),
    ("географический модуль", "географический расчёт"),
    ("отдельный модуль", "отдельный этап расчёта"),
    ("модуль Vimshottari", "методику Vimshottari"),
    ("модуль Vimsottari", "методику Vimsottari"),
    ("внутренний код режима", "точное обозначение режима"),
    ("код системы домов", "обозначение системы домов"),
    ("код метода", "обозначение метода"),
    ("код возврата", "указание применённого метода"),
    ("версия библиотеки", "редакция расчётной методики"),
    ("версии библиотеки", "редакции расчётной методики"),
    ("версию библиотеки", "редакцию расчётной методики"),
    ("версия приложения", "редакция расчёта"),
    ("версию приложения", "редакцию расчёта"),
    ("эфемеридные файлы", "эфемеридные данные"),
    ("файлы эфемерид", "эфемеридные данные"),
    ("файл эфемерид", "набор эфемерид"),
    ("список файлов", "состав эфемеридных данных"),
    ("имена и SHA-256 файлов", "состав набора эфемерид"),
    ("SHA-256", "контрольное обозначение"),
    ("хэши данных", "состав набора данных"),
    ("хэши", "контрольные обозначения"),
    ("если программа показывает", "если расчёт показывает"),
    ("Если программа показывает", "Если расчёт показывает"),
    ("программа показывает", "расчёт показывает"),
    ("Программа показывает", "Расчёт показывает"),
    ("программа использует", "методика использует"),
    ("Программа использует", "Методика использует"),
    ("программа позволяет", "методика позволяет"),
    ("Программа позволяет", "Методика позволяет"),
    ("программа уже определила", "предварительный расчёт уже определил"),
    ("Программа уже определила", "Предварительный расчёт уже определил"),
    ("две программы", "два расчёта"),
    ("Две программы", "Два расчёта"),
    ("двух программ", "двух расчётов"),
    ("между программами", "между расчётами"),
    ("Между программами", "Между расчётами"),
    ("разные программы", "разные расчёты"),
    ("Разные программы", "Разные расчёты"),
    ("одна программа", "один расчёт"),
    ("Одна программа", "Один расчёт"),
    ("другая программа", "другой расчёт"),
    ("Другaя программа", "Другой расчёт"),
    ("настройках программы", "параметрах расчёта"),
    ("настройки программы", "параметры расчёта"),
    ("настройку программы", "параметр расчёта"),
    ("название программы и версию", "методику и параметры расчёта"),
    ("название программы", "название методики"),
    ("версию программы", "набор расчётных параметров"),
    ("версия программы", "набор расчётных параметров"),
    ("при переходе между программами", "при сопоставлении разных расчётов"),
    ("При переходе между программами", "При сопоставлении разных расчётов"),
    ("на калькуляторе", "самостоятельно"),
    ("На калькуляторе", "Самостоятельно"),
    ("через калькулятор натальной карты", "через расчёт натальной карты"),
    ("калькулятор натальной карты", "расчёт натальной карты"),
    ("онлайн-калькулятор", "онлайн-расчёт"),
    ("Онлайн-калькулятор", "Онлайн-расчёт"),
    ("движок", "методика расчёта"),
    ("Движок", "Методика расчёта"),
    ("разработчики", "авторы методики"),
    ("разработчик", "автор методики"),
    ("интерфейсе", "форме расчёта"),
    ("интерфейсу", "форме расчёта"),
    ("интерфейсом", "формой расчёта"),
    ("интерфейса", "формы расчёта"),
    ("интерфейс", "форма расчёта"),
    ("API", "порядок расчёта"),
    ("приложением", "способом расчёта"),
    ("приложении", "способе расчёта"),
    ("приложения", "способа расчёта"),
    ("приложение", "способ расчёта"),
    ("пакета", "набора расчётных правил"),
    ("пакете", "наборе расчётных правил"),
    ("пакет", "набор расчётных правил"),
    ("сервисы", "способы расчёта"),
    ("сервисов", "способов расчёта"),
    ("сервисами", "способами расчёта"),
    ("сервисах", "способах расчёта"),
    ("сервиса", "способа расчёта"),
    ("сервисе", "способе расчёта"),
    ("сервисом", "способом расчёта"),
    ("сервис", "способ расчёта"),
    ("флагами", "параметрами"),
    ("флагов", "параметров"),
    ("флагом", "параметром"),
    ("флаги", "параметры"),
    ("флага", "параметра"),
    ("флаг", "параметр"),
)

WORD_FORMS = {
    "программирования": "расчётной процедуры",
    "программируемый": "рассчитываемый",
    "программируемая": "рассчитываемая",
    "программируемые": "рассчитываемые",
    "программному": "расчётному",
    "программного": "расчётного",
    "программными": "расчётными",
    "программных": "расчётных",
    "программном": "расчётном",
    "программную": "расчётную",
    "программной": "расчётной",
    "программные": "расчётные",
    "программный": "расчётный",
    "программная": "расчётная",
    "программное": "расчётное",
    "программами": "системами расчёта",
    "программам": "системам расчёта",
    "программах": "системах расчёта",
    "программист": "исследователь",
    "программу": "систему расчёта",
    "программой": "системой расчёта",
    "программе": "системе расчёта",
    "программы": "системы расчёта",
    "программ": "систем расчёта",
    "программа": "система расчёта",
    "калькуляторами": "расчётами",
    "калькуляторах": "расчётах",
    "калькуляторов": "расчётов",
    "калькулятором": "расчётом",
    "калькуляторе": "расчёте",
    "калькулятору": "расчёту",
    "калькулятора": "расчёта",
    "калькуляторы": "расчёты",
    "калькулятор": "расчёт",
    "библиотеками": "расчётными методиками",
    "библиотеках": "расчётных методиках",
    "библиотекой": "расчётной методикой",
    "библиотеке": "расчётной методике",
    "библиотеку": "расчётную методику",
    "библиотек": "расчётных методик",
    "библиотеки": "расчётной методики",
    "библиотека": "расчётная методика",
    "репозиториями": "сопоставлениями расчётных методик",
    "репозиториях": "сопоставлениях расчётных методик",
    "репозиторию": "сопоставлению расчётных методик",
    "репозиторием": "сопоставлением расчётных методик",
    "репозитории": "сопоставлении расчётных методик",
    "репозитория": "сопоставления расчётных методик",
    "репозиторий": "сопоставление расчётных методик",
    "кодами": "расчётными обозначениями",
    "кодах": "расчётных обозначениях",
    "кодов": "расчётных обозначений",
    "кодом": "расчётным правилом",
    "коде": "расчётной схеме",
    "коду": "расчётному правилу",
    "кода": "расчётного правила",
    "коды": "расчётные обозначения",
    "код": "расчётное правило",
}

FORBIDDEN_PUBLIC_PATTERNS = (
    re.compile(r"PyJHora|JHora|pyswisseph|Swiss Ephemeris|Panchangam", re.I),
    re.compile(r"compute_dasha|swe_[a-z_]+|[a-z_]+\.(?:py|rs)\b", re.I),
    re.compile(r"\bGitHub\b|\bREADME\b|\bAPI\b", re.I),
    re.compile(r"\bрепозитор\w*|\bпрограмм\w*|\bбиблиотек\w*", re.I),
    re.compile(
        r"(?<![A-Za-zА-Яа-яЁё])код(?:а|е|ом|у|ы|ов|ами|ах)?(?![A-Za-zА-Яа-яЁё])", re.I
    ),
    re.compile(
        r"\bкалькулятор\w*|\bсервис\w*|\bинтерфейс\w*|"
        r"\bдвиж(?:ок|к)\w*|\bразработчик\w*|\bобвязк\w*|"
        r"\bJSON\b|\bмашинн\w+\s+ответ\w*",
        re.I,
    ),
)

SOFTWARE_SENTENCE_PATTERN = re.compile(
    r"PyJHora|JHora|pyswisseph|Swiss Ephemeris|Panchangam|panchangam|"
    r"compute_dasha|swe_[a-z_]+|[a-z_]+\.(?:py|rs)\b|GitHub|README|API|"
    r"\bрепозитор\w*|\bпрограмм\w*|\bбиблиотек\w*|\bкалькулятор\w*|"
    r"\bсервис\w*|\bинтерфейс\w*|\bдвиж(?:ок|к)\w*|\bразработчик\w*|"
    r"\bприложени\w*|\bпакет\w*|\bисходник\w*|"
    r"\bJSON\b|\bмашинн\w+\s+ответ\w*|\bкомпьютер\w*|\bобвязк\w*|"
    r"\bпроцесс\w*|\bустановочн\w*|\bdefaults?\b|[a-z]+_[a-z_]+|"
    r"(?<![A-Za-zА-Яа-яЁё])код(?:а|е|ом|у|ы|ов|ами|ах)?(?![A-Za-zА-Яа-яЁё])",
    re.I,
)


def _astrological_replacement(sentence: str) -> str:
    plain = re.sub(r"<[^>]+>", "", sentence)
    lowered = plain.casefold()
    if any(word in lowered for word in ("полярн", "placidus", "koch", "porphyry")):
        return (
            "На высоких широтах отдельно проверяйте применённую систему домов: "
            "если выбранный метод не даёт устойчивых куспидов, расчёт должен явно "
            "назвать использованную альтернативу."
        )
    if any(
        word in lowered
        for word in (
            "эфемерид",
            "файл",
            "sha",
            "хэш",
            "верси",
            "обновлен",
            "обновлён",
            "данных",
        )
    ):
        if any(word in lowered for word in ("файл", "sha", "хэш", "путь", "набор")):
            return (
                "Для повторной проверки запишите название и дату набора эфемерид; "
                "внутренние сведения о хранении данных читателю не нужны."
            )
        if any(
            word in lowered
            for word in ("верси", "обновлен", "обновлён", "defaults", "исправлен")
        ):
            return (
                "После обновления расчёта заново сверьте долготы у границ знаков "
                "и накшатр, сохранив прежние исходные данные."
            )
        if any(word in lowered for word in ("дом", "лагн", "бхав", "куспид")):
            return (
                "Рядом с картой указывайте систему домов, аянамшу и источник "
                "эфемерид: при повторной проверке эти параметры сравнивают до трактовки."
            )
        return (
            "Рядом с картой указывайте дату расчёта и источник эфемерид, а при "
            "повторной проверке сравнивайте неокруглённые долготы."
        )
    if any(
        word in lowered
        for word in (
            "даша",
            "dasha",
            "vimsh",
            "ashtott",
            "yogini",
            "chara",
            "narayana",
            "период",
        )
    ):
        if any(word in lowered for word in ("уров", "влож", "дочерн", "антар")):
            return (
                "Для вложенных периодов заранее выберите одну формулу деления и "
                "одно календарное правило; смешение разных редакций меняет границы даш."
            )
        return (
            "Правило расчёта даши сверяйте с выбранной школой: исходная точка, "
            "порядок управителей и вложенность периодов должны принадлежать одной редакции."
        )
    if any(
        word in lowered
        for word in ("накшатр", "титхи", "tithi", "панчанг", "panchang", "йог")
    ):
        if any(word in lowered for word in ("границ", "округл", "делит", "сектор")):
            return (
                "На границе накшатры используйте исходную долготу без округления "
                "и заранее зафиксированное правило включения граничной точки."
            )
        return (
            "Для проверки расчёта сохраните неокруглённые долготы Солнца и Луны, "
            "аянамшу и правило деления круга на секторы."
        )
    if any(word in lowered for word in ("ретроград", "стационар", "скорост")):
        return (
            "Статус грахи проверяйте по её угловой скорости в выбранной сидерической "
            "системе, а порог стационарности записывайте отдельно."
        )
    if any(
        word in lowered
        for word in ("ayan", "аянамш", "сидерич", "lahiri", "raman", "chitra")
    ):
        if any(word in lowered for word in ("показы", "вывод", "получ", "форм")):
            return (
                "В подписи к карте должны быть видны аянамша, система домов и "
                "исходные координаты, чтобы читатель мог повторить расчёт."
            )
        return (
            "При сравнении расчётов фиксируйте название аянамши и исходную "
            "сидерическую долготу: у границы знака даже небольшое расхождение "
            "может изменить раши, накшатру или паду."
        )
    if any(
        word in lowered for word in ("бхав", "дом", "лагн", "lagna", "асценд", "ascend")
    ):
        if any(
            word in lowered for word in ("предупреж", "переключ", "замен", "возврат")
        ):
            return (
                "Если выбранная система домов была заменена при расчёте, укажите "
                "фактически применённый метод рядом с лагной и куспидами."
            )
        if any(word in lowered for word in ("координат", "широт", "долгот", "мест")):
            return (
                "Координаты места записывайте с направлением долготы и широты, "
                "а систему домов называйте рядом с лагной и куспидами."
            )
        return (
            "Для воспроизводимого расчёта домов записывайте систему домов, аянамшу "
            "и точные координаты; трактовку начинайте только после проверки этих параметров."
        )
    if any(
        word in lowered
        for word in (
            "julian",
            "utc",
            "tt",
            "ut1",
            "часов",
            "время",
            "времени",
            "временн",
            "календар",
            "дата",
        )
    ):
        if any(word in lowered for word in ("julian", "tt", "ut1")):
            return (
                "Юлианскую дату используйте вместе с явно указанной шкалой времени: "
                "положения планет и расчёт домов требуют согласованных временных данных."
            )
        return (
            "Для воспроизводимого расчёта сохраните местное время, исторический "
            "часовой пояс, UTC и принятую временную шкалу."
        )
    if any(word in lowered for word in ("варг", "d9", "d30", "d60")):
        return (
            "При чтении дробной карты фиксируйте правило деления знака и проверяйте "
            "пограничные долготы до интерпретации."
        )
    if any(
        word in lowered
        for word in ("показы", "вывод", "форма", "интерфейс", "калькулятор", "сервис")
    ):
        if any(word in lowered for word in ("сравн", "расхож", "разн")):
            return (
                "Если два расчёта расходятся, сравните исходные данные и настройки "
                "по одному параметру за раз."
            )
        if any(word in lowered for word in ("настрой", "выбер", "режим")):
            return (
                "Перед расчётом явно выберите аянамшу и систему домов, затем "
                "сохраните эти параметры рядом с картой."
            )
        return (
            "В подписи к карте должны быть видны исходные данные и принятые "
            "астрологические настройки, чтобы результат можно было проверить вручную."
        )
    if any(
        word in lowered
        for word in ("код", "репозитор", "github", "readme", "исходник", "модул")
    ):
        return (
            "Расчётное правило сверяйте с классическим источником и редакцией "
            "выбранной школы, не подменяя ими астрологическую интерпретацию."
        )
    if any(word in lowered for word in ("json", "машинн", "компьютер", "процесс")):
        return (
            "Сохраняйте рядом с изображением карты таблицу исходных данных и "
            "неокруглённых долгот: этого достаточно для повторной ручной проверки."
        )
    if any(word in lowered for word in ("сравн", "расхож", "разн")):
        return (
            "Если два расчёта расходятся, сначала сравните время рождения, аянамшу "
            "и систему домов, а затем правило округления."
        )
    if any(word in lowered for word in ("сохран", "фиксир", "запиш")):
        return (
            "Сохраняйте рядом с картой исходные данные и принятые правила расчёта, "
            "чтобы позднее повторить проверку на тех же условиях."
        )
    if any(word in lowered for word in ("источник", "документ", "описан", "руковод")):
        return (
            "Расчётное правило сверяйте с классическим источником и называйте "
            "редакцию, на которую опирается трактовка."
        )
    if any(word in lowered for word in ("настрой", "параметр", "режим")):
        return (
            "Аянамшу, систему домов и правило округления выбирайте до трактовки "
            "и указывайте рядом с результатом."
        )
    generic_variants = (
        "Исходные данные и правила выбранной школы записывайте рядом с картой, "
        "чтобы расчёт оставался проверяемым.",
        "Отделяйте вычисленные долготы от трактовки: сначала фиксируйте параметры "
        "карты, затем применяйте правила школы.",
        "Проверку начинайте с исходных данных и астрологических настроек, а вывод "
        "формулируйте только после их сверки.",
        "Один и тот же набор исходных параметров должен сопровождать расчёт и "
        "последующую интерпретацию карты.",
    )
    variant = sum(ord(character) for character in plain) % len(generic_variants)
    return generic_variants[variant]


def _rewrite_segment(segment: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", segment)
    result: list[str] = []
    inserted: set[str] = set()
    for part in parts:
        if not SOFTWARE_SENTENCE_PATTERN.search(part):
            result.append(part)
            continue
        if re.search(r"<a\b", part, flags=re.I):
            result.append(part)
            continue
        replacement = _astrological_replacement(part)
        if replacement not in inserted:
            result.append(replacement)
            inserted.add(replacement)
    return " ".join(result)


def _rewrite_software_sentences(value: str) -> str:
    if re.search(r"<p\b", value, flags=re.I):
        return re.sub(
            r"(<p\b[^>]*>)(.*?)(</p>)",
            lambda match: (
                f"{match.group(1)}{_rewrite_segment(match.group(2))}{match.group(3)}"
            ),
            value,
            flags=re.I | re.S,
        )

    lines: list[str] = []
    for line in value.splitlines(keepends=True):
        stripped = line.lstrip()
        if SOFTWARE_SENTENCE_PATTERN.search(line) and not stripped.startswith(
            ("#", "|", "-", "*", ">")
        ):
            ending = "\n" if line.endswith("\n") else ""
            lines.append(_rewrite_segment(line.rstrip("\r\n")) + ending)
        else:
            lines.append(line)
    return "".join(lines)


def _case_preserving_replacement(match: re.Match[str]) -> str:
    source = match.group(0)
    replacement = WORD_FORMS[source.casefold()]
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def refine_text(value: str) -> str:
    value = _rewrite_software_sentences(value)
    for old, new in LITERAL_REPLACEMENTS:
        value = value.replace(old, new)

    forms = "|".join(
        sorted((re.escape(word) for word in WORD_FORMS), key=len, reverse=True)
    )
    value = re.sub(
        rf"(?<![A-Za-zА-Яа-яЁё])(?:{forms})(?![A-Za-zА-Яа-яЁё])",
        _case_preserving_replacement,
        value,
        flags=re.I,
    )

    value = re.sub(r"\b(?:levels)\b", "глубина вложенных периодов", value, flags=re.I)
    value = re.sub(
        r"\b(?:source code|source-code)\b",
        "описание расчётного правила",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"\b(?:technical implementation)\b", "расчётная методика", value, flags=re.I
    )
    value = re.sub(r"\b(?:GitHub)\b", "сравнительный источник", value, flags=re.I)
    value = re.sub(r"\b(?:README)\b", "описание методики", value, flags=re.I)
    value = re.sub(r"\b(?:API)\b", "порядок расчёта", value, flags=re.I)

    unwrap_terms = (
        "выбор режима аянамши",
        "точное деление долготы",
        "эфемеридный расчёт положения",
        "перевод времени в юлианскую шкалу",
        "перевод местного времени в UTC",
        "расчёт домов с заданной аянамшей",
        "расчёт домов",
        "расчёт звёздного времени",
        "обозначение редакции эфемерид",
        "проверку состава эфемеридных данных",
        "момент рождения по юлианской шкале",
        "сидерическая долгота Луны",
        "знак Лагны",
        "сидерический режим",
        "расчёт Ашоттари-даши",
        "расчёт Вимшоттари-даши",
        "расчёт Йогини-даши",
        "расчёт Чара-даши",
        "расчёт Нараяна-даши",
    )
    unwrap = "|".join(re.escape(term) for term in unwrap_terms)
    value = re.sub(rf"<code>({unwrap})</code>", r"\1", value, flags=re.I)
    value = re.sub(rf"`({unwrap})`", r"\1", value, flags=re.I)

    cleanups = (
        ("расчётный расчёт", "расчёт"),
        ("расчётная система расчёта", "расчётная система"),
        ("методика расчёта расчёта", "методика расчёта"),
        ("система расчёта расчёта", "методика расчёта"),
        ("расчётная методика расчёта", "расчётная методика"),
        ("способ расчёта расчёта", "способ расчёта"),
        ("редакция расчётной методики расчёта", "редакция расчётной методики"),
        ("расчётной расчётной", "расчётной"),
        ("расчётного расчётного", "расчётного"),
        ("расчётные расчётные", "расчётные"),
        ("расчётный расчётный", "расчётный"),
        ("версия движка", "редакция расчёта"),
        ("версии движка", "редакции расчёта"),
        ("версию движка", "редакцию расчёта"),
        ("расчётный стек", "параметры расчёта"),
        ("Техническая воспроизводимость", "Точность повторного расчёта"),
        ("техническая воспроизводимость", "точность повторного расчёта"),
        ("Технический расчёт", "Расчёт координат"),
        ("технический расчёт", "расчёт координат"),
        ("в техническом расчёте", "при вычислении координат"),
        ("В техническом расчёте", "При вычислении координат"),
        (
            "с точностью, которую принял методика расчёта",
            "с точностью, необходимой для выбранного метода",
        ),
        (
            "запрошенный обозначение системы домов и фактически возвращённый расчётное правило",
            "выбранную и фактически применённую систему домов",
        ),
        (
            "система расчёта должна назвать алгоритм",
            "в описании нужно назвать правило расчёта",
        ),
    )
    for old, new in cleanups:
        value = value.replace(old, new)
        value = value.replace(old[:1].upper() + old[1:], new[:1].upper() + new[1:])
    return value


def refine_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    source = json.loads(json.dumps(manifest, ensure_ascii=False))
    for key in ("title",):
        if isinstance(source.get(key), str):
            source[key] = refine_text(source[key])
    seo = source.get("seo")
    if isinstance(seo, dict):
        for key in ("seo_title", "meta_description", "focus_keyphrase", "excerpt"):
            if isinstance(seo.get(key), str):
                seo[key] = refine_text(seo[key])
    if isinstance(source.get("prohibited_claims"), list):
        source["prohibited_claims"] = [
            refine_text(value) if isinstance(value, str) else value
            for value in source["prohibited_claims"]
        ]
    if isinstance(source.get("tags"), list):
        source["tags"] = [
            refine_text(value) if isinstance(value, str) else value
            for value in source["tags"]
        ]
    cover = source.get("cover")
    if isinstance(cover, dict):
        for key in ("alt", "title", "caption"):
            if isinstance(cover.get(key), str):
                cover[key] = refine_text(cover[key])

    source_schema_extra = source.get("schema_extra")
    if isinstance(source_schema_extra, dict) and isinstance(
        source_schema_extra.get("citation"), list
    ):
        citations = [
            citation
            for citation in source_schema_extra["citation"]
            if not any(
                pattern in str(citation).casefold()
                for pattern in TECHNICAL_CITATION_PATTERNS
            )
        ]
        if citations:
            source_schema_extra["citation"] = citations
        else:
            source_schema_extra.pop("citation", None)
    if isinstance(source_schema_extra, dict) and not source_schema_extra.get(
        "citation"
    ):
        fallback_citation = FALLBACK_CITATIONS.get(str(source.get("slug") or ""))
        if fallback_citation:
            source_schema_extra["citation"] = [fallback_citation]

    if isinstance(source_schema_extra, dict) and isinstance(
        source_schema_extra.get("about"), list
    ):
        for item in source_schema_extra["about"]:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                item["name"] = refine_text(item["name"])

    refined = source
    internal_links = refined.get("internal_links")
    if isinstance(internal_links, list):
        aliases = {
            "/guide/rashi-v-dzhyotish": "/guide/rashi-v-dzhyotishe",
            "/guide/dostoinstva-planet-v-dzhyotishe": "/guide/svakshetra-mulatrikona-uchcha",
        }
        normalized_links: list[Any] = []
        for link in internal_links:
            if isinstance(link, str):
                normalized_links.append(aliases.get(link, link))
            elif isinstance(link, dict):
                normalized_link = dict(link)
                for key in ("url", "href"):
                    if isinstance(normalized_link.get(key), str):
                        normalized_link[key] = aliases.get(
                            normalized_link[key], normalized_link[key]
                        )
                normalized_links.append(normalized_link)
            else:
                normalized_links.append(link)
        refined["internal_links"] = normalized_links
    return refined


def _route_is_valid(path: str, slugs: set[str]) -> bool:
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc:
        return True
    route = parsed.path.rstrip("/") or "/"
    if route in {"/", "/guide", "/blog", "/chart", "/privacy", "/terms"}:
        return True
    if route.startswith("/guide/"):
        return route.removeprefix("/guide/") in slugs
    return False


def _validate_public_text(path: Path, value: str, errors: list[str]) -> None:
    for pattern in FORBIDDEN_PUBLIC_PATTERNS:
        match = pattern.search(value)
        if match:
            errors.append(f"{path}: осталось техническое упоминание {match.group(0)!r}")
    if path.name == "article.html":
        if len(re.findall(r"<h1(?:\s|>)", value, flags=re.I)):
            errors.append(f"{path}: тело статьи не должно содержать H1")
        if not re.search(r"<h2(?:\s|>)", value, flags=re.I):
            errors.append(f"{path}: статья осталась без H2")


def run(content_root: Path, *, apply: bool) -> dict[str, Any]:
    article_dirs = sorted(path for path in content_root.iterdir() if path.is_dir())
    slugs = {path.name for path in article_dirs}
    changed_files: list[str] = []
    changed_articles: set[str] = set()
    replacements = Counter()
    errors: list[str] = []

    for article_dir in article_dirs:
        for filename in ("article.html", "article.md"):
            path = article_dir / filename
            original = path.read_text(encoding="utf-8")
            refined = refine_text(original)
            _validate_public_text(path, refined, errors)
            for href in re.findall(r'href=["\']([^"\']+)["\']', refined, flags=re.I):
                if href.startswith("/") and not _route_is_valid(href, slugs):
                    errors.append(f"{path}: нерабочая внутренняя ссылка {href}")
            if refined != original:
                changed_files.append(str(path.relative_to(REPOSITORY_ROOT)))
                changed_articles.add(article_dir.name)
                replacements["article_text_files"] += 1
                if apply:
                    path.write_text(refined, encoding="utf-8", newline="\n")

        manifest_path = article_dir / "manifest.json"
        original_manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(original_manifest_text)
        refined_manifest = refine_manifest(manifest)
        for link in refined_manifest.get("internal_links") or []:
            target = (
                link
                if isinstance(link, str)
                else link.get("url") or link.get("href")
                if isinstance(link, dict)
                else None
            )
            if (
                isinstance(target, str)
                and target.startswith("/")
                and not _route_is_valid(target, slugs)
            ):
                errors.append(f"{manifest_path}: нерабочая внутренняя ссылка {target}")
        schema_for_validation = dict(refined_manifest.get("schema_extra") or {})
        schema_for_validation.pop("citation", None)
        public_manifest_text = json.dumps(
            {
                "title": refined_manifest.get("title"),
                "seo": refined_manifest.get("seo"),
                "prohibited_claims": refined_manifest.get("prohibited_claims"),
                "schema_extra": schema_for_validation,
            },
            ensure_ascii=False,
        )
        _validate_public_text(manifest_path, public_manifest_text, errors)
        refined_manifest_text = (
            json.dumps(refined_manifest, ensure_ascii=False, indent=2) + "\n"
        )
        if refined_manifest_text != original_manifest_text:
            changed_files.append(str(manifest_path.relative_to(REPOSITORY_ROOT)))
            changed_articles.add(article_dir.name)
            replacements["manifest_files"] += 1
            if apply:
                manifest_path.write_text(
                    refined_manifest_text, encoding="utf-8", newline="\n"
                )

    if len(article_dirs) != 202:
        errors.append(f"ожидалось 202 каталога статей, найдено {len(article_dirs)}")
    if errors:
        raise RuntimeError("\n".join(errors[:80]))

    return {
        "mode": "apply" if apply else "dry-run",
        "articles_checked": len(article_dirs),
        "articles_changed": len(changed_articles),
        "files_changed": len(changed_files),
        "changes": dict(replacements),
        "sample_files": changed_files[:12],
        "internal_links": "valid",
        "technical_markers": "absent after refinement",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Surgically remove software-centric fragments from the fixed guide corpus"
    )
    parser.add_argument("--content-root", type=Path, default=DEFAULT_CONTENT_ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.content_root.resolve(), apply=args.apply),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

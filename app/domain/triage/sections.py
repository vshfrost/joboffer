"""Секції вакансії за заголовками (EN, UK, RU, ES): обов'язкові вимоги, «буде плюсом», решта."""

import re
from dataclasses import dataclass
from enum import StrEnum

from domain.sources.fold import fold

# Довший рядок — це речення, а не заголовок.
MAX_HEADING_WORDS = 6
# Пункт списку («- », «• », «* », «1. ») не заголовок; «**Requirements**» — заголовок.
BULLET = re.compile(r"(?:[-•·–—*]|\d+[.)])\s")


class Kind(StrEnum):
    MUST = "must"
    NICE = "nice"
    OTHER = "other"


# Фрази вже згорнуті `fold` (без регістру, діакритики, апострофів); заголовок починається з фрази.
NICE_PHRASES = (
    "nice to have",
    "nice to haves",
    "bonus points",
    "extra points",
    "preferred qualifications",
    "preferred skills",
    "preferred experience",
    "desirable",
    "desired skills",
    "would be a plus",
    "a plus",
    "plus",
    "pluses",
    "буде плюсом",
    "буде великим плюсом",
    "буде перевагою",
    "додатковим плюсом",
    "бажано",
    "будет плюсом",
    "плюсом будет",
    "будет преимуществом",
    "желательно",
    "приветствуется",
    "se valora",
    "se valorara",
    "se valoran",
    "deseable",
    "deseables",
    "valorable",
    "sera un plus",
    "es un plus",
    "additional experience",
    "additional skills",
    "good to have",
    "great to have",
    "would be an advantage",
    "tambien valoramos",
    "valoramos",
)
MUST_PHRASES = (
    "requirements",
    "requirement",
    "key requirements",
    "minimum requirements",
    "basic requirements",
    "technical requirements",
    "mandatory requirements",
    "required skills",
    "required",
    "must have",
    "must haves",
    "what we are looking for",
    "what were looking for",
    "we are looking for",
    "were looking for",
    "what you bring",
    "what you need",
    "what youll need",
    "who you are",
    "about you",
    "your profile",
    "qualifications",
    "skills",
    "essential",
    "вимоги",
    "ми шукаємо",
    "що ми шукаємо",
    "що ми очікуємо",
    "що потрібно",
    "требования",
    "мы ищем",
    "что мы ищем",
    "что мы ожидаем",
    "что нужно",
    "requisitos",
    "requerimientos",
    "que buscamos",
    "lo que buscamos",
    "buscamos",
    "perfil",
    "tu perfil",
    "se requiere",
    "imprescindible",
    "imprescindibles",
    "sobre ti",
    "que necesitas",
    "lo que necesitas",
    "que aportas",
    "lo que aportas",
    "tu experiencia",
    "minimum qualifications",
    "basic qualifications",
    "what you will bring",
    "what youll bring",
    "you bring",
    "ideal candidate",
    "the ideal candidate",
)
OTHER_PHRASES = (
    "responsibilities",
    "key responsibilities",
    "your responsibilities",
    "duties",
    "what you will do",
    "what youll do",
    "your role",
    "the role",
    "about the role",
    "job description",
    "what we offer",
    "we offer",
    "benefits",
    "perks",
    "compensation",
    "salary",
    "why join us",
    "about us",
    "about the company",
    "about the team",
    "who we are",
    "our culture",
    "our values",
    "our mission",
    "how to apply",
    "hiring process",
    "interview process",
    "recruitment process",
    "next steps",
    "working conditions",
    "обовязки",
    "ваші завдання",
    "завдання",
    "що робити",
    "ми пропонуємо",
    "що ми пропонуємо",
    "умови",
    "про нас",
    "про компанію",
    "про роль",
    "про вакансію",
    "про команду",
    "як податися",
    "обязанности",
    "задачи",
    "что делать",
    "мы предлагаем",
    "что мы предлагаем",
    "условия",
    "о нас",
    "о компании",
    "о роли",
    "о вакансии",
    "о команде",
    "responsabilidades",
    "funciones",
    "tus funciones",
    "tus responsabilidades",
    "que haras",
    "ofrecemos",
    "que ofrecemos",
    "te ofrecemos",
    "beneficios",
    "condiciones",
    "oferta",
    "sobre nosotros",
    "sobre la empresa",
    "sobre el puesto",
    "quienes somos",
    "como aplicar",
    "accountabilities",
    "key accountabilities",
    "what youll be doing",
    "what you will be doing",
    "tu mision",
    "sobre el rol",
)
# Довші за ліміт, але все ж заголовки: рядок має збігатися з фразою повністю.
LONG_HEADINGS = ("additional experience that would be an advantage",)
# Порядок: «Nice to have requirements» — nice, а не must.
HEADINGS = (
    (Kind.NICE, NICE_PHRASES),
    (Kind.MUST, MUST_PHRASES),
    (Kind.OTHER, OTHER_PHRASES),
)


@dataclass(frozen=True, slots=True)
class Sections:
    """Рядки секцій вимог. `recognised` — знайдено принаймні один заголовок must чи nice."""

    must: str
    nice: str
    text: str
    recognised: bool


def heading_kind(head: str) -> Kind | None:
    """Вид секції, якщо короткий рядок починається з відомого заголовка."""
    folded = fold(head)
    if len(folded.split()) > MAX_HEADING_WORDS and folded not in LONG_HEADINGS:
        return None
    padded = f"{folded} "
    for kind, phrases in HEADINGS:
        if any(padded.startswith(f"{phrase} ") for phrase in phrases):
            return kind
    return None


def split_sections(text: str) -> Sections:
    """Секція триває до наступного заголовка (будь-якого виду); текст перед першим — нічий.

    Текст після двокрапки в рядку заголовка належить секції. Порожні рядки пропускаються."""
    current = Kind.OTHER
    recognised = False
    lines: dict[Kind, list[str]] = {kind: [] for kind in Kind}
    ordered: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        head, _, rest = line.partition(":")
        kind = None if BULLET.match(line) else heading_kind(head)
        if kind is not None:
            current = kind
            recognised = recognised or kind is not Kind.OTHER
            line = rest.strip()
        if line:
            lines[current].append(line)
            if current is not Kind.OTHER:
                ordered.append(line)
    return Sections(
        must="\n".join(lines[Kind.MUST]),
        nice="\n".join(lines[Kind.NICE]),
        text="\n".join(ordered),
        recognised=recognised,
    )

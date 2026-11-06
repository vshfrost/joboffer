"""Порівняння тексту без регістру, діакритики й розділових знаків: основа фільтра й дедупу."""

import re
import unicodedata

CYRILLIC = re.compile("[а-яіїєґё]", re.IGNORECASE)
CYRILLIC_VOWELS = "аяиіїеєоуюыэ"
# Коротші слова не різати: «Київ» лишається «київ».
MIN_STEM_LENGTH = 5


def fold(text: str) -> str:
    """Без діакритики й регістру, розділові знаки — пробіли («back-end» → «back end»);
    крапки й апострофи зникають («S.L.» → «sl»)."""
    plain = unicodedata.normalize("NFKD", text.casefold().replace("’", "'"))
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    plain = plain.replace(".", "").replace("'", "")
    return " ".join(re.sub(r"[^\w]+", " ", plain).split())


def has_phrase(folded: str, phrase: str) -> bool:
    """Фраза як ціле слово (слова) всередині тексту; обидва вже згорнуті `fold`."""
    return bool(phrase) and f" {phrase} " in f" {folded} "


def has_stem(folded: str, stem: str) -> bool:
    """Слово починається з основи («віддален» → «віддалено», «віддаленої»)."""
    return f" {fold(stem)}" in f" {folded}"


def cyrillic_stem(folded: str) -> str:
    """Основа кириличного слова: без кінцевого голосного («україна» → «україн»)."""
    if len(folded) >= MIN_STEM_LENGTH and folded[-1] in CYRILLIC_VOWELS:
        return folded[:-1]
    return folded


def has_term(folded: str, term: str) -> bool:
    """Слово чи фраза профілю в тексті: латиниця — ціле слово, кирилиця — за основою слова."""
    key = fold(term)
    if not key:
        return False
    if CYRILLIC.search(term):
        return has_stem(folded, cyrillic_stem(key))
    return has_phrase(folded, key)

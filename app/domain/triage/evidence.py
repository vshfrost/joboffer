"""Докази з тексту вакансії для тріажу без LLM: вимоги (must / nice), рівень із назви,
цільові домени, зарплата в EUR. Чисті функції без IO."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from domain.profile.modes import Seniority
from domain.sources.fold import CYRILLIC, fold, has_phrase, has_term
from domain.triage.sections import split_sections
from domain.triage.terms import TERMS, Term, literal_pattern

# Менше за це на рік — майже напевно місячна чи погодинна ставка, а не річна зарплата.
MIN_ANNUAL_EUR = 10_000
THOUSAND = 1_000
# Коротші слова не різати: «bus», «gas» лишаються собою.
MIN_WORD_STEM = 3

# Від старшого рівня до молодшого: «Senior Tech Lead» — lead.
SENIORITY_WORDS = (
    (Seniority.PRINCIPAL, ("principal",)),
    (Seniority.LEAD, ("lead",)),
    (Seniority.SENIOR, ("senior", "sr")),
    (Seniority.MIDDLE, ("middle", "mid")),
    (Seniority.JUNIOR, ("junior", "jr")),
)

_NUMBER = r"\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?"
_CURRENCY_BEFORE = r"(?:€|\bEUR\b)\s?"
# Межа діапазону: тире чи слова «and» / «to» («between 45.600 EUR and 61.800 EUR», «€50k to €70k»).
_RANGE_SEPARATOR = r"(?:\s?[-–—]\s?|\s+(?:and|to)\s+)"
SALARY = re.compile(
    rf"(?P<before>{_CURRENCY_BEFORE})?(?P<low>{_NUMBER})(?P<low_k>\s?k\b)?"
    rf"(?:(?P<low_after>\s?(?:€|\bEUR\b))?{_RANGE_SEPARATOR}(?:{_CURRENCY_BEFORE})?"
    rf"(?P<high>{_NUMBER})(?P<high_k>\s?k\b)?)?"
    r"(?P<after>\s?(?:€|\bEUR\b|\beuros?\b))?",
    re.IGNORECASE,
)
THOUSANDS_GROUPED = re.compile(r"\d{1,3}(?:[,.]\d{3})+")
# Ставка за годину, день, тиждень чи місяць одразу після суми.
NOT_ANNUAL = re.compile(
    r"\s*(?:/|per\s+)(?:h|hr|hour|d|day|w|week|m|mo|month)\b", re.IGNORECASE
)


class Confidence(StrEnum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class Requirements:
    """Терміни словника за секціями вимог і текст цих секцій.

    Заголовків вимог не знайдено → усе в `must`, `confidence` низька, `text` — увесь текст."""

    must: tuple[str, ...]
    nice: tuple[str, ...]
    confidence: Confidence
    text: str


@dataclass(frozen=True, slots=True)
class SalaryRange:
    """Річна зарплата у EUR; одне число — `low_eur == high_eur`."""

    low_eur: int
    high_eur: int


def _mentions(term: Term, text: str, folded: str) -> bool:
    return any(has_term(folded, synonym) for synonym in term.synonyms) or any(
        literal_pattern(literal).search(text) for literal in term.literals
    )


def find_terms(text: str) -> tuple[str, ...]:
    """Канонічні назви термінів словника, згаданих у тексті (порядок словника, без повторів)."""
    folded = fold(text)
    return tuple(term.name for term in TERMS if _mentions(term, text, folded))


def terms_in_facts(facts: Sequence[str]) -> tuple[str, ...]:
    """Терміни словника, згадані в текстах фактів; кожен факт читається окремо."""
    found = {name for fact in facts for name in find_terms(fact)}
    return tuple(term.name for term in TERMS if term.name in found)


def extract_requirements(text: str) -> Requirements:
    """Вимоги вакансії: терміни в секціях must і nice (термін в обох — must)."""
    sections = split_sections(text)
    if not sections.recognised:
        return Requirements(find_terms(text), (), Confidence.LOW, text)
    must = find_terms(sections.must)
    nice = tuple(term for term in find_terms(sections.nice) if term not in must)
    return Requirements(must, nice, Confidence.HIGH, sections.text)


def seniority_from_title(title: str) -> Seniority | None:
    """Найвищий рівень, названий в назві посади; жодного — `None`."""
    folded = fold(title)
    for level, words in SENIORITY_WORDS:
        if any(has_phrase(folded, word) for word in words):
            return level
    return None


def _stem_word(word: str) -> str:
    """Латинське слово без закінчення множини й «-ing» («fintechs» → «fintech», «banking» → «bank»)."""
    if len(word) > MIN_WORD_STEM and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    if len(word) > MIN_WORD_STEM + len("ing") and word.endswith("ing"):
        word = word[: -len("ing")]
    return word


def _stemmed(folded: str) -> str:
    return " ".join(_stem_word(word) for word in folded.split())


def find_domains(text: str, domains: Sequence[str]) -> tuple[str, ...]:
    """Цільові домени профілю, згадані в тексті (у тому вигляді, як у профілі).
    Латиниця — ціле слово з точністю до множини й «-ing»: «fintechs» — fintech, «banking» — bank."""
    folded = fold(text)
    stemmed = _stemmed(folded)
    return tuple(
        domain
        for domain in domains
        if (
            has_term(folded, domain)
            if CYRILLIC.search(domain)
            else has_phrase(stemmed, _stemmed(fold(domain)))
        )
    )


def _amount(number: str, thousands: bool) -> int:
    value = (
        float(re.sub(r"[,.]", "", number))
        if THOUSANDS_GROUPED.fullmatch(number)
        else float(number)
    )
    return round(value * THOUSAND) if thousands else round(value)


def parse_salary_eur(text: str) -> SalaryRange | None:
    """Перша річна сума в EUR («€60–80k», «€60,000–80,000», «60k EUR»); інша валюта,
    місячна чи погодинна ставка, замала сума — `None`."""
    for match in SALARY.finditer(text):
        if not (match["before"] or match["low_after"] or match["after"]):
            continue
        if NOT_ANNUAL.match(text, match.end()):
            continue
        high = match["high"] or match["low"]
        thousands = bool(match["low_k"] or match["high_k"])
        low_eur = _amount(match["low"], thousands)
        if low_eur >= MIN_ANNUAL_EUR:
            return SalaryRange(low_eur, _amount(high, thousands))
    return None

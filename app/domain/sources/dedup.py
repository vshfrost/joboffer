"""Дедуп між джерелами: та сама «компанія + посада» під різними URL."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from domain.sources.fold import fold

# Та сама вакансія під різними URL (ATS, DOU, Djinni, LinkedIn): «компанія + посада» за цей час.
DEDUP_WINDOW = timedelta(days=30)
# Юридичні форми не є частиною назви компанії при зіставленні.
COMPANY_SUFFIXES = frozenset(
    {
        "inc",
        "ltd",
        "llc",
        "gmbh",
        "sl",
        "slu",
        "sa",
        "bv",
        "ag",
        "plc",
        "limited",
        "corp",
    }
)


@dataclass(frozen=True, slots=True)
class RecentJob:
    """Недавня вакансія користувача (і схована теж) для дедупу між джерелами."""

    number: int
    company: str | None
    title: str | None
    needs_text: bool


def company_key(company: str) -> str:
    """Назва компанії для зіставлення: без регістру, діакритики, крапок і юридичних форм."""
    return " ".join(
        word for word in fold(company).split() if word not in COMPANY_SUFFIXES
    )


def find_same_job(
    recent: Iterable[RecentJob], company: str, title: str
) -> RecentJob | None:
    """Недавня вакансія з тією самою нормалізованою парою «компанія + посада». Якщо їх кілька,
    перша без тексту (їй допишуть опис), інакше перша."""
    wanted = (company_key(company), fold(title))
    if not all(wanted):
        return None
    same = [
        job
        for job in recent
        if job.company is not None
        and job.title is not None
        and (company_key(job.company), fold(job.title)) == wanted
    ]
    return next((job for job in same if job.needs_text), same[0] if same else None)

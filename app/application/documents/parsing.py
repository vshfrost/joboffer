"""Сирі значення документів ↔ домен: рядки чистяться тут, межі перевіряє домен."""

from application.contracts.documents import (
    ClaimData,
    CoverLetterData,
    CvData,
    CvEntryData,
    CvSectionData,
)
from domain.documents.document import (
    Claim,
    CoverLetter,
    Cv,
    CvEntry,
    CvSection,
    CvSectionName,
)
from domain.profile.text import one_line
from domain.shared.errors import InvalidValue


def parse_cv(data: CvData) -> Cv:
    return Cv(
        headline=_claim(data.headline),
        summary=_claim(data.summary),
        sections=tuple(_section(section) for section in data.sections),
    )


def parse_cover_letter(data: CoverLetterData) -> CoverLetter:
    """Абзаци — за порожнім рядком; одинарний перенос усередині абзацу лишається межею рядка
    (підпис «Best regards,\\nName»), пробіли в рядках стискаються."""
    paragraphs: list[str] = []
    lines: list[str] = []
    for line in map(one_line, [*data.text.splitlines(), ""]):
        if line:
            lines.append(line)
        elif lines:
            paragraphs.append("\n".join(lines))
            lines = []
    return CoverLetter(tuple(paragraphs), tuple(dict.fromkeys(data.fact_ids)))


def cv_raw_fields(data: CvData) -> tuple[list[str], list[str]]:
    """Сирі рядки CV до чистки пробілів: (заголовки, підсумок, meta, subtitle) і пункти (bullets)."""
    fields = [data.headline.text, data.summary.text]
    bullets: list[str] = []
    for section in data.sections:
        for entry in section.entries:
            fields.append(entry.heading.text)
            fields += [claim.text for claim in (entry.meta, entry.subtitle) if claim]
            bullets += [bullet.text for bullet in entry.bullets]
    return fields, bullets


def cv_data(cv: Cv) -> CvData:
    return CvData(
        headline=_claim_data(cv.headline),
        summary=_claim_data(cv.summary),
        sections=tuple(
            CvSectionData(
                name=section.name.value,
                entries=tuple(
                    CvEntryData(
                        heading=_claim_data(entry.heading),
                        bullets=tuple(_claim_data(bullet) for bullet in entry.bullets),
                        meta=None if entry.meta is None else _claim_data(entry.meta),
                        subtitle=None
                        if entry.subtitle is None
                        else _claim_data(entry.subtitle),
                    )
                    for entry in section.entries
                ),
            )
            for section in cv.sections
        ),
    )


def cover_letter_data(letter: CoverLetter) -> CoverLetterData:
    return CoverLetterData(text=letter.text, fact_ids=letter.fact_ids)


def _claim(data: ClaimData) -> Claim:
    return Claim(one_line(data.text), tuple(dict.fromkeys(data.fact_ids)))


def _optional_claim(data: ClaimData | None) -> Claim | None:
    return None if data is None else _claim(data)


def _entry(data: CvEntryData) -> CvEntry:
    return CvEntry(
        _claim(data.heading),
        tuple(_claim(bullet) for bullet in data.bullets),
        _optional_claim(data.meta),
        _optional_claim(data.subtitle),
    )


def _section(data: CvSectionData) -> CvSection:
    try:
        name = CvSectionName(data.name.strip())
    except ValueError:
        allowed = ", ".join(member.value for member in CvSectionName)
        raise InvalidValue(
            "sections", f"Секція {data.name!r} — допустимо: {allowed}."
        ) from None
    return CvSection(name, tuple(_entry(entry) for entry in data.entries))


def _claim_data(claim: Claim) -> ClaimData:
    return ClaimData(text=claim.text, fact_ids=claim.fact_ids)

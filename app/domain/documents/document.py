"""Документи під вакансію (CV, cover letter): пише Claude, сервер перевіряє довжини й форму,
а кожен рядок стоїть на фактах (їх підтвердженість перевіряє use case)."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domain.documents.ids import DocumentId
from domain.documents.lint import PLACEHOLDER, LintReport
from domain.shared.errors import InvalidValue

MAX_CLAIM_LENGTH = 400
MAX_FACT_IDS = 10
MAX_BULLETS = 12
MAX_ENTRIES = 20
MIN_LETTER_WORDS = 150
MAX_LETTER_WORDS = 250
MAX_LETTER_FACT_IDS = 30
# Назва групи скілів стоїть в окремій колонці таблиці і не переноситься.
MAX_SKILL_LABEL = 30
# Номер документа зберігається в int4: більший за нього не існує.
MAX_DOCUMENT_NUMBER = 2**31 - 1


class DocumentKind(StrEnum):
    CV = "cv"
    COVER_LETTER = "cl"


class CvSectionName(StrEnum):
    """Стандартні заголовки, які ATS розпізнають. Порядок секцій у CV обирає Claude."""

    EXPERIENCE = "Experience"
    PROJECTS = "Projects"
    ACHIEVEMENTS = "Achievements"
    SKILLS = "Skills"
    EDUCATION = "Education"
    EDUCATION_AND_LANGUAGES = "Education and Languages"
    CERTIFICATIONS = "Certifications"
    LANGUAGES = "Languages"

    @property
    def heading(self) -> str:
        """Заголовок у PDF (шаблон пише його великими літерами)."""
        return SECTION_HEADINGS.get(self, self.value)


SECTION_HEADINGS = {
    CvSectionName.EXPERIENCE: "Professional Experience",
    CvSectionName.PROJECTS: "Selected Projects",
}


@dataclass(frozen=True, slots=True)
class Claim:
    """Рядок документа і факти, на яких він стоїть."""

    text: str
    fact_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.text or len(self.text) > MAX_CLAIM_LENGTH:
            raise InvalidValue(
                "text",
                f"Кожен рядок — від 1 до {MAX_CLAIM_LENGTH} символів: {self.text[:60]!r}.",
            )
        if not self.fact_ids:
            raise InvalidValue("fact_ids", f"Рядок без fact_ids: {self.text[:60]!r}.")
        if len(self.fact_ids) > MAX_FACT_IDS:
            raise InvalidValue(
                "fact_ids",
                f"Не більше {MAX_FACT_IDS} fact_ids на рядок: {self.text[:60]!r}.",
            )


@dataclass(frozen=True, slots=True)
class CvEntry:
    """Пункт секції: роль, проєкт, група скілів… Заголовок — теж твердження з фактами.
    meta — праворуч від заголовка (дати, «Independent project»), subtitle — сірий рядок
    під ним (контекст ролі); обидва необов'язкові й теж стоять на фактах."""

    heading: Claim
    bullets: tuple[Claim, ...] = ()
    meta: Claim | None = None
    subtitle: Claim | None = None

    def __post_init__(self) -> None:
        if len(self.bullets) > MAX_BULLETS:
            raise InvalidValue(
                "bullets",
                f"Не більше {MAX_BULLETS} пунктів у {self.heading.text[:60]!r}.",
            )

    def claims(self) -> Iterator[Claim]:
        yield self.heading
        if self.meta is not None:
            yield self.meta
        if self.subtitle is not None:
            yield self.subtitle
        yield from self.bullets


@dataclass(frozen=True, slots=True)
class CvSection:
    name: CvSectionName
    entries: tuple[CvEntry, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.entries) <= MAX_ENTRIES:
            raise InvalidValue(
                "entries", f"Секція {self.name.value}: від 1 до {MAX_ENTRIES} пунктів."
            )
        if self.name is CvSectionName.SKILLS:
            for entry in self.entries:
                if entry.bullets and len(entry.heading.text) > MAX_SKILL_LABEL:
                    raise InvalidValue(
                        "entries",
                        f"Назва групи скілів — до {MAX_SKILL_LABEL} символів: "
                        f"{entry.heading.text[:60]!r}.",
                    )


@dataclass(frozen=True, slots=True)
class Cv:
    headline: Claim
    summary: Claim
    sections: tuple[CvSection, ...]

    def __post_init__(self) -> None:
        if not self.sections:
            raise InvalidValue("sections", "CV без секцій.")
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise InvalidValue("sections", "Кожна секція — один раз.")

    def claims(self) -> Iterator[Claim]:
        yield self.headline
        yield self.summary
        for section in self.sections:
            for entry in section.entries:
                yield from entry.claims()

    @property
    def fact_ids(self) -> frozenset[int]:
        return frozenset(i for claim in self.claims() for i in claim.fact_ids)


@dataclass(frozen=True, slots=True)
class CoverLetter:
    """Абзаци листа (розділені порожнім рядком; одинарний `\\n` усередині — межа рядка, як у
    підписі) і всі факти, на які він спирається."""

    paragraphs: tuple[str, ...]
    fact_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        words = sum(len(paragraph.split()) for paragraph in self.paragraphs)
        if not MIN_LETTER_WORDS <= words <= MAX_LETTER_WORDS:
            raise InvalidValue(
                "text",
                f"Лист — {MIN_LETTER_WORDS}–{MAX_LETTER_WORDS} слів, а тут {words}.",
            )
        placeholder = next(
            (m.group() for p in self.paragraphs if (m := PLACEHOLDER.search(p))), None
        )
        if placeholder is not None:
            raise InvalidValue("text", f"Незаповнений шаблон у листі: {placeholder}.")
        if not self.fact_ids:
            raise InvalidValue(
                "fact_ids", "Лист без fact_ids: вкажи факти, на які він спирається."
            )
        if len(self.fact_ids) > MAX_LETTER_FACT_IDS:
            raise InvalidValue(
                "fact_ids", f"Не більше {MAX_LETTER_FACT_IDS} fact_ids у листі."
            )

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)

    @property
    def lines(self) -> tuple[tuple[str, ...], ...]:
        """Рядки кожного абзацу: абзац без одинарних переносів — один рядок."""
        return tuple(tuple(paragraph.split("\n")) for paragraph in self.paragraphs)


@dataclass(frozen=True, slots=True)
class Document:
    """Збережена версія документа. Версії CV і листа однієї вакансії нумеруються незалежно."""

    id: DocumentId
    # Номер у межах користувача (з 1): його бачать люди й MCP; `id` — внутрішній ключ.
    number: int
    job_number: int
    kind: DocumentKind
    version: int
    content: Cv | CoverLetter
    created_at: datetime
    # Звіт ATS-lint на момент збереження; None — версії без звіту.
    lint: LintReport | None = None
    # Номер фото в шапці CV; None — без фото (чи фото видалено після збереження).
    photo_number: int | None = None

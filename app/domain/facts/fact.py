"""Факт, новий факт і оригінал CV. Факти — атомарні твердження з CV; у CV потрапляють лише підтверджені."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self

from domain.facts.ids import FactId
from domain.shared.errors import InvalidValue
from domain.shared.fingerprint import text_fingerprint

MAX_FACT_LENGTH = 500
MAX_CV_LENGTH = 50_000
MAX_FILE_NAME_LENGTH = 255
# Номер факту зберігається в int4: більший за нього не існує.
MAX_FACT_NUMBER = 2**31 - 1


class FactKind(StrEnum):
    """Порядок оголошення = порядок секцій у списку фактів."""

    EXPERIENCE = "experience"
    ACHIEVEMENT = "achievement"
    PROJECT = "project"
    SKILL = "skill"
    EDUCATION = "education"
    LANGUAGE = "language"


class FactSource(StrEnum):
    """Звідки факт: розібрано з CV, зі розмови чи вписано користувачем."""

    CV = "cv"
    CHAT = "chat"
    MANUAL = "manual"

    @classmethod
    def parse(cls, source: str) -> Self:
        try:
            return cls(source)
        except ValueError:
            raise InvalidValue(
                "source", f"Невідоме джерело факту: {source!r}."
            ) from None


@dataclass(frozen=True, slots=True)
class NewFact:
    """Одне атомарне твердження з CV. Цифри й назви — як у джерелі, без перефразування."""

    kind: FactKind
    text: str
    source: FactSource = FactSource.CV
    # Нові факти непідтверджені; підтвердженим одразу створюється лише факт, вписаний вручну.
    confirmed: bool = False
    # Номер вакансії користувача, до якої факт прив'язано (відповідь на прогалину); None — загальний.
    job_number: int | None = None

    @classmethod
    def parse(cls, *, kind: str, text: str, source: FactSource = FactSource.CV) -> Self:
        try:
            fact_kind = FactKind(kind)
        except ValueError:
            raise InvalidValue("kind", f"Невідомий вид факту: {kind!r}.") from None
        text = " ".join(text.split())
        if not text:
            raise InvalidValue("text", "Факт не може бути порожнім.")
        if len(text) > MAX_FACT_LENGTH:
            raise InvalidValue(
                "text",
                f"Факт задовгий: більше {MAX_FACT_LENGTH} символів — розбий на кілька.",
            )
        return cls(kind=fact_kind, text=text, source=source)

    @property
    def fingerprint(self) -> str:
        """Дубль = той самий текст без урахування пробілів і регістру, хоч і іншого виду."""
        return text_fingerprint(self.text)


@dataclass(frozen=True, slots=True)
class Fact:
    id: FactId
    # Номер у межах користувача (з 1): його бачать люди й MCP; `id` — внутрішній ключ.
    number: int
    kind: FactKind
    text: str
    confirmed: bool
    created_at: datetime
    updated_at: datetime
    source: FactSource = FactSource.CV
    # Номер вакансії користувача, до якої факт прив'язано; не задано — загальний.
    job_id: int | None = None


@dataclass(frozen=True, slots=True)
class NewOriginalCv:
    """Текст CV, який Claude прочитав з PDF. Байти PDF не зберігаються."""

    text: str
    file_name: str | None = None

    @classmethod
    def parse(cls, *, text: str, file_name: str) -> Self:
        text = text.strip()
        if not text:
            raise InvalidValue("text", "Текст CV порожній.")
        if len(text) > MAX_CV_LENGTH:
            raise InvalidValue("text", f"CV задовге: більше {MAX_CV_LENGTH} символів.")
        file_name = file_name.strip()
        if len(file_name) > MAX_FILE_NAME_LENGTH:
            raise InvalidValue(
                "file_name",
                f"Назва файлу задовга: більше {MAX_FILE_NAME_LENGTH} символів.",
            )
        return cls(text=text, file_name=file_name or None)


@dataclass(frozen=True, slots=True)
class OriginalCv:
    text: str
    file_name: str | None
    saved_at: datetime

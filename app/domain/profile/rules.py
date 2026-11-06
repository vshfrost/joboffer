"""Правила відбору вакансій за назвою й слова для зниження пріоритету."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from domain.profile.text import unique_lines


@dataclass(frozen=True, slots=True)
class Rules:
    """`title_keywords` порожні — назва не обмежена; `title_exclude` відсіюють вакансії;
    `stop_words` лише знижують пріоритет при аналізі."""

    title_keywords: tuple[str, ...] = ()
    title_exclude: tuple[str, ...] = ()
    stop_words: tuple[str, ...] = ()

    @classmethod
    def parse(
        cls,
        *,
        title_keywords: Sequence[str],
        title_exclude: Sequence[str],
        stop_words: Sequence[str],
    ) -> Self:
        return cls(
            title_keywords=unique_lines(title_keywords),
            title_exclude=unique_lines(title_exclude),
            stop_words=unique_lines(stop_words),
        )

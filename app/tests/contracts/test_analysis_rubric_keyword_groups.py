"""Рубрика аналізу вчить Claude писати ключові слова групами «a | b» (ATS-1) і карту фактів
`keyword_facts` (ATS-2). Ваги балів тут не перевіряємо."""

from pathlib import Path

import pytest

from application.ports.prompts import PromptKey
from infrastructure.prompts.catalog import FilePrompts

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
RUBRIC = FilePrompts.load(CATALOG).get(PromptKey.ANALYSIS_RUBRIC)

PHRASES = {
    "one requirement in several ways is one item joined by a bar": (
        'One requirement written several ways is ONE item with the variants joined by " | "'
    ),
    "at most five variants": "at most 5",
    "spellings and Spanish forms": "spellings, Spanish and English forms",
    "a group example": '"Java | Python"',
    "every requirement once": "list every requirement once, no duplicates",
    "the fact map": "- keyword_facts: for each keyword that confirmed facts back",
    "keywords no fact backs are left out": "leave out keywords no fact backs",
}


@pytest.mark.parametrize("phrase", PHRASES.values(), ids=PHRASES.keys())
def test_rubric_teaches(phrase: str) -> None:
    assert phrase in RUBRIC

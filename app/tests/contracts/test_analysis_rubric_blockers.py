"""Рубрика аналізу називає три блокери окремо: головна мова програмування без факту, локація чи режим
роботи поза профілем, розмовна мова вище за рівень користувача. Ваги балів тут не перевіряємо."""

from pathlib import Path

import pytest

from application.ports.prompts import PromptKey
from infrastructure.prompts.catalog import FilePrompts

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
RUBRIC = FilePrompts.load(CATALOG).get(PromptKey.ANALYSIS_RUBRIC).lower()

BLOCKER_PHRASES = {
    "main programming language without a fact": "blocker: main programming language without a confirmed fact",
    "location or work mode outside the profile": "blocker: location or work mode outside the profile",
    "spoken language above the user's level": "blocker: spoken language above the user's level",
}


@pytest.mark.parametrize("phrase", BLOCKER_PHRASES.values(), ids=BLOCKER_PHRASES.keys())
def test_rubric_names_blocker(phrase: str) -> None:
    assert phrase in RUBRIC

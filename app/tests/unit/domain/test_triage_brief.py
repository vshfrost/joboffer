"""Текст вакансії для агента: розпізнані секції вимог — лише вони, інакше весь текст."""

from domain.triage.brief import AgentText, TextScope, agent_text

POSTING = """About us
We are a great company.

Requirements:
- Python
- Docker

Nice to have:
- Kafka

Benefits:
Free lunch
"""


def test_recognised_sections_give_only_the_requirements_and_the_nice_to_haves() -> None:
    assert agent_text(POSTING) == AgentText(
        "Requirements:\n- Python\n- Docker\n\nNice to have:\n- Kafka",
        TextScope.REQUIREMENTS,
    )


def test_only_a_requirements_section_gives_only_that_section() -> None:
    assert agent_text("About us\nGreat.\n\nRequirements:\n- Python\n") == AgentText(
        "Requirements:\n- Python", TextScope.REQUIREMENTS
    )


def test_only_a_nice_to_have_section_gives_only_that_section() -> None:
    assert agent_text("About us\nGreat.\n\nNice to have:\n- Kafka\n") == AgentText(
        "Nice to have:\n- Kafka", TextScope.REQUIREMENTS
    )


def test_ukrainian_headings_are_recognised() -> None:
    text = "Про нас\nКомпанія.\n\nВимоги:\n- Python\n\nМи пропонуємо:\n- Офіс"
    assert agent_text(text) == AgentText(
        "Requirements:\n- Python", TextScope.REQUIREMENTS
    )


def test_a_text_without_recognised_sections_comes_whole() -> None:
    text = "We need a Python engineer who knows Docker.\nRemote, Europe."
    assert agent_text(text) == AgentText(text, TextScope.FULL)


def test_headings_with_nothing_under_them_fall_back_to_the_whole_text() -> None:
    text = "Requirements:\nBenefits:\nFree lunch"
    assert agent_text(text) == AgentText(text, TextScope.FULL)


def test_the_whole_text_is_not_cut() -> None:
    text = "a" * 5000
    assert agent_text(text) == AgentText(text, TextScope.FULL)

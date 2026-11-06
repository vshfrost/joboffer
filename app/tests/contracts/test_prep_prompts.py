"""Промпти тем підготовки в каталозі: правила = v1 TOPIC_RULES без імені власника, описи тулів."""

import re
from pathlib import Path

from application.ports.prompts import PromptKey
from infrastructure.prompts.catalog import FilePrompts
from tests.support.v1_topic_rules import NEUTRAL_TOPIC_RULES, V1_TOPIC_RULES

CATALOG = Path(__file__).resolve().parents[2] / "prompts"
OWNER = re.compile(r"\b(Taras|he|his|him|himself)\b")


def _text(key: PromptKey) -> str:
    return FilePrompts.load(CATALOG).get(key)


CV_DEFENCE_RULE = (
    "- Also propose a topic for each claim the CV already makes for this job (cv_lines, each "
    "with the facts behind it) that the user must defend in the interview, e.g. state "
    "management or 4+ years of full stack; gap: the CV line, as worded.\n"
)


def test_topic_rules_are_v1_plus_the_cv_defence_rule() -> None:
    # ATS-5 додав одне правило до v1; решта тексту дослівно v1.
    assert CV_DEFENCE_RULE in _text(PromptKey.PREP_TOPIC_RULES)
    assert (
        _text(PromptKey.PREP_TOPIC_RULES).replace(CV_DEFENCE_RULE, "")
        == NEUTRAL_TOPIC_RULES
    )


def test_topic_rules_still_cover_the_gaps() -> None:
    assert "Propose interview-prep topics that close this job's gaps." in _text(
        PromptKey.PREP_TOPIC_RULES
    )


def test_topic_rules_do_not_name_the_owner() -> None:
    text = _text(PromptKey.PREP_TOPIC_RULES)
    assert not OWNER.search(text)
    assert OWNER.search(V1_TOPIC_RULES)


def test_topic_rules_say_what_the_user_decides() -> None:
    text = _text(PromptKey.PREP_TOPIC_RULES)
    assert (
        "reuse its slug and send its\n  title, kind, summary and deadline unchanged "
        "unless the user asks to change them." in text
    )
    assert (
        "- deadline: YYYY-MM-DD only when the user gives one, otherwise empty." in text
    )
    assert (
        "- Show the user the proposed list first; call save_prep_topics only with the "
        "topics the user approves." in text
    )


def test_prepare_prep_topics_description_is_the_v1_text_addressed_to_any_user() -> None:
    assert _text(PromptKey.MCP_TOOL_PREPARE_PREP_TOPICS) == (
        "The analysed job's requirements and gaps, the user's existing prep topics and "
        "the rules for proposing new ones. Show the user the proposal, then call "
        "save_prep_topics."
    )


def test_save_prep_topics_description_is_the_v1_text_addressed_to_any_user() -> None:
    assert _text(PromptKey.MCP_TOOL_SAVE_PREP_TOPICS) == (
        "Save the topics the user approved and link them to the job. An existing slug "
        "updates that topic instead of creating a duplicate. One invalid topic rejects "
        "the whole call."
    )


def test_list_prep_topics_description_is_the_v1_text_addressed_to_any_user() -> None:
    assert _text(PromptKey.MCP_TOOL_LIST_PREP_TOPICS) == (
        "The user's interview-prep topics by priority (jobs that need them and their "
        "scores), with the closer deadline first among equals."
    )

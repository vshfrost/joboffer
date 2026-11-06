"""Усі промпти лежать в `app/prompts/` і написані англійською; запити веба — шаблони з {job_id}/{topic_id}."""

import re
from pathlib import Path

import pytest

from application.ports.prompts import PromptKey

CATALOG = Path(__file__).resolve().parents[2] / "prompts"

CYRILLIC = re.compile("[А-Яа-яІіЇїЄєҐґʼ’]")
# Дані, а не мова промпта: приклад синоніма міста і значення причини в MCP-інструкціях.
DATA_EXAMPLES = ("Мадрид", "фільтр профілю")

NEW_KEYS = [
    "onboarding/setup",
    "requests/analysis",
    "requests/triage",
    "requests/cv",
    "requests/cover_letter",
    "requests/plan",
    "requests/questions",
    "requests/quiz",
    "requests/quiz_topic",
    "requests/topics",
    "requests/job_prep",
    "requests/interview_kit",
    "requests/gaps",
    "requests/facts",
    "requests/add_job",
    "requests/reanalysis",
    "requests/apply",
]

TEMPLATES = {
    "requests/analysis": "Analyse job #{job_id} in joboffer",
    "requests/triage": (
        "Triage the new jobs in joboffer. Call prepare_triage once and rate every job of that batch (up to 5) by the returned rules, which are the same as the server's own keyword triage, then call save_triage. Do one batch only: show me a short summary (how many analyse, maybe and skip, and the reasons for the analyse ones) and ask whether to continue with the next batch. Do not hide any job because of its triage."
    ),
    "requests/cv": (
        "Prepare a CV for job #{job_id} in joboffer using prepare_cv. Use the "
        "confirmed facts and the rules from the brief. Call check_cv until it "
        "passes, then save the CV once with save_cv; it replaces the previous CV. "
        "Do not add unconfirmed claims."
    ),
    "requests/cover_letter": (
        "Prepare a cover letter for job #{job_id} in joboffer using "
        "prepare_cover_letter. Use the confirmed facts and the rules from the brief. "
        "Call check_cover_letter until it passes, then save the letter once with "
        "save_cover_letter; it replaces the previous letter. Do not add unconfirmed "
        "claims."
    ),
    "requests/plan": "Create or update the plan for topic #{topic_id} in joboffer",
    "requests/questions": "Write quiz questions for topic #{topic_id} in joboffer",
    "requests/quiz": "Run today's quiz in joboffer",
    "requests/quiz_topic": "Run today's quiz for topic #{topic_id} in joboffer",
    "requests/topics": ("Suggest prep topics based on the gaps in my jobs in joboffer"),
    "requests/job_prep": "Prepare me for job #{job_id} in joboffer",
    "requests/interview_kit": "Prepare an interview kit for job #{job_id} in joboffer",
    "requests/gaps": (
        "Clarify the open gaps of job #{job_id} in joboffer. Call "
        "prepare_analysis to see the gaps, their questions and the answers "
        "already given, and list_facts to see what is already known. Ask me "
        "about each open gap, one at a time. If I have the experience, write "
        "each fact as one atomic claim with my numbers and names, and only "
        "after I approve the wording call answer_gap with has_experience true "
        "and those facts. If I do not, call answer_gap with has_experience "
        "false. Never ask again about a gap that already has an answer, and "
        "never invent facts."
    ),
    "requests/facts": (
        "Help me add facts to my joboffer profile. Call list_facts first and "
        "do not repeat what is already saved. Ask me one question at a time "
        "about the experience, skills, projects and achievements that are "
        "missing. Write each fact as one atomic claim with my numbers, names "
        "and dates exactly as I say them, show it to me, and only after I "
        "approve the wording call save_facts with source chat and then "
        "confirm_facts for the approved facts. Never infer or invent anything."
    ),
}


def _text(key: str) -> str:
    return (CATALOG / f"{key}.md").read_bytes().decode("utf-8")


def _without_data_examples(text: str) -> str:
    for example in DATA_EXAMPLES:
        text = text.replace(example, "")
    return text


@pytest.mark.parametrize("key", NEW_KEYS)
def test_the_web_prompt_is_a_catalog_key(key: str) -> None:
    assert key in {k.value for k in PromptKey}


@pytest.mark.parametrize("key", NEW_KEYS)
def test_the_web_prompt_file_is_english_and_not_empty(key: str) -> None:
    text = _text(key)

    assert text.strip() != ""
    assert not CYRILLIC.search(_without_data_examples(text))


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_request_template_is_the_translated_ukrainian_request(key: str) -> None:
    assert _text(key) == TEMPLATES[key]


def test_no_prompt_file_has_cyrillic_outside_the_data_examples() -> None:
    files = sorted(CATALOG.rglob("*.md"))
    assert files != []
    for file in files:
        text = _without_data_examples(file.read_text(encoding="utf-8"))
        assert not CYRILLIC.search(text), file.relative_to(CATALOG)


def test_mcp_instructions_keep_the_data_examples() -> None:
    text = _text("mcp/instructions")

    assert "Мадрид" in text
    assert "фільтр профілю" in text


def test_mcp_instructions_answer_in_the_users_language() -> None:
    text = _text("mcp/instructions")

    assert "guide the user through the next pending step in the user's language" in text
    assert "in Ukrainian" not in text


def test_setup_prompt_is_a_rules_section_and_seven_step_blocks() -> None:
    text = _text("onboarding/setup")

    assert text.startswith("Set up my joboffer profile with me, step by step")
    assert "\nRules\n- " in text
    paragraphs = text.split("\n\n")
    steps = [p for p in paragraphs if re.match(r"Step \d — ", p)]
    assert [p[:6] for p in steps] == [f"Step {n}" for n in range(7)]
    assert any(p.startswith("Finish. Call get_profile") for p in paragraphs)
    assert len(text) < 5000
